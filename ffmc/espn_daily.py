"""ESPN fantasy basketball and hockey: daily lineups and this week's head-to-head win chance.

These games score every day (a "scoring period" is one day) and a matchup is a week, so:

* **Today's lineup**: of your players with a game that day, the best one for every slot, filled exactly
  (players can be eligible for several slots, e.g. PG, G and UTIL).
* **This week**: for every remaining day we start the best lineup of whoever plays that day, add up the
  games each player gets, and simulate the rest of the week 1,000,000 times for you and your opponent,
  on top of the points already scored.

Per-game points blend ESPN's projection with each player's last 15 days and season average; the spread
comes from their own game log. Points leagues use the league's scoring; category leagues are valued with
ESPN's standard points scoring as a stand-in (there's no single number to add up in categories).
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import numpy as np

from .http import APIError, CachedJSON

ET = ZoneInfo("America/New_York")
API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/{game}/seasons/{season}"
POINTS_RULES = 2                     # ESPN's default head-to-head points league


@dataclass(frozen=True)
class Sport:
    key: str
    game: str
    name: str
    positions: dict
    slots: dict                       # ESPN lineup slot id -> name
    bench: frozenset
    cv: dict                          # typical game-to-game spread, as a share of the average
    floor: dict                       # lowest realistic score in one game
    headshot: str                     # ESPN CDN folder

    def season(self, today: dt.date | None = None) -> int:
        """ESPN names these seasons by the year they end (2026-27 is 2027)."""
        today = today or dt.datetime.now(ET).date()
        return today.year + 1 if today.month >= 8 else today.year


NBA = Sport("nba", "fba", "NBA", {1: "PG", 2: "SG", 3: "SF", 4: "PF", 5: "C"},
            {0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C", 5: "G", 6: "F", 7: "SG/SF", 8: "G/F", 9: "PF/C",
             10: "F/C", 11: "UTIL"}, frozenset({12, 13, 14}), {"*": 0.32}, {"*": 0.0}, "nba")
NHL = Sport("nhl", "fhl", "NHL", {1: "C", 2: "LW", 3: "RW", 4: "D", 5: "G"},
            {0: "C", 1: "LW", 2: "RW", 3: "F", 4: "D", 5: "G", 6: "UTIL"}, frozenset({7, 8, 9}),
            {"G": 1.0, "*": 0.9}, {"G": -6.0, "*": -1.0}, "nhl")
SPORTS = {"nba": NBA, "nhl": NHL}

PLAY = {None: 1.0, "ACTIVE": 1.0, "NORMAL": 1.0, "PROBABLE": 0.9, "DAY_TO_DAY": 0.6, "QUESTIONABLE": 0.5,
        "DOUBTFUL": 0.2, "OUT": 0.0, "INJURY_RESERVE": 0.0, "SUSPENSION": 0.0}
STATUS = {"DAY_TO_DAY": "Day-to-day", "QUESTIONABLE": "Questionable", "DOUBTFUL": "Doubtful", "OUT": "Out",
          "INJURY_RESERVE": "IR", "SUSPENSION": "Suspended", "PROBABLE": "Probable"}


@dataclass
class DPlayer:
    id: str
    name: str
    position: str
    team: str
    team_id: int
    eligible: frozenset            # lineup slot names this player can fill
    avg: float                     # expected fantasy points in one game, if he plays
    sd: float
    p_play: float = 1.0
    status: str = ""
    season_avg: float | None = None
    recent_avg: float | None = None
    proj_avg: float | None = None
    games_played: int = 0
    tags: set = field(default_factory=set)

    @property
    def value(self) -> float:
        return self.avg * self.p_play


@dataclass
class Day:
    period: int
    date: dt.date
    games: dict                    # team id -> (opponent abbrev, home?)


@dataclass
class Team:
    id: int
    name: str
    owner: str = ""


@dataclass
class Board:
    """Everything one page needs: players, slots, the week's days, and (in a league) the two rosters."""
    sport: Sport
    season: int
    today: int                     # today's scoring period
    days: list[Day]                # today through the end of this matchup week
    slots: list[str]
    players: list[DPlayer]
    scoring: str
    my_ids: set = field(default_factory=set)
    opp_ids: set = field(default_factory=set)
    my_name: str = "Your team"
    opp_name: str | None = None
    my_score: float = 0.0          # points already scored this week
    opp_score: float = 0.0
    points_league: bool = True
    notes: list[str] = field(default_factory=list)

    def by_id(self) -> dict[str, DPlayer]:
        return {p.id: p for p in self.players}


