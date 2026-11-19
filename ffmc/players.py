"""Player stats from ESPN: search any player, then this season, career, last game, live game and fun facts.

Sources (all public ESPN JSON on site.api.espn.com):
  search      /apis/common/v3/search?query=...&type=player
  overview    /apis/common/v3/sports/{sport}/{league}/athletes/{id}/overview   season / career / projected lines
  stats       /apis/common/v3/sports/{sport}/{league}/athletes/{id}/stats      every season + career totals
  gamelog     /apis/common/v3/sports/{sport}/{league}/athletes/{id}/gamelog    game by game
  scoreboard + summary (site/v2)                                              a game in progress right now
"""

from __future__ import annotations

import datetime as dt
import difflib
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from .http import APIError, CachedJSON

COMMON = "https://site.api.espn.com/apis/common/v3"
SITE = "https://site.api.espn.com/apis/site/v2/sports"
EASTERN = ZoneInfo("America/New_York")
SPORTS = {"football", "basketball", "hockey", "baseball", "soccer"}

# The numbers worth leading with, best first. The first few a player actually has are shown.
KEY_STATS = {
    "football": ["passingYards", "passingTouchdowns", "interceptions", "rushingYards", "rushingTouchdowns",
                 "receptions", "receivingYards", "receivingTouchdowns", "totalTackles", "sacks",
                 "fieldGoalsMade", "passesDefended"],
    "basketball": ["points", "totalRebounds", "assists", "threePointFieldGoalsMade", "steals", "blocks"],
    "hockey": ["goals", "assists", "points", "shotsTotal", "saves", "goalsAgainst", "wins"],
    "baseball": ["homeRuns", "hits", "RBIs", "runs", "stolenBases", "strikeouts", "wins", "innings"],
    "soccer": ["totalGoals", "goalAssists", "totalShots", "shotsOnTarget", "saves"],
}
# Stats where "a game with at least one" makes a streak worth mentioning.
STREAK_STATS = ["passingTouchdowns", "rushingTouchdowns", "receivingTouchdowns", "totalGoals", "goals", "points",
                "hits", "homeRuns", "threePointFieldGoalsMade"]


# ---------------------------------------------------------------- search

@dataclass
class Player:
    id: str
    name: str
    sport: str
    league: str               # ESPN league slug ("nfl", "nba"...); "all" for soccer
    label: str                # "NFL - New England Patriots"
    team: str = ""
    team_id: str = ""
    team_abbr: str = ""
    position: str = ""
    jersey: str = ""
    headshot: str = ""
    color: str = ""

    @property
    def key(self) -> str:
        return f"{self.sport}~{self.league}~{self.id}"

    @property
    def short_label(self) -> str:
        bits = [self.position, self.team or self.label]
        return " · ".join(b for b in bits if b)


def _player(item: dict) -> Player | None:
    if item.get("type") != "player" or item.get("sport") not in SPORTS:
        return None
    team = next((t for t in item.get("teamRelationships") or [] if t.get("type") == "team"), None)
    core = (team or {}).get("core") or {}
    pos = item.get("position") or {}
    return Player(
        id=str(item["id"]), name=item.get("displayName", ""), sport=item["sport"],
        league="all" if item["sport"] == "soccer" else item.get("league", ""),
        label=item.get("label", ""), team=(team or {}).get("displayName", ""), team_id=str(core.get("id", "")),
        team_abbr=core.get("abbreviation", ""), position=pos.get("abbreviation", ""),
        jersey=str(item.get("jersey") or ""), headshot=(item.get("headshot") or {}).get("href", ""),
        color=core.get("color", ""))


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("-", " ")).strip()


def _similar(query: str, name: str) -> float:
    q, n = _norm(query), _norm(name)
    whole = difflib.SequenceMatcher(None, q, n).ratio()
    # every typed word close to some word of the name ("drak maye" ~ "drake maye")
    words = [max((difflib.SequenceMatcher(None, w, x).ratio() for x in n.split()), default=0) for w in q.split()]
    return max(whole, sum(words) / len(words) if words else 0)


