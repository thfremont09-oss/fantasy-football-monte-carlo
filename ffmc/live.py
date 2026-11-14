"""Live board: scores and odds for the top leagues around the world.

* Scores, game status and DraftKings lines (moneyline, spread, total) come from
  ESPN's public scoreboards. For games in progress, ESPN shows DraftKings'
  pre-game line.
* Kalshi keeps trading during games, so its price is a live win probability.
  Each game is matched to its Kalshi "who wins" market by team names and time.
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from .http import APIError, CachedJSON

ESPN = "https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2/markets"

# (sport, league, ESPN path, Kalshi winner series)
LEAGUES = [
    ("Football", "NFL", "football/nfl", "KXNFLGAME"),
    ("Football", "College Football", "football/college-football", "KXNCAAFGAME"),
    ("Basketball", "NBA", "basketball/nba", "KXNBAGAME"),
    ("Basketball", "WNBA", "basketball/wnba", "KXWNBAGAME"),
    ("Basketball", "Men's College Basketball", "basketball/mens-college-basketball", "KXNCAAMBGAME"),
    ("Hockey", "NHL", "hockey/nhl", "KXNHLGAME"),
    ("Baseball", "MLB", "baseball/mlb", "KXMLBGAME"),
    ("Soccer", "Premier League", "soccer/eng.1", "KXEPLGAME"),
    ("Soccer", "La Liga", "soccer/esp.1", "KXLALIGAGAME"),
    ("Soccer", "Bundesliga", "soccer/ger.1", "KXBUNDESLIGAGAME"),
    ("Soccer", "Serie A", "soccer/ita.1", "KXSERIEAGAME"),
    ("Soccer", "Ligue 1", "soccer/fra.1", "KXLIGUE1GAME"),
    ("Soccer", "Champions League", "soccer/uefa.champions", "KXUCLGAME"),
    ("Soccer", "Europa League", "soccer/uefa.europa", "KXUELGAME"),
    ("Soccer", "MLS", "soccer/usa.1", "KXMLSGAME"),
    ("Soccer", "Liga MX", "soccer/mex.1", "KXLIGAMXGAME"),
    ("Soccer", "Eredivisie", "soccer/ned.1", "KXEREDIVISIEGAME"),
    ("Soccer", "Primeira Liga", "soccer/por.1", "KXLIGAPORTUGALGAME"),
    ("Soccer", "Brasileirão", "soccer/bra.1", "KXBRASILEIROGAME"),
    ("Soccer", "Argentine Primera", "soccer/arg.1", "KXARGPREMDIVGAME"),
    ("Soccer", "Saudi Pro League", "soccer/ksa.1", "KXSAUDIPLGAME"),
    ("Soccer", "EFL Championship", "soccer/eng.2", "KXEFLCHAMPIONSHIPGAME"),
    ("Soccer", "Scottish Premiership", "soccer/sco.1", "KXSCOTTISHPREMGAME"),
    ("Tennis", "ATP", "tennis/atp", "KXATPMATCH"),
    ("Tennis", "WTA", "tennis/wta", "KXWTAMATCH"),
    ("MMA", "UFC", "mma/ufc", "KXUFCFIGHT"),
]


@dataclass
class Side:
    name: str
    short: str
    logo: str | None = None
    score: str = ""
    winner: bool = False
    record: str = ""
    dk: int | None = None          # DraftKings moneyline (American odds)
    kalshi: float | None = None    # Kalshi win chance (0-1)
    kalshi_ticker: str | None = None


@dataclass
class Game:
    id: str
    sport: str
    league: str
    start: dt.datetime
    state: str                     # pre, in, post
    detail: str                    # "Q3 5:12", "Final", "Sat, Nov 15 at 1:00 PM EST"...
    sides: list[Side]              # away/first, then home/second
    venue: str = ""
    draw_dk: int | None = None
    draw_kalshi: float | None = None
    spread: str = ""               # e.g. "DET -2.5 (-120)"
    total: str = ""                # e.g. "O/U 51.5 (o +100 / u -120)"
    kalshi_updated: bool = False
    kalshi_series: str | None = None
    draw_ticker: str | None = None
    path: str = ""                 # ESPN league path, e.g. "basketball/nba"
    event_id: str = ""             # ESPN event id (differs from the match id in tennis)
    tags: set[str] = field(default_factory=set)
    period: int = 0                # quarter / half / period / inning in progress
    clock: float = 0.0             # ESPN game clock in seconds (time left; time played in soccer)

    @property
    def key(self) -> str:
        """Identifies the game in a link: path~event~match."""
        return f"{self.path}~{self.event_id}~{self.id}"

    def dk_fair(self) -> list[float] | None:
        """DraftKings' win chances with the bookmaker's cut removed (sides, then draw)."""
        lines = [s.dk for s in self.sides] + ([self.draw_dk] if self.draw_dk is not None else [])
        if any(x is None for x in lines):
            return None
        imp = [1 / (1 + (o / 100 if o > 0 else 100 / -o)) for o in lines]
        return [x / sum(imp) for x in imp]

    @property
    def label(self) -> str:
        return " vs ".join(s.name for s in self.sides)

    def matches(self, query: str) -> bool:
        q = _norm(query)
        hay = _norm(" ".join([self.league, self.sport, self.venue] + [f"{s.name} {s.short}" for s in self.sides]))
        return all(word in hay for word in q.split())


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower().replace("&", "and")).strip()


def _odds(x) -> int | None:
    try:
        s = str(x).strip().upper()
        if s in ("EVEN", "EV"):
            return 100
        v = int(float(s.replace("+", "")))
        return v if abs(v) >= 100 else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ ESPN side
def _side(c: dict) -> Side:
    t = c.get("team") or c.get("athlete") or {}
    logo = t.get("logo") or ((t.get("flag") or {}).get("href")) or None
    score = c.get("score")
    if isinstance(score, dict):
        score = score.get("displayValue")
    if score in (None, "") and c.get("linescores"):                    # tennis: set scores
        score = " ".join(str(int(float(l.get("value", 0)))) for l in c["linescores"])
    rec = ""
    for r in c.get("records") or []:
        if r.get("summary"):
            rec = r["summary"]
            break
    return Side(name=t.get("displayName") or t.get("shortDisplayName") or "?",
                short=t.get("abbreviation") or t.get("shortDisplayName") or "",
                logo=logo, score=str(score or ""), winner=bool(c.get("winner")), record=rec)


def _game(comp: dict, event: dict, sport: str, league: str) -> Game | None:
    cs = comp.get("competitors") or []
    if len(cs) < 2:
        return None
    order = sorted(cs, key=lambda c: {"away": 0, "home": 1}.get(c.get("homeAway"), c.get("order", 0)))
    sides = [_side(c) for c in order]
    status = comp.get("status") or event.get("status") or {}
    stype = status.get("type", {})
    when = comp.get("date") or comp.get("startDate") or event.get("date")
    start = dt.datetime.fromisoformat(when.replace("Z", "+00:00"))
    g = Game(id=str(comp.get("id") or event.get("id")), sport=sport, league=league, start=start,
             state=stype.get("state", "pre"), detail=stype.get("shortDetail") or stype.get("detail") or "",
             sides=sides, venue=(comp.get("venue") or {}).get("fullName", ""))
    try:
        g.period, g.clock = int(status.get("period") or 0), float(status.get("clock") or 0)
    except (TypeError, ValueError):
        pass
    odds = next((o for o in comp.get("odds") or [] if "draftkings" in o.get("provider", {}).get("name", "").lower()), None)
    if odds:
        ml = odds.get("moneyline") or {}
        by_side = {"away": 0, "home": 1}
        for key, idx in by_side.items():
            line = _odds(((ml.get(key) or {}).get("close") or {}).get("odds"))
            if line is not None and idx < len(sides):
                sides[idx].dk = line
        g.draw_dk = _odds(((ml.get("draw") or {}).get("close") or {}).get("odds"))
        ps = odds.get("pointSpread") or {}
        home = (ps.get("home") or {}).get("close") or {}
        if home.get("line"):
            g.spread = f"{sides[1].short or sides[1].name} {home['line']} ({home.get('odds', '')})"
        tot = odds.get("total") or {}
        over, under = (tot.get("over") or {}).get("close") or {}, (tot.get("under") or {}).get("close") or {}
        if over.get("line"):
            g.total = f"O/U {str(over['line']).lstrip('ou')} (o {over.get('odds', '')} / u {under.get('odds', '')})"
    return g


def espn_games(http: CachedJSON, path: str, sport: str, league: str, days: list[dt.date]) -> list[Game]:
    games = []
    for day in days:
        try:
            data = http.get(ESPN.format(path=path), [("dates", day.strftime("%Y%m%d")), ("limit", "300")], ttl=12)
        except APIError:
            continue
        for e in data.get("events", []):
            comps = []
            for grp in e.get("groupings") or []:                   # tennis: tournament -> matches
                if "singles" in (grp.get("grouping", {}).get("displayName", "").lower()):
                    comps += grp.get("competitions", [])
            comps += e.get("competitions") or []
            for comp in comps:
                g = _game(comp, e, sport, league)
                if g:
                    g.path, g.event_id = path, str(e.get("id", ""))
                    games.append(g)
    return games


# ----------------------------------------------------------- game details
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/{path}/summary"


@dataclass
class Details:
    team_stats: list[tuple[str, str, str]] = field(default_factory=list)       # (label, away, home)
    stats_kind: str = ""                                                        # "Game stats" or "Season averages"
    leaders: list[tuple[str, list[tuple[str, str, str]]]] = field(default_factory=list)  # category -> (team, name, value)
    predictor: tuple[float, float] | None = None                                # ESPN matchup predictor (away, home)
    win_prob: list[tuple[dt.datetime, float]] = field(default_factory=list)    # ESPN model: (time, home win chance)
    plays: list[tuple[str, str]] = field(default_factory=list)                 # (period/clock, description), newest first
    last_five: list[tuple[str, list[str]]] = field(default_factory=list)       # team -> results
    venue: str = ""
    broadcast: str = ""


def game_details(path: str, event_id: str, cache_dir=".ffmc_cache") -> Details:
    """Stats for one game from ESPN's game summary (box score, leaders, win probability, plays)."""
    d = Details()
    if not path or not event_id:
        return d
    try:
        s = CachedJSON(cache_dir).get(SUMMARY.format(path=path), [("event", event_id)], ttl=12)
    except APIError:
        return d
    bs = s.get("boxscore") or {}
    teams = sorted(bs.get("teams") or [], key=lambda t: {"away": 0, "home": 1}.get(t.get("homeAway"), 0))
    if len(teams) == 2:
        rows: dict[str, list[str]] = {}
        for i, t in enumerate(teams):
            for st in t.get("statistics") or []:
                label = st.get("label") or st.get("displayName") or st.get("name", "")
                rows.setdefault(label, ["", ""])[i] = str(st.get("displayValue", ""))
        d.team_stats = [(k, a, h) for k, (a, h) in rows.items() if a or h]
        state = ((s.get("header") or {}).get("competitions") or [{}])[0].get("status", {}).get("type", {}).get("state")
        d.stats_kind = "Season averages" if state == "pre" else "Game stats"
    for team_block in s.get("leaders") or []:
        abbr = (team_block.get("team") or {}).get("abbreviation", "")
        for cat in team_block.get("leaders") or []:
            top = (cat.get("leaders") or [None])[0]
            if not top:
                continue
            name = (top.get("athlete") or {}).get("displayName", "")
            entry = next((c for c in d.leaders if c[0] == cat.get("displayName")), None)
            if entry is None:
                entry = (cat.get("displayName") or cat.get("name", ""), [])
                d.leaders.append(entry)
            entry[1].append((abbr, name, str(top.get("displayValue", ""))))
    pred = s.get("predictor") or {}
    try:
        d.predictor = (float(pred["awayTeam"]["gameProjection"]) / 100, float(pred["homeTeam"]["gameProjection"]) / 100)
    except (KeyError, TypeError, ValueError):
        pass
    plays = s.get("plays") or []
    when = {}
    for p in plays:
        if p.get("wallclock"):
            try:
                when[str(p.get("id"))] = dt.datetime.fromisoformat(p["wallclock"].replace("Z", "+00:00"))
            except ValueError:
                pass
    for w in s.get("winprobability") or []:
        t = when.get(str(w.get("playId")))
        if t is not None and w.get("homeWinPercentage") is not None:
            d.win_prob.append((t, float(w["homeWinPercentage"])))
    for p in reversed(plays[-12:]):
        per = (p.get("period") or {}).get("displayValue") or (f"P{p['period'].get('number')}" if p.get("period") else "")
        clock = (p.get("clock") or {}).get("displayValue", "")
        d.plays.append((" ".join(x for x in (per, clock) if x), p.get("text", "")))
    for team_block in s.get("lastFiveGames") or []:
        abbr = (team_block.get("team") or {}).get("abbreviation", "")
        results = []
        for ev in team_block.get("events") or []:
            opp = (ev.get("opponent") or {}).get("abbreviation", "")
            results.append(f"{ev.get('gameResult', '')} {ev.get('score', '')} {ev.get('atVs', '')} {opp}".strip())
        if results:
            d.last_five.append((abbr, results))
    info = s.get("gameInfo") or {}
    d.venue = (info.get("venue") or {}).get("fullName", "")
    bc = s.get("broadcasts") or []
    if bc:
        names = bc[0].get("media", {}).get("shortName") or ", ".join(bc[0].get("names", []) or [])
        d.broadcast = names or ""
    return d