# ---------------------------------------------------------------- ESPN client

class DailyFantasy:
    def __init__(self, sport: Sport, season: int | None = None, cache_dir=".ffmc_cache", espn_s2: str = "",
                 swid: str = ""):
        self.sport = sport
        self.season = season or sport.season()
        self.http = CachedJSON(cache_dir)
        swid = swid.strip()
        if swid and not swid.startswith("{"):
            swid = "{" + swid.strip("{}") + "}"
        self.cookies = {"espn_s2": espn_s2.strip(), "SWID": swid} if espn_s2.strip() and swid else None

    def _get(self, path="", params=None, filt=None, ttl=900):
        headers = {"X-Fantasy-Filter": json.dumps(filt)} if filt else None
        return self.http.get(API.format(game=self.sport.game, season=self.season) + path, params, ttl=ttl,
                             headers=headers, cookies=self.cookies)

    def defaults(self) -> dict:
        return self._get(f"/segments/0/leaguedefaults/{POINTS_RULES}", [("view", "mSettings")], ttl=1800)

    def today(self) -> int:
        return int(self.defaults()["scoringPeriodId"])

    def pro_schedule(self) -> dict[int, dict]:
        teams = self._get("", [("view", "proTeamSchedules_wl")], ttl=6 * 3600)["settings"]["proTeams"]
        return {t["id"]: t for t in teams}

    def players(self, period: int, *, league_id: str | None = None, ids: list[int] | None = None,
                limit: int = 400) -> list[dict]:
        base = f"/segments/0/leagues/{league_id}" if league_id else f"/segments/0/leaguedefaults/{POINTS_RULES}"
        filt = {"players": {"filterIds": {"value": ids}}} if ids else {"players": {
            "limit": limit, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
        data = self._get(base, [("scoringPeriodId", str(period)), ("view", "kona_player_info")], filt, ttl=1800)
        return [e["player"] for e in data.get("players", [])]

    def league(self, league_id: str, period: int) -> dict:
        try:
            return self._get(f"/segments/0/leagues/{league_id}",
                             [("scoringPeriodId", str(period)), ("view", "mSettings"), ("view", "mTeam"),
                              ("view", "mRoster"), ("view", "mMatchupScore"), ("view", "mMatchup")], ttl=120)
        except APIError as exc:
            msg = str(exc)
            if "NOT_VISIBLE" in msg or "401" in msg:
                raise APIError("This ESPN league is private. Add your espn_s2 and SWID cookies "
                               "(see 'How do I find these?') and try again.") from exc
            if "404" in msg or "NOT_FOUND" in msg:
                raise APIError(f"No ESPN fantasy {self.sport.name} league with ID {league_id} this season.") from exc
            raise


# ---------------------------------------------------------------- conversion

def week_days(schedule: dict[int, dict], today: int, today_date: dt.date | None = None) -> list[Day]:
    """Today's scoring period through Sunday (fantasy weeks run Monday to Sunday)."""
    by_period: dict[int, dict] = {}
    dates: dict[int, dt.date] = {}
    abbrev = {tid: t.get("abbrev", "") for tid, t in schedule.items()}
    for tid, t in schedule.items():
        for per, games in (t.get("proGamesByScoringPeriod") or {}).items():
            per = int(per)
            for g in games:
                opp = g["awayProTeamId"] if g["homeProTeamId"] == tid else g["homeProTeamId"]
                by_period.setdefault(per, {})[tid] = (abbrev.get(opp, ""), g["homeProTeamId"] == tid)
                when = dt.datetime.fromtimestamp(g["date"] / 1000, ET).date()
                dates[per] = min(dates.get(per, when), when)
    start = today_date or dates.get(today) or dt.datetime.now(ET).date()
    sunday = start + dt.timedelta(days=6 - start.weekday())
    out = []
    for i in range((sunday - start).days + 1):
        per = today + i
        out.append(Day(per, start + dt.timedelta(days=i), by_period.get(per, {})))
    return out


def _stat(p: dict, season: int, source: int, split: int):
    for s in p.get("stats") or []:
        if s.get("seasonId") == season and s.get("statSourceId") == source and s.get("statSplitTypeId") == split:
            return s
    return None


def to_player(p: dict, sport: Sport, season: int, abbrev: dict[int, str]) -> DPlayer | None:
    pos = sport.positions.get(p.get("defaultPositionId"))
    if pos is None:
        return None
    elig = frozenset(sport.slots[s] for s in p.get("eligibleSlots") or [] if s in sport.slots)
    seas = _stat(p, season, 0, 0)
    recent = _stat(p, season, 0, 2)                  # last 15 days
    proj = _stat(p, season, 1, 0)
    season_avg = (seas or {}).get("appliedAverage")
    recent_avg = (recent or {}).get("appliedAverage")
    proj_avg = (proj or {}).get("appliedAverage")
    parts = [(proj_avg, 0.45), (recent_avg, 0.30), (season_avg, 0.25)]
    have = [(v, w) for v, w in parts if v is not None]
    avg = sum(v * w for v, w in have) / sum(w for _, w in have) if have else 0.0
    games = [float(s.get("appliedTotal") or 0) for s in p.get("stats") or []
             if s.get("seasonId") == season and s.get("statSourceId") == 0 and s.get("statSplitTypeId") == 5
             and s.get("stats")]
    cv = sport.cv.get(pos, sport.cv["*"])
    prior = cv * max(avg, 1.0)
    if len(games) >= 3:
        n = len(games)
        sd = math.sqrt((n * float(np.var(games, ddof=1)) + 4 * prior ** 2) / (n + 4))
    else:
        sd = prior
    status = p.get("injuryStatus") or "ACTIVE"
    return DPlayer(
        id=str(p["id"]), name=p.get("fullName", str(p["id"])), position=pos,
        team=abbrev.get(p.get("proTeamId"), "FA"), team_id=p.get("proTeamId") or 0, eligible=elig,
        avg=max(avg, 0.0), sd=sd, p_play=PLAY.get(status, 1.0), status=STATUS.get(status, ""),
        season_avg=season_avg, recent_avg=recent_avg, proj_avg=proj_avg, games_played=len(games))


def to_players(raw: list[dict], sport: Sport, season: int, schedule: dict[int, dict]) -> list[DPlayer]:
    abbrev = {tid: t.get("abbrev", "") for tid, t in schedule.items()}
    out = [p for p in (to_player(x, sport, season, abbrev) for x in raw) if p]
    # Goalies split their team's games: count only the share they've started (the busiest player on the
    # team shows how many games it has played).
    team_games: dict[int, int] = {}
    for p in out:
        team_games[p.team_id] = max(team_games.get(p.team_id, 0), p.games_played)
    for p in out:
        if p.position == "G" and team_games.get(p.team_id, 0) >= 4:
            p.p_play *= min(1.0, p.games_played / team_games[p.team_id])
    return out


def slot_list(counts: dict, sport: Sport) -> list[str]:
    return [sport.slots[int(k)] for k, n in sorted(counts.items(), key=lambda kv: int(kv[0]))
            if int(k) in sport.slots for _ in range(int(n))]


# ---------------------------------------------------------------- loading

def load_default(api: DailyFantasy) -> Board:
    """The most-owned players with ESPN's standard points scoring (no league needed)."""
    settings = api.defaults()
    today = int(settings["scoringPeriodId"])
    schedule = api.pro_schedule()
    slots = slot_list(settings["settings"]["rosterSettings"]["lineupSlotCounts"], api.sport)
    players = to_players(api.players(today), api.sport, api.season, schedule)
    return Board(api.sport, api.season, today, week_days(schedule, today), slots, players, "ESPN standard points",
                 notes=["Points per game from ESPN, scored with ESPN's standard points-league rules."])


def load_league(api: DailyFantasy, league_id: str, team_id: int | None = None) -> tuple[Board | None, list[Team]]:
    today = api.today()
    league = api.league(league_id, today)
    members = {m.get("id"): m.get("displayName", "") for m in league.get("members", [])}
    teams = []
    for t in league.get("teams", []):
        name = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip() or t.get("abbrev", "")
        teams.append(Team(t["id"], name or f"Team {t['id']}",
                          members.get(t.get("primaryOwner") or (t.get("owners") or [None])[0], "")))
    if team_id is None:
        return None, teams

    settings = league.get("settings", {})
    scoring_type = (settings.get("scoringSettings") or {}).get("scoringType", "")
    points_league = "POINTS" in scoring_type
    slots = slot_list((settings.get("rosterSettings") or {}).get("lineupSlotCounts", {}), api.sport)
    rosters = {t["id"]: (t.get("roster") or {}).get("entries", []) for t in league.get("teams", [])}
    period = (league.get("status") or {}).get("currentMatchupPeriod")
    game = next((m for m in league.get("schedule", []) if m.get("matchupPeriodId") == period and
                 team_id in ((m.get("home") or {}).get("teamId"), (m.get("away") or {}).get("teamId"))), None)
    opp_id, my_score, opp_score = None, 0.0, 0.0
    notes = []
    if game and game.get("away"):
        me, them = ("home", "away") if game["home"]["teamId"] == team_id else ("away", "home")
        opp_id = game[them]["teamId"]

        def so_far(side: dict) -> float:
            by = side.get("pointsByScoringPeriod") or {}
            if by:
                return float(sum(v for k, v in by.items() if int(k) < today))
            return float(side.get("totalPoints") or 0)
        my_score, opp_score = so_far(game[me]), so_far(game[them])
    else:
        notes.append("No head-to-head opponent this week (bye or playoffs).")

    mine, theirs = rosters.get(team_id, []), rosters.get(opp_id, []) if opp_id else []
    ids = [e["playerId"] for e in mine + theirs]
    schedule = api.pro_schedule()
    raw = api.players(today, league_id=league_id, ids=ids) if ids else []
    if not points_league:
        # Category leagues have no points to add up: value players with ESPN's standard points scoring.
        raw = api.players(today, ids=ids) if ids else []
        notes.append("Your league uses categories, so players are ranked with ESPN's standard points scoring as "
                     "a stand-in, and there's no single win chance to show.")
    players = to_players(raw, api.sport, api.season, schedule)
    my_ids, opp_ids = {str(e["playerId"]) for e in mine}, {str(e["playerId"]) for e in theirs}
    for p in players:
        if p.id in my_ids:
            p.tags.add("mine")
        if p.id in opp_ids:
            p.tags.add("opp")
    names = {t.id: t.name for t in teams}
    board = Board(api.sport, api.season, today, week_days(schedule, today), slots, players,
                  f"your league ({settings.get('name', league_id)})", my_ids, opp_ids, names.get(team_id, "Your team"),
                  names.get(opp_id) if opp_id else None, my_score, opp_score, points_league, notes)
    return board, teams


def with_rosters(board: Board, mine: set[str], theirs: set[str]) -> Board:
    from dataclasses import replace
    players = [replace(p, tags=({"mine"} if p.id in mine else set()) | ({"opp"} if p.id in theirs else set()))
               for p in board.players]
    return replace(board, players=players, my_ids=set(mine), opp_ids=set(theirs),
                   opp_name="Opponent" if theirs else None, my_score=0.0, opp_score=0.0)


# ---------------------------------------------------------------- lineups

def assign(values: np.ndarray, elig: np.ndarray) -> list[int]:
    """Best total value with each slot (row) given at most one eligible player (column); -1 = left empty.

    The Hungarian algorithm on a padded square cost matrix, so the answer is exact even when players fit
    several slots (a guard who can play PG, G or UTIL).
    """
    n_slots, n_players = elig.shape
    if n_slots == 0:
        return []
    n = max(n_slots, n_players + n_slots)          # extra "nobody" columns let a slot stay empty
    big = 1e6
    cost = np.zeros((n, n))
    cost[:n_slots, :n_players] = np.where(elig, -values[None, :], big)
    cost[:n_slots, n_players:n_players + n_slots] = 0.0
    # e-maxx Hungarian, 1-indexed
    u, v = np.zeros(n + 1), np.zeros(n + 1)
    p, way = np.zeros(n + 1, dtype=int), np.zeros(n + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(n + 1, np.inf)
        used = np.zeros(n + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            cur = cost[i0 - 1, :] - u[i0] - v[1:]
            free = ~used[1:]
            better = free & (cur < minv[1:])
            minv[1:][better] = cur[better]
            way[1:][better] = j0
            cand = np.where(free, minv[1:], np.inf)
            j1 = int(np.argmin(cand)) + 1
            delta = cand[j1 - 1]
            u[p[used]] += delta
            v[used] -= delta
            minv[1:][free] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    out = [-1] * n_slots
    for j in range(1, n + 1):
        i = p[j]
        if 1 <= i <= n_slots and j <= n_players and elig[i - 1, j - 1]:
            out[i - 1] = j - 1
    return out


def day_lineup(players: list[DPlayer], slots: list[str], day: Day) -> list[DPlayer | None]:
    """Best lineup that day from these players (only those with a game can score)."""
    active = [p for p in players if p.team_id in day.games and p.value > 0]
    if not active:
        return [None] * len(slots)
    elig = np.array([[s in p.eligible for p in active] for s in slots], dtype=bool)
    picks = assign(np.array([p.value for p in active]), elig)
    return [active[j] if j >= 0 else None for j in picks]


def week_starts(players: list[DPlayer], slots: list[str], days: list[Day]) -> dict[str, int]:
    """How many games each player gets in the lineup over the rest of the week."""
    starts: dict[str, int] = {}
    for d in days:
        for p in day_lineup(players, slots, d):
            if p:
                starts[p.id] = starts.get(p.id, 0) + 1
    return starts


@dataclass
class WeekOutlook:
    my_total: np.ndarray
    opp_total: np.ndarray | None
    my_starts: dict[str, int]
    opp_starts: dict[str, int]
    win_prob: float | None


def simulate_week(board: Board, n_sims: int = 1_000_000, seed: int = 7) -> WeekOutlook:
    """Simulate the rest of the week: every player's games in your best daily lineups, plus points so far."""
    rng = np.random.default_rng(seed)
    mine = [p for p in board.players if "mine" in p.tags]
    theirs = [p for p in board.players if "opp" in p.tags]

    def total(roster: list[DPlayer], already: float) -> tuple[np.ndarray, dict[str, int]]:
        starts = week_starts(roster, board.slots, board.days)
        out = np.full(n_sims, already, dtype=np.float32)      # half the memory of float64
        for p in roster:
            k = starts.get(p.id, 0)
            if not k:
                continue
            # k games, each played with chance p_play: mean and variance of the sum
            mean = k * p.p_play * p.avg
            var = k * (p.p_play * p.sd ** 2 + p.p_play * (1 - p.p_play) * p.avg ** 2)
            draw = rng.normal(mean, math.sqrt(var), n_sims).astype(np.float32)
            out += np.maximum(draw, k * board.sport.floor.get(p.position, board.sport.floor["*"]))
            del draw
        return out, starts

    my_total, my_starts = total(mine, board.my_score)
    opp_total, opp_starts, win = None, {}, None
    if theirs:
        opp_total, opp_starts = total(theirs, board.opp_score)
        win = float((my_total > opp_total).mean() + 0.5 * (my_total == opp_total).mean())
    return WeekOutlook(my_total, opp_total, my_starts, opp_starts, win)


def game_range(p: DPlayer, sport: Sport) -> tuple[float, float]:
    """10th and 90th percentile of one game."""
    lo = sport.floor.get(p.position, sport.floor["*"])
    return max(lo, p.avg - 1.2816 * p.sd), p.avg + 1.2816 * p.sd