def search(query: str, http: CachedJSON | None = None, limit: int = 6) -> list[Player]:
    """Players matching ``query``, closest first. Copes with typos by also searching each word on its own."""
    query = query.strip()
    if len(query) < 2:
        return []
    http = http or CachedJSON()

    def run(q: str) -> list[Player]:
        for attempt in range(3):                  # ESPN's search answers 503 now and then: try again
            try:
                data = http.get(f"{COMMON}/search", params=[("query", q), ("type", "player"), ("limit", "15")],
                                ttl=6 * 3600)
                return [p for p in (_player(i) for i in data.get("items", [])) if p]
            except APIError:
                time.sleep(0.4 * (attempt + 1))
        return []

    found = run(query)
    best = max((_similar(query, p.name) for p in found), default=0)
    if best < 0.9:                              # probably a typo or a partial name: try each word too
        for w in sorted({w for w in _norm(query).split() if len(w) >= 3}, key=len, reverse=True):
            found += run(w)
    seen, ranked = set(), []
    for order, p in enumerate(found):
        if p.key in seen:
            continue
        seen.add(p.key)
        pro = 0.0 if "college" in p.league else 0.03
        ranked.append((_similar(query, p.name) + pro - order * 0.002, p))   # ESPN's own order breaks ties
    ranked.sort(key=lambda x: -x[0])
    top = ranked[0][0] if ranked else 0
    return [p for score, p in ranked if score >= max(0.55, top - 0.3)][:limit]


# ---------------------------------------------------------------- profile

@dataclass
class GameLine:
    id: str
    date: dt.datetime
    opponent: str
    opp_abbr: str
    at_vs: str                # "vs" or "@"
    result: str               # "W", "L", "D", "T" or ""
    score: str
    stats: dict[str, str]     # stat name -> shown value
    season_type: str = ""     # "Regular Season", "Postseason"...

    @property
    def matchup(self) -> str:
        return f"{self.at_vs} {self.opp_abbr or self.opponent}"


@dataclass
class Table:
    title: str
    columns: list[str]                     # short labels
    tips: list[str]                        # long names, same order
    rows: list[tuple[str, list[str]]]      # (row label, values)


@dataclass
class KeyStat:
    name: str
    label: str
    last: str | None = None          # last game
    season: str | None = None        # this season total
    per_game: str | None = None      # this season per game
    career: str | None = None        # career total (or per game, see career_note)
    career_note: str = ""


@dataclass
class LiveLine:
    status: str                      # "Q3 5:12", "Final"
    state: str                       # "in" or "post"
    score: str                       # "NE 17 - 14 BUF"
    stats: list[tuple[str, str, str]]   # (short label, long name, value)


@dataclass
class Profile:
    player: Player
    keys: list[KeyStat]
    games: list[GameLine]                   # this season, newest first
    game_columns: list[tuple[str, str, str]]   # (stat name, short label, long name)
    seasons: list[Table]
    splits: Table | None
    facts: list[str]
    next_game: str = ""
    news: str = ""
    news_more: str = ""
    live: LiveLine | None = None
    season_label: str = ""
    fantasy: dict = field(default_factory=dict)

    @property
    def last_game(self) -> GameLine | None:
        return self.games[0] if self.games else None


def _num(v) -> float | None:
    """'2,330' -> 2330; '12.0' -> 12; '70-156' -> 70 (made); '-' -> None."""
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if "-" in s[1:]:
        s = s.split("-")[0]
    try:
        return float(s)
    except ValueError:
        return None


def _value(names: list[str], values: list, key: str):
    """The value for ``key`` in a row, understanding ESPN's combined 'made-attempted' columns."""
    for i, n in enumerate(names):
        if i >= len(values):
            break
        if n == key:
            return values[i]
        parts = n.split("-")
        if len(parts) == 2 and key in parts:
            v = str(values[i])
            bits = v.split("-")
            return bits[parts.index(key)] if len(bits) == 2 else v
    return None


def _commas(v) -> str:
    """'43628' -> '43,628'; anything else as it is."""
    s = str(v)
    return f"{int(s):,}" if s.isdigit() else s


def fmt(x: float | None, decimals: int = 0) -> str:
    if x is None:
        return "-"
    if decimals == 0:
        return f"{x:,.0f}"
    return f"{x:,.{decimals}f}"


def _when(d: dt.datetime) -> str:
    return d.astimezone(EASTERN).strftime("%b %-d")


