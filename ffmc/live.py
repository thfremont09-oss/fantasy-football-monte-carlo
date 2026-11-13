"""Live board: scores and odds for the top leagues around the world.

* Scores, game status and DraftKings lines (moneyline, spread, total) come from
  ESPN's public scoreboards. For games in progress, ESPN shows DraftKings'
  pre-game line.
* Kalshi keeps trading during games, so its price is a live win probability.
  Each game is matched to its Kalshi "who wins" market by team names and time.
"""

from __future__ import annotations

import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

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
    tags: set[str] = field(default_factory=set)

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
            data = http.get(ESPN.format(path=path), [("dates", day.strftime("%Y%m%d")), ("limit", "300")], ttl=25)
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
                    games.append(g)
    return games


# ---------------------------------------------------------------- Kalshi side
def kalshi_prices(http: CachedJSON, series: str) -> dict[str, list[dict]]:
    """Open Kalshi winner markets for a series, grouped by event."""
    try:
        data = http.get(KALSHI, [("series_ticker", series), ("status", "open"), ("limit", "1000")], ttl=25)
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
