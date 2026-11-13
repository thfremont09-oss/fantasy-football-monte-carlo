"""Plain-English matchup info for one player: who he plays, who's guarding him, and how
that defense has done against his position this season."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .espn_ff import ACTUAL, ESPNFantasy, POSITIONS, _weekly
from .http import APIError

DEPTH = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{id}/depthcharts"

# Which spots on the opponent's depth chart matter for each position (first match wins per group).
GUARDS = {
    "WR": ("Who's guarding: cornerbacks", [["lcb"], ["rcb"], ["nb"]]),
    "TE": ("Who's guarding: safeties and linebackers", [["ss"], ["fs"], ["wlb", "mlb", "lilb", "rilb", "slb"]]),
    "RB": ("Who's in the way: run defenders", [["mlb", "lilb", "rilb"], ["wlb", "slb"], ["ldt", "nt", "rdt"]]),
    "QB": ("Who's rushing the passer", [["lde", "lolb"], ["rde", "rolb"], ["ldt", "nt", "rdt"]]),
    "DEF": ("Offense it's up against", [["qb"], ["rb"], ["wr1"]]),
}


@dataclass
class Matchup:
    opponent: str = ""                 # full team name, e.g. "Atlanta Falcons"
    opp_abbrev: str = ""
    home: bool | None = None
    kickoff: dt.datetime | None = None
    guard_label: str = ""
    guards: list[tuple[str, str]] = field(default_factory=list)   # (role, name)
    allowed_avg: float | None = None   # fantasy points per game this defense allows to his position
    allowed_rank: int | None = None    # 1 = gives up the most
    n_teams: int = 0
    outlook: str = ""                  # ESPN's write-up for this week


def _depth(api: ESPNFantasy, team_id: int) -> dict[str, tuple[str, str]]:
    """Depth-chart spot -> (position name, starter) for one NFL team."""
    try:
        data = api.http.get(DEPTH.format(id=team_id), ttl=86400)
    except APIError:
        return {}
    out: dict[str, tuple[str, str]] = {}
    for chart in data.get("depthchart") or []:
        for key, spot in (chart.get("positions") or {}).items():
            athletes = spot.get("athletes") or []
            if athletes and key not in out:
                out[key] = ((spot.get("position") or {}).get("displayName", key.upper()),
                            athletes[0].get("displayName", ""))
    return out


def allowed_by_position(pool: list[dict], schedule: dict[int, dict], season: int,
                        week: int) -> dict[tuple[int, str], float]:
    """Average fantasy points per game each defense has given up to each position before ``week``."""
    opp_by_week: dict[tuple[int, int], int] = {}
    for tid, t in schedule.items():
        for w, games in (t.get("proGamesByScoringPeriod") or {}).items():
            for g in games:
                opp_by_week[(tid, int(w))] = g["awayProTeamId"] if g["homeProTeamId"] == tid else g["homeProTeamId"]
    totals: dict[tuple[int, str, int], float] = {}
    for p in pool:
        pos = POSITIONS.get(p.get("defaultPositionId"))
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        for w, pts in _weekly(p, season, ACTUAL).items():
            opp = opp_by_week.get((p.get("proTeamId"), w))
            if opp is not None and 0 < w < week:
                totals[(opp, pos, w)] = totals.get((opp, pos, w), 0.0) + pts
    per_game: dict[tuple[int, str], list[float]] = {}
    for (opp, pos, _), pts in totals.items():
        per_game.setdefault((opp, pos), []).append(pts)
    return {k: sum(v) / len(v) for k, v in per_game.items()}


def rank_of(allowed: dict[tuple[int, str], float], team_id: int, pos: str) -> tuple[float | None, int | None, int]:
    vals = sorted(((v, t) for (t, p), v in allowed.items() if p == pos), reverse=True)
    for i, (v, t) in enumerate(vals):
        if t == team_id:
            return v, i + 1, len(vals)
    return None, None, len(vals)


def matchup(api: ESPNFantasy, player_id: str, position: str, team: str | None, week: int) -> Matchup:
    m = Matchup()
    schedule = api.pro_schedule()
    by_abbrev = {t.get("abbrev"): tid for tid, t in schedule.items()}
    tid = by_abbrev.get(team)
    if tid is None:
        return m
    games = (schedule[tid].get("proGamesByScoringPeriod") or {}).get(str(week)) or []
    if not games:
        return m
    g = games[0]
    opp = g["awayProTeamId"] if g["homeProTeamId"] == tid else g["homeProTeamId"]
    o = schedule.get(opp, {})
    m.opponent = f"{o.get('location', '')} {o.get('name', '')}".strip()
    m.opp_abbrev = o.get("abbrev", "")
    m.home = g["homeProTeamId"] == tid
    if g.get("date"):
        m.kickoff = dt.datetime.fromtimestamp(g["date"] / 1000, dt.timezone.utc)

    if position in GUARDS:
        m.guard_label, groups = GUARDS[position]
        chart = _depth(api, opp)
        for keys in groups:
            hit = next((chart[k] for k in keys if k in chart), None)
            if hit and hit[1] not in {n for _, n in m.guards}:
                m.guards.append(hit)

    if position in ("QB", "RB", "WR", "TE"):
        try:
            pool = api.players(week, rules=3)
            m.allowed_avg, m.allowed_rank, m.n_teams = rank_of(
                allowed_by_position(pool, schedule, api.season, week), opp, position)
        except APIError:
            pass

    if player_id.isdigit():
        try:
            info = api.players(week, ids=[int(player_id)])
            if info:
                m.outlook = ((info[0].get("outlooks") or {}).get("outlooksByWeek") or {}).get(str(week), "")
        except APIError:
            pass
    return m


def verdict(rank: int | None, n: int) -> str:
    if not rank or not n:
        return ""
    if rank <= max(1, round(n * 0.25)):
        return "a good matchup"
    if rank > n - round(n * 0.25):
        return "a tough matchup"
    return "an average matchup"


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