def _parse_games(log: dict) -> list[GameLine]:
    names = log.get("names") or []
    meta = log.get("events") or {}
    out: dict[str, GameLine] = {}
    for st in log.get("seasonTypes") or []:
        st_name = st.get("displayName", "")
        for cat in st.get("categories") or []:
            if cat.get("type") not in (None, "event"):
                continue
            label = f"{st_name} {cat.get('displayName', '')}"
            if "preseason" in label.lower():
                continue
            for ev in cat.get("events") or []:
                m = meta.get(str(ev.get("eventId"))) or {}
                if not m.get("gameDate"):
                    continue
                opp = m.get("opponent") or {}
                at_vs = "@" if m.get("atVs") == "@" else "vs"
                stats = {n: v for n, v in zip(names, ev.get("stats") or [])}
                out[str(ev["eventId"])] = GameLine(
                    id=str(ev["eventId"]), date=dt.datetime.fromisoformat(m["gameDate"].replace("Z", "+00:00")),
                    opponent=opp.get("displayName", ""), opp_abbr=opp.get("abbreviation", ""), at_vs=at_vs,
                    result=m.get("gameResult", "") or "", score=m.get("score", "") or "", stats=stats,
                    season_type="Postseason" if "post" in label.lower() else "Regular Season")
    return sorted(out.values(), key=lambda g: g.date, reverse=True)


def _season_tables(stats: dict) -> list[Table]:
    tables = []
    for c in stats.get("categories") or []:
        labels, names = c.get("labels") or [], c.get("names") or []
        tips = c.get("displayNames") or names
        rows = []
        for s in c.get("statistics") or []:
            year = (s.get("season") or {}).get("displayName", "")
            team = s.get("teamSlug", "").replace("-", " ").title()
            rows.append((f"{year} {('· ' + team) if team else ''}".strip(), s.get("stats") or []))
        if c.get("totals"):
            rows.append(("Career", c["totals"]))
        if rows:
            tables.append(Table((c.get("displayName") or c.get("name", "")).strip(), labels, tips, rows))
    return tables


def _career_value(stats: dict, overview: dict, key: str) -> tuple[str | None, str]:
    """Career total for ``key`` from the stats feed, else ESPN's career line (which may be per game)."""
    cats = stats.get("categories") or []
    order = sorted(cats, key=lambda c: 0 if c.get("name") in ("totals", "career-batting", "career-pitching") else 1)
    for c in order:
        if c.get("name") in ("averages", "postseason-batting", "postseason-pitching"):
            continue
        v = _value(c.get("names") or [], c.get("totals") or [], key)
        if v not in (None, "", "-"):
            return _commas(v), ""
    ov = overview.get("statistics") or {}
    career = next((s for s in ov.get("splits") or [] if s.get("displayName") == "Career"), None)
    if career:
        names = ov.get("names") or []
        v = _value(names, career.get("stats") or [], key)
        if v not in (None, "", "-"):
            return _commas(v), ""
        avg = "avg" + key[0].upper() + key[1:]
        v = _value(names, career.get("stats") or [], avg)
        if key == "totalRebounds" and v is None:
            v = _value(names, career.get("stats") or [], "avgRebounds")
        if v not in (None, "", "-"):
            return str(v), "per game"
    return None, ""


def _career_games(stats: dict, overview: dict) -> float | None:
    for c in stats.get("categories") or []:
        for k in ("gamesPlayed", "games"):
            v = _num(_value(c.get("names") or [], c.get("totals") or [], k))
            if v:
                return v
    ov = overview.get("statistics") or {}
    career = next((s for s in ov.get("splits") or [] if s.get("displayName") == "Career"), None)
    if career:
        for k in ("gamesPlayed", "games"):
            v = _num(_value(ov.get("names") or [], career.get("stats") or [], k))
            if v:
                return v
    return None


RATE_WORDS = ("Pct", "avg", "Avg", "per", "Rating", "QBR", "OPS", "ERA", "WHIP", "yardsPer", "production",
              "timeOnIce", "long", "plusMinus")


def _is_count(name: str) -> bool:
    return not any(w in name for w in RATE_WORDS)