# ---------------------------------------------------------------- Kalshi side
def kalshi_prices(http: CachedJSON, series: str) -> dict[str, list[dict]]:
    """Open Kalshi winner markets for a series, grouped by event."""
    try:
        data = http.get(KALSHI, [("series_ticker", series), ("status", "open"), ("limit", "1000")], ttl=12)
    except APIError:
        return {}
    events: dict[str, list[dict]] = {}
    for m in data.get("markets", []):
        events.setdefault(m["event_ticker"], []).append(m)
    return events


def _chance(m: dict) -> float | None:
    bid, ask = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
    if 0 < bid < ask <= 1:
        return (bid + ask) / 2
    last = float(m.get("last_price_dollars") or 0)
    return last if 0 < last < 1 else None


def _same(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    last_a, last_b = a.split()[-1], b.split()[-1]                    # tennis/UFC: surnames
    return len(last_a) > 3 and last_a == last_b


def attach_kalshi(games: list[Game], events: dict[str, list[dict]], series: str = "") -> None:
    for markets in events.values():
        names = [(m.get("yes_sub_title") or m.get("title") or "", m) for m in markets]
        when = markets[0].get("occurrence_datetime") or markets[0].get("expected_expiration_time")
        try:
            k_time = dt.datetime.fromisoformat(str(when).replace("Z", "+00:00"))
        except ValueError:
            k_time = None
        teams = [(n, m) for n, m in names if _norm(n) not in ("tie", "draw")]
        for g in games:
            if k_time and abs((g.start - k_time).total_seconds()) > 40 * 3600:
                continue
            pairs = {}
            for n, m in teams:
                hits = [i for i, s in enumerate(g.sides) if _same(n, s.name) or _same(n, s.short)]
                if len(hits) == 1:
                    pairs[hits[0]] = m
            if len(pairs) == len(teams) == len(g.sides):
                for i, m in pairs.items():
                    g.sides[i].kalshi = _chance(m)
                    g.sides[i].kalshi_ticker = m["ticker"]
                tie = next((m for n, m in names if _norm(n) in ("tie", "draw")), None)
                if tie:
                    g.draw_kalshi = _chance(tie)
                    g.draw_ticker = tie["ticker"]
                g.kalshi_updated = True
                g.kalshi_series = series
                break


def kalshi_history(series: str, ticker: str, hours: float, interval: int, cache_dir=".ffmc_cache"
                   ) -> list[tuple[dt.datetime, float]]:
    """Kalshi win chance over time: (time, mid of bid and ask) per ``interval``-minute candle."""
    http = CachedJSON(cache_dir)
    end = int(dt.datetime.now(dt.timezone.utc).timestamp())
    try:
        data = http.get(f"https://api.elections.kalshi.com/trade-api/v2/series/{series}/markets/{ticker}/candlesticks",
                        [("start_ts", str(end - int(hours * 3600))), ("end_ts", str(end)),
                         ("period_interval", str(interval))], ttl=30)
    except APIError:
        return []
    out = []
    for c in data.get("candlesticks", []):
        bid = float((c.get("yes_bid") or {}).get("close_dollars") or 0)
        ask = float((c.get("yes_ask") or {}).get("close_dollars") or 0)
        last = float((c.get("price") or {}).get("close_dollars") or 0)
        val = (bid + ask) / 2 if 0 < bid < ask <= 1 else (last if 0 < last < 1 else None)
        if val is not None:
            out.append((dt.datetime.fromtimestamp(c["end_period_ts"], dt.timezone.utc), val))
    return out


# ------------------------------------------------------------------- board
def load_board(cache_dir=".ffmc_cache", leagues=LEAGUES, now: dt.datetime | None = None) -> list[Game]:
    """Every game from yesterday to tomorrow in the top leagues, with scores and both apps' odds."""
    now = now or dt.datetime.now(dt.timezone.utc)
    http = CachedJSON(cache_dir)
    days = [(now + dt.timedelta(d)).date() for d in (-1, 0, 1)]
    with ThreadPoolExecutor(12) as pool:
        espn = list(pool.map(lambda l: espn_games(http, l[2], l[0], l[1], days), leagues))
    with ThreadPoolExecutor(6) as pool:
        kal = list(pool.map(lambda l: kalshi_prices(http, l[3]), leagues))
    games: list[Game] = []
    for lg, gs, events in zip(leagues, espn, kal):
        seen = {}
        for g in gs:
            seen.setdefault(g.id, g)
        gs = list(seen.values())
        attach_kalshi([g for g in gs if g.state != "post"], events, lg[3])
        games += gs
    # Keep what's relevant: live now, finished in the last 18 hours, or starting in the next 36.
    keep = []
    for g in games:
        if g.state == "in":
            keep.append(g)
        elif g.state == "post" and now - g.start < dt.timedelta(hours=18):
            keep.append(g)
        elif g.state == "pre" and dt.timedelta(hours=-2) < g.start - now < dt.timedelta(hours=36):
            keep.append(g)
    live = sorted((g for g in keep if g.state == "in"), key=lambda g: g.start)
    upcoming = sorted((g for g in keep if g.state == "pre"), key=lambda g: g.start)
    final = sorted((g for g in keep if g.state == "post"), key=lambda g: g.start, reverse=True)
    return live + upcoming + final


EASTERN = ZoneInfo("America/New_York")
TEAMS = "https://site.api.espn.com/apis/site/v2/sports/{path}/teams"


def team_index(cache_dir=".ffmc_cache") -> list[tuple[str, str, list[str]]]:
    """(league, team id, names) for every team in the team leagues; refreshed once a day."""
    http = CachedJSON(cache_dir)

    def one(lg):
        try:
            data = http.get(TEAMS.format(path=lg[2]), [("limit", "1000")], ttl=86400)
        except APIError:
            return []
        out = []
        for lgs in (data.get("sports") or [{}])[0].get("leagues") or []:
            for t in lgs.get("teams") or []:
                t = t.get("team") or {}
                names = [t.get(k, "") for k in ("displayName", "shortDisplayName", "name", "nickname",
                                                "location", "abbreviation") if t.get(k)]
                if t.get("id") and names:
                    out.append((lg[1], str(t["id"]), names))
        return out

    with ThreadPoolExecutor(12) as pool:
        parts = pool.map(one, [l for l in LEAGUES if l[0] not in ("Tennis", "MMA")])
    return [t for part in parts for t in part]


def find_teams(query: str, index: list[tuple[str, str, list[str]]], limit: int = 6) -> list[tuple[str, str, str]]:
    """Teams whose name matches the search: (league, team id, full name). Whole-name matches first."""
    q = query.lower().strip()
    if len(q) < 3:
        return []
    hits = []
    for league, tid, names in index:
        low = [n.lower() for n in names]
        if q in low:
            hits.append((0, league, tid, names[0]))
        elif any(q in n for n in low[:5]):          # skip abbreviations for partial matches
            hits.append((1, league, tid, names[0]))
    order = {l[1]: i for i, l in enumerate(LEAGUES)}
    college = lambda lg: "College" in lg            # pro teams before college teams with the same nickname
    hits.sort(key=lambda h: (h[0], college(h[1]), order.get(h[1], 99)))
    return [(l, t, n) for _, l, t, n in hits[:limit]]


def correct(query: str, index: list[tuple[str, str, list[str]]]) -> str | None:
    """Spelling fix for a search with no exact hits, e.g. 'bayren' -> 'Bayern Munich'. None if it already matches."""
    q = query.lower().strip()
    if len(q) < 3 or find_teams(q, index, 1) or any(q in l[1].lower() for l in LEAGUES):
        return None
    words: dict[str, str] = {}
    for _, _, names in index:
        for n in names[:5]:
            words.setdefault(n.lower(), names[0])
            for w in n.lower().split():
                if len(w) > 3:
                    words.setdefault(w, names[0])
    for l in LEAGUES:
        words.setdefault(l[1].lower(), l[1])
    best = difflib.get_close_matches(q, list(words), n=1, cutoff=0.72)
    return words[best[0]] if best else None


def next_games(query: str, cache_dir=".ffmc_cache", now: dt.datetime | None = None) -> list[Game]:
    """The next game (however far away) for every team matching the search, in each competition."""
    now = now or dt.datetime.now(dt.timezone.utc)
    http = CachedJSON(cache_dir)
    index = team_index(cache_dir)
    teams = find_teams(query, index) or find_teams(correct(query, index) or "", index)

    def one(team):
        league, tid, _ = team
        sport, _, path, _ = league_info(league)
        params = [("fixture", "true")] if sport == "Soccer" else []
        try:
            data = http.get(f"{TEAMS.format(path=path)}/{tid}/schedule", params, ttl=1800)
        except APIError:
            return None
        upcoming = []
        for e in data.get("events") or []:
            state = ((e.get("competitions") or [{}])[0].get("status") or {}).get("type", {}).get("state")
            try:
                start = dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if state == "in" or (state == "pre" and start > now - dt.timedelta(hours=3)):
                upcoming.append((start, str(e.get("id"))))
        if not upcoming:
            return None
        start, eid = min(upcoming)
        day = start.astimezone(EASTERN).date()
        return next((g for g in load_schedule(league, day, cache_dir) if g.id == eid or g.event_id == eid), None)

    with ThreadPoolExecutor(6) as pool:
        found = [g for g in pool.map(one, teams) if g is not None]
    seen: dict[str, Game] = {}
    for g in sorted(found, key=lambda g: g.start):
        seen.setdefault(g.key, g)
    return list(seen.values())


def league_info(name: str) -> tuple[str, str, str, str]:
    return next(l for l in LEAGUES if l[1] == name)


def load_schedule(league: str, day: dt.date, cache_dir=".ffmc_cache") -> list[Game]:
    """One league's games on one day (US Eastern), with both apps' odds where they're posted."""
    sport, name, path, series = league_info(league)
    http = CachedJSON(cache_dir)
    # ESPN files late-night games under the next day, so ask for both and keep this day's.
    gs = espn_games(http, path, sport, name, [day, day + dt.timedelta(1)])
    seen: dict[str, Game] = {}
    for g in gs:
        if g.start.astimezone(EASTERN).date() == day:
            seen.setdefault(g.id, g)
    games = sorted(seen.values(), key=lambda g: g.start)
    attach_kalshi([g for g in games if g.state != "post"], kalshi_prices(http, series), series)
    return games


def load_week(league: str, first: dt.date, days: int = 8, cache_dir=".ffmc_cache") -> list[Game]:
    """One league's games from ``first`` through the next ``days`` days (US Eastern dates)."""
    sport, name, path, series = league_info(league)
    http = CachedJSON(cache_dir)
    span = [first + dt.timedelta(i) for i in range(days + 1)]
    with ThreadPoolExecutor(6) as pool:
        parts = pool.map(lambda d: espn_games(http, path, sport, name, [d]), span)
    seen: dict[str, Game] = {}
    for g in (g for part in parts for g in part):
        if first <= g.start.astimezone(EASTERN).date() < first + dt.timedelta(days):
            seen.setdefault(g.id, g)
    games = sorted(seen.values(), key=lambda g: g.start)
    attach_kalshi([g for g in games if g.state != "post"], kalshi_prices(http, series), series)
    return games


def league_for_path(path: str) -> str | None:
    return next((l[1] for l in LEAGUES if l[2] == path), None)
