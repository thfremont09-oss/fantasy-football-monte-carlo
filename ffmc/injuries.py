"""Injuries and rest: how much a team is weakened for its next game.

ESPN publishes an injury report for the NBA, WNBA, NFL and NHL. For every player listed as Out, Doubtful,
Questionable or Day-To-Day we estimate what the player is worth to the team per game, from season stats,
and multiply by the chance they sit:

* Basketball: points + half the rebounds + most of the assists, above what a bench replacement gives.
  A star scoring 30 a night is worth about 4-5 points of margin; a role player about 1.
* NFL: a starting quarterback is worth about 5-6 points; a lead back or top receiver up to 2, by yards.
  Linemen and defenders aren't valued (box scores say too little about them).
* Hockey: skaters by points per game (a star is worth about a quarter of a goal); a starting goalie about
  a quarter of a goal.

Each value is scaled by how much of the season the player has actually played, because a long absence is
already in the team's results (and players on injured reserve are left out for the same reason).

Rest: a team playing the second night of a back-to-back loses about 1.5 points (NBA), 1 point (WNBA) or a
tenth of a goal (NHL).
"""

from __future__ import annotations

import datetime as dt
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .http import APIError, CachedJSON

PATHS = {"NBA": "basketball/nba", "WNBA": "basketball/wnba", "NFL": "football/nfl", "NHL": "hockey/nhl"}
CHANCE_OUT = {"Out": 1.0, "Suspension": 1.0, "Doubtful": 0.75, "Questionable": 0.4, "Day-To-Day": 0.4,
              "Probable": 0.1}
BACK_TO_BACK = {"NBA": 1.5, "WNBA": 1.0, "NHL": 0.1}
REFRESH = 30 * 60
COMMON = "https://site.api.espn.com/apis/common/v3/sports"


@dataclass
class Missing:
    name: str
    position: str
    status: str
    chance_out: float
    value: float                 # points (goals) of margin the player is worth per game when playing
    note: str = ""

    @property
    def expected(self) -> float:
        return self.value * self.chance_out


@dataclass
class Report:
    league: str
    teams: dict[str, list[Missing]] = field(default_factory=dict)     # team display name -> listed players
    fetched: float = 0.0

    def cost(self, team: str) -> float:
        """Expected points (goals) of margin the team loses to injuries."""
        return sum(m.expected for m in self.teams.get(team, []))


def _athlete_id(a: dict) -> str | None:
    for link in a.get("links") or []:
        m = re.search(r"/id/(\d+)", link.get("href", ""))
        if m:
            return m.group(1)
    m = re.search(r"/full/(\d+)\.png", (a.get("headshot") or {}).get("href", ""))
    return m.group(1) if m else None