def _key_stats(p: Player, games: list[GameLine], names: list[str], stats: dict, overview: dict,
               labels: dict[str, str]) -> list[KeyStat]:
    season_games = [g for g in games if g.season_type == "Regular Season"] or games
    flat = set()
    for n in names:
        flat.update(n.split("-") if n.count("-") == 1 else [n])
    picks = []
    for key in KEY_STATS.get(p.sport, []):
        if key not in flat:
            continue
        total = sum(_num(_value(list(g.stats), list(g.stats.values()), key)) or 0 for g in season_games)
        career, note = _career_value(stats, overview, key)
        if total == 0 and not (_num(career) or 0):
            continue
        picks.append((key, total, career, note))
        if len(picks) == 4:
            break
    if not picks:                                     # a position we don't list: take its first counting stats
        for key in [n for n in flat if _is_count(n)][:4]:
            total = sum(_num(_value(list(g.stats), list(g.stats.values()), key)) or 0 for g in season_games)
            career, note = _career_value(stats, overview, key)
            picks.append((key, total, career, note))
    out = []
    n = len(season_games)
    for key, total, career, note in picks:
        last = games[0] if games else None
        lv = _value(list(last.stats), list(last.stats.values()), key) if last else None
        per = total / n if n else None
        out.append(KeyStat(key, labels.get(key, key), last=lv if lv not in (None, "") else None,
                           season=fmt(total) if n else None,
                           per_game=fmt(per, 1) if per is not None else None,
                           career=career, career_note=note))
    return out


def _labels(*feeds: dict) -> dict[str, str]:
    """Stat name -> plain long name ("passingYards" -> "Passing Yards")."""
    out = {}
    for f in feeds:
        for c in [f] + list(f.get("categories") or []):
            names, longs = c.get("names") or [], c.get("displayNames") or []
            for n, l in zip(names, longs):
                parts, lparts = n.split("-"), l.split("-")
                if len(parts) == 2 and len(lparts) == 2:
                    out.setdefault(parts[0], lparts[0].strip())
                    out.setdefault(parts[1], lparts[1].strip())
                out.setdefault(n, l)
    out.update({"totalRebounds": "Rebounds", "threePointFieldGoalsMade": "3-Pointers Made", "totalGoals": "Goals",
                "goalAssists": "Assists", "RBIs": "RBIs", "shotsTotal": "Shots"})
    return out


def _short_labels(log: dict) -> list[tuple[str, str, str]]:
    names, labels = log.get("names") or [], log.get("labels") or []
    longs = log.get("displayNames") or names
    return list(zip(names, labels, longs))


# ---------------------------------------------------------------- fun facts

def _milestone(total: float) -> float | None:
    """The next round number a career total is closing in on (within 12%)."""
    if total < 50:
        return None
    step = 10 ** math.floor(math.log10(total))
    for m in (step * k for k in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 7.5, 8, 9, 10)):
        if m > total:
            return m if (m - total) / m <= 0.12 else None
    return None


def fun_facts(p: Player, keys: list[KeyStat], games: list[GameLine], overview: dict, stats: dict,
              labels: dict[str, str], older: list[GameLine]) -> list[str]:
    facts: list[str] = []
    who = p.name.split()[-1] if p.name else "He"
    season = [g for g in games if g.season_type == "Regular Season"] or games
    if not season:
        return facts

    def val(g: GameLine, k: str) -> float | None:
        return _num(_value(list(g.stats), list(g.stats.values()), k))

    main = keys[0] if keys else None
    if main:
        lbl = main.label.lower()
        # best game this season, and in the last two seasons
        best = max(season, key=lambda g: val(g, main.name) or -1)
        bv = val(best, main.name)
        if bv:
            facts.append(f"Season high: **{fmt(bv)} {lbl}** {best.matchup} on {_when(best.date)}"
                         + (f" ({'won' if best.result == 'W' else 'lost' if best.result == 'L' else 'drew'} "
                            f"{best.score})" if best.result in ("W", "L", "D") and best.score else "") + ".")
        both = season + older
        top = max(both, key=lambda g: val(g, main.name) or -1)
        tv = val(top, main.name)
        if older and tv and tv > (bv or 0):
            facts.append(f"Best game since {min(g.date for g in both).year}: {fmt(tv)} {lbl} {top.matchup} "
                         f"({_when(top.date)}, {top.date.year}).")
        # this season vs career average
        cg = _career_games(stats, overview)
        cv = _num(main.career)
        if main.per_game and cv and cg and not main.career_note and cg > len(season) + 3:
            career_avg = cv / cg
            now = _num(main.per_game) or 0
            if career_avg > 0:
                diff = (now - career_avg) / career_avg
                if abs(diff) >= 0.08:
                    facts.append(f"Averaging **{fmt(now, 1)} {lbl} per game** this season, "
                                 f"{abs(diff) * 100:.0f}% {'above' if diff > 0 else 'below'} {who}'s career "
                                 f"average ({fmt(career_avg, 1)}).")
        # wins vs losses
        won = [val(g, main.name) or 0 for g in season if g.result == "W"]
        lost = [val(g, main.name) or 0 for g in season if g.result == "L"]
        if len(won) >= 2 and len(lost) >= 2:
            aw, al = sum(won) / len(won), sum(lost) / len(lost)
            if max(aw, al) > 0 and abs(aw - al) / max(aw, al) >= 0.15:
                facts.append(f"{fmt(aw, 1)} {lbl} per game in wins vs {fmt(al, 1)} in losses.")
        # home vs away
        home = [val(g, main.name) or 0 for g in season if g.at_vs == "vs"]
        away = [val(g, main.name) or 0 for g in season if g.at_vs == "@"]
        if len(home) >= 2 and len(away) >= 2:
            ah, aa = sum(home) / len(home), sum(away) / len(away)
            if max(ah, aa) > 0 and abs(ah - aa) / max(ah, aa) >= 0.2:
                facts.append(f"Much better {'at home' if ah > aa else 'on the road'}: {fmt(max(ah, aa), 1)} {lbl} "
                             f"per game there vs {fmt(min(ah, aa), 1)} {'away' if ah > aa else 'at home'}.")
    # streaks: "a touchdown pass in 6 straight games", "20+ points in 5 straight"
    for k in [k for k in STREAK_STATS if any(val(g, k) is not None for g in season)][:3]:
        vals = [val(g, k) or 0 for g in season]
        avg = sum(vals) / len(vals)
        bar = 1 if avg < 4 else max(5, int(avg // 5) * 5)
        run = 0
        for v in vals:
            if v >= bar:
                run += 1
            else:
                break
        name = labels.get(k, k).lower()
        if run >= 3:
            facts.append(f"🔥 {'At least one' if bar == 1 else f'{bar}+'} {name if bar > 1 else name.rstrip('s')} "
                         f"in **{run} straight games**.")
            break
        if bar == 1 and len(vals) >= 5 and run == 0:
            dry = next((i for i, v in enumerate(vals) if v >= 1), len(vals))
            if dry >= 4:
                facts.append(f"No {name.rstrip('s').lower()} in the last {dry} games.")
                break
    # team record in his games
    w = sum(g.result == "W" for g in season)
    l_ = sum(g.result == "L" for g in season)
    d = sum(g.result in ("D", "T") for g in season)
    if w + l_ >= 3:
        rec = f"{w}-{l_}{f'-{d}' if d else ''}"
        team = p.team if p.team and "National Team" not in p.team and p.sport != "soccer" else ""
        facts.append(f"The {team} are {rec} in games {who} has played this season." if team else
                     f"Team record in games {who} has played this season: {rec}.")
    # on pace and milestones
    ov = overview.get("statistics") or {}
    proj = next((s for s in ov.get("splits") or [] if s.get("displayName") == "Projected"), None)
    for k in keys[:2]:
        if proj:
            v = _num(_value(ov.get("names") or [], proj.get("stats") or [], k.name))
            if v and v > (_num(k.season) or 0):
                facts.append(f"On pace for **{fmt(v)} {k.label.lower()}** this season.")
                break
    for k in keys:
        cv = _num(k.career)
        if cv and not k.career_note:
            m = _milestone(cv)
            if m:
                facts.append(f"🎯 {fmt(m - cv)} {k.label.lower()} away from **{fmt(m)} career {k.label.lower()}**.")
                break
    return facts


# ---------------------------------------------------------------- live game

def live_line(p: Player, http: CachedJSON) -> LiveLine | None:
    """The player's line in a game being played right now (or that finished in the last few hours)."""
    if not p.team_id or p.sport == "soccer":
        return None
    path = f"{p.sport}/{p.league}"
    try:
        board = http.get(f"{SITE}/{path}/scoreboard", ttl=20)
    except APIError:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    for ev in board.get("events") or []:
        comp = (ev.get("competitions") or [{}])[0]
        teams = comp.get("competitors") or []
        if p.team_id not in {str((c.get("team") or {}).get("id")) for c in teams}:
            continue
        state = ((ev.get("status") or {}).get("type") or {}).get("state")
        start = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
        if state == "pre" or (state == "post" and now - start > dt.timedelta(hours=10)):
            return None
        try:
            summ = http.get(f"{SITE}/{path}/summary", params=[("event", ev["id"])], ttl=20)
        except APIError:
            return None
        lines = []
        for team in (summ.get("boxscore") or {}).get("players") or []:
            for cat in team.get("statistics") or []:
                for a in cat.get("athletes") or []:
                    if str((a.get("athlete") or {}).get("id")) == p.id:
                        labels = cat.get("labels") or []
                        longs = cat.get("descriptions") or cat.get("names") or labels
                        for lab, lng, v in zip(labels, longs, a.get("stats") or []):
                            lines.append((lab, str(lng), str(v)))
        side = sorted(teams, key=lambda c: c.get("homeAway") != "away")
        score = " - ".join(f"{(c.get('team') or {}).get('abbreviation', '')} {c.get('score', '')}" for c in side)
        status = ((ev.get("status") or {}).get("type") or {}).get("shortDetail", "")
        return LiveLine(status=status, state=state, score=score, stats=lines)
    return None


# ---------------------------------------------------------------- everything for one player

def profile(p: Player, http: CachedJSON | None = None) -> Profile:
    http = http or CachedJSON()
    base = f"{COMMON}/sports/{p.sport}/{p.league}/athletes/{p.id}"

    def get(url: str, ttl: float, params=None) -> dict:
        try:
            return http.get(url, params=params, ttl=ttl) or {}
        except APIError:
            return {}

    with ThreadPoolExecutor(4) as pool:
        f_over = pool.submit(get, f"{base}/overview", 300)
        f_stats = pool.submit(get, f"{base}/stats", 3600)
        f_log = pool.submit(get, f"{base}/gamelog", 300)
        f_live = pool.submit(live_line, p, http)
        overview, stats, log, live = f_over.result(), f_stats.result(), f_log.result(), f_live.result()
    games = _parse_games(log)
    # last season's games too, for "best game since..." facts
    older: list[GameLine] = []
    seasons = [o.get("value") for f in log.get("filters") or [] if f.get("name") == "season"
               for o in f.get("options") or []]
    if len(seasons) >= 2:
        older = _parse_games(get(f"{base}/gamelog", 6 * 3600, params=[("season", seasons[1])]))
    labels = _labels(log, stats, overview.get("statistics") or {})
    keys = _key_stats(p, games, log.get("names") or [], stats, overview, labels)
    ov = overview.get("statistics") or {}
    splits = None
    if ov.get("splits"):
        splits = Table(ov.get("displayName", "Summary"), ov.get("labels") or [], ov.get("displayNames") or [],
                       [(s.get("displayName", ""), s.get("stats") or []) for s in ov["splits"]])
    nxt = ""
    for ev in ((overview.get("nextGame") or {}).get("league") or {}).get("events") or []:
        when = dt.datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(EASTERN)
        if when < dt.datetime.now(EASTERN) - dt.timedelta(hours=4):
            continue
        nxt = f"{ev.get('shortName') or ev.get('name', '')}, {when.strftime('%a %b %-d, %-I:%M %p ET')}"
        break
    rw = overview.get("rotowire") or {}
    types = [st.get("displayName", "") for st in log.get("seasonTypes") or []]
    season_label = next((x for x in types if "regular" in x.lower()), types[0] if types else "")
    return Profile(
        player=p, keys=keys, games=games, game_columns=_short_labels(log), seasons=_season_tables(stats),
        splits=splits, facts=fun_facts(p, keys, games, overview, stats, labels, older), next_game=nxt,
        news=rw.get("headline", ""), news_more=rw.get("story", ""), live=live, season_label=season_label,
        fantasy={k: v for k, v in (overview.get("fantasy") or {}).items() if k in ("percentOwned", "positionRank")})