def _num(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _season_line(http: CachedJSON, path: str, pid: str) -> dict[str, float]:
    """The player's 'Regular Season' line from ESPN's athlete overview, by stat name."""
    try:
        o = http.get(f"{COMMON}/{path}/athletes/{pid}/overview", ttl=12 * 3600).get("statistics") or {}
    except APIError:
        return {}
    split = next((s for s in o.get("splits") or [] if s.get("displayName") == "Regular Season"), None)
    if not split:
        return {}
    return {n: _num(v) for n, v in zip(o.get("names") or [], split.get("stats") or [])}


def player_value(league: str, position: str, line: dict[str, float], team_games: int) -> float:
    """What the player is worth per game to the team's margin (points, or goals in hockey)."""
    if not line:
        return 0.0
    tg = max(team_games, 1)
    if league in ("NBA", "WNBA"):
        gp = line.get("gamesPlayed", 0)
        box = line.get("avgPoints", 0) + 0.5 * line.get("avgRebounds", 0) + 0.8 * line.get("avgAssists", 0)
        return 0.15 * max(0.0, box - 8) * min(1.0, gp / tg)
    if league == "NFL":
        if position == "QB":
            ypg = line.get("passingYards", 0) / tg
            return 5.5 * min(1.0, ypg / 220) if ypg >= 120 else 0.0
        if position in ("RB", "WR", "TE"):
            ypg = (line.get("rushingYards", 0) + line.get("receivingYards", 0)) / tg
            return min(2.0, max(0.0, 0.025 * (ypg - 30)))
        return 0.0
    if league == "NHL":
        if position == "G":
            starts = line.get("gameStarted", line.get("games", 0))
            return 0.25 if starts / tg >= 0.5 else 0.05
        games = line.get("games", 0)
        if not games:
            return 0.0
        return 0.25 * max(0.0, line.get("points", 0) / games - 0.3) * min(1.0, games / tg)
    return 0.0


_CACHE: dict[str, Report] = {}
_LOCK = threading.Lock()


def report(league: str, team_games=None, http: CachedJSON | None = None) -> Report | None:
    """This league's injury report, valued, refreshed every 30 minutes. None if ESPN has none for it."""
    path = PATHS.get(league)
    if not path:
        return None
    with _LOCK:
        cached = _CACHE.get(league)
    if cached and time.time() - cached.fetched < REFRESH:
        return cached
    from .mem import heavy
    http = http or CachedJSON()
    try:
        with heavy():                                        # the NFL report alone is ~9 MB of JSON
            data = http.get(f"https://site.api.espn.com/apis/site/v2/sports/{path}/injuries", ttl=REFRESH)
            listed = []
            for t in data.get("injuries") or []:
                for x in t.get("injuries") or []:
                    status = x.get("status", "")
                    if status not in CHANCE_OUT:             # Active, Injured Reserve (already in results)...
                        continue
                    a = x.get("athlete") or {}
                    listed.append((t.get("displayName", ""), a.get("displayName", ""),
                                   (a.get("position") or {}).get("abbreviation", ""), status,
                                   x.get("shortComment", ""), _athlete_id(a)))
            del data
    except APIError:
        return cached

    def value(item):
        team, name, pos, status, note, pid = item
        line = _season_line(http, path, pid) if pid else {}
        games = team_games(team) if team_games else 0
        return team, Missing(name, pos, status, CHANCE_OUT[status], player_value(league, pos, line, games), note)

    with ThreadPoolExecutor(6) as pool:
        valued = list(pool.map(value, listed))
    rep = Report(league, fetched=time.time())
    for team, m in valued:
        rep.teams.setdefault(team, []).append(m)
    for ms in rep.teams.values():
        ms.sort(key=lambda m: -m.expected)
    with _LOCK:
        _CACHE[league] = rep
    return rep


def back_to_back(league: str, team: str, game_day: dt.date, results: list[tuple]) -> bool:
    """Did the team also play the day before this game?"""
    if league not in BACK_TO_BACK:
        return False
    yesterday = game_day - dt.timedelta(days=1)
    return any(g[0] == yesterday and team in (g[1], g[2]) for g in results)


@dataclass
class Situation:
    """Injuries and rest for one game, from the home side's point of view."""
    home_adj: float                       # points (goals) added to the home margin
    home_out: list[Missing]
    away_out: list[Missing]
    home_b2b: bool
    away_b2b: bool
    has_report: bool


def situation(g, r) -> Situation | None:
    """Injury and rest adjustment for an upcoming game (None for past games, or leagues without either)."""
    league = g.league
    if league not in PATHS and league not in BACK_TO_BACK:
        return None
    start = getattr(g, "start", None)
    now = dt.datetime.now(dt.timezone.utc)
    if start is None or start < now - dt.timedelta(hours=4) or start > now + dt.timedelta(days=4):
        return None                           # replays of old games don't get today's injury report
    away, home = g.sides[0].name, g.sides[1].name

    def team_games(team: str) -> int:
        n = (r.notes or {}).get(team) if r else None
        return (n.wins + n.losses + n.draws) if n else 0

    rep = report(league, team_games)
    from . import ratings
    from .live import EASTERN
    day = start.astimezone(EASTERN).date()
    results = ratings.results(league, day) if league in BACK_TO_BACK else []
    hb, ab = back_to_back(league, home, day, results), back_to_back(league, away, day, results)
    rest = BACK_TO_BACK.get(league, 0.0)
    adj = (rep.cost(away) - rep.cost(home) if rep else 0.0) - (rest if hb else 0.0) + (rest if ab else 0.0)
    return Situation(adj, rep.teams.get(home, []) if rep else [], rep.teams.get(away, []) if rep else [], hb, ab,
                     rep is not None)
