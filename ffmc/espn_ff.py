"""ESPN Fantasy Football: leagues, rosters, scoring and projections.

Uses ESPN's fantasy API (the same one espn.com's fantasy app uses):

* ESPN's own weekly projections and past points, already scored with your
  league's rules (or ESPN's default Standard / PPR rules).
* Your league's lineup slots, your roster, and this week's opponent.

Public leagues need only the league ID. Private leagues (ESPN's default) also
need the ``espn_s2`` and ``SWID`` cookies from a browser that's logged in to ESPN.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .data import Slate
from .http import APIError, CachedJSON
from .lineup import DEFAULT_SLOTS, parse_slots
from .model import PLAY_PROBABILITY, Player, estimate

API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
# ESPN lineup slot ids -> our slot names (IDP and head-coach slots aren't supported).
SLOTS = {0: "QB", 2: "RB", 3: "WRRB_FLEX", 4: "WR", 5: "REC_FLEX", 6: "TE", 7: "SUPER_FLEX",
         16: "DEF", 17: "K", 23: "FLEX"}
BENCH_SLOTS = {20, 21}             # bench, injured reserve
INJURY = {"ACTIVE": None, "NORMAL": None, "QUESTIONABLE": "Questionable", "DOUBTFUL": "Doubtful",
          "OUT": "Out", "INJURY_RESERVE": "IR", "SUSPENSION": "Sus"}
DEFAULT_RULES = {"ESPN PPR": [3], "ESPN Half-PPR": [1, 3], "ESPN Standard": [1]}   # ESPN default-scoring ids
PROJECTED, ACTUAL = 1, 0

ESPNError = APIError


@dataclass
class LeagueTeam:
    id: int
    name: str
    owner: str


class ESPNFantasy:
    def __init__(self, season: int, cache_dir=".ffmc_cache", espn_s2: str = "", swid: str = ""):
        self.season = season
        self.http = CachedJSON(cache_dir)
        swid = swid.strip()
        if swid and not swid.startswith("{"):
            swid = "{" + swid.strip("{}") + "}"
        self.cookies = {"espn_s2": espn_s2.strip(), "SWID": swid} if espn_s2.strip() and swid else None

    def _get(self, path: str = "", params=None, filt: dict | None = None, ttl: float = 900):
        headers = {"X-Fantasy-Filter": json.dumps(filt)} if filt else None
        return self.http.get(API.format(season=self.season) + path, params, ttl=ttl, headers=headers,
                             cookies=self.cookies)

    # ------------------------------------------------------------- endpoints
    def pro_schedule(self) -> dict[int, dict]:
        teams = self._get("", [("view", "proTeamSchedules_wl")], ttl=86400)["settings"]["proTeams"]
        return {t["id"]: t for t in teams}

    def current_week(self) -> int:
        return int(self._get("/segments/0/leaguedefaults/3", [("view", "mSettings")], ttl=1800)["scoringPeriodId"])

    def players(self, week: int, *, league_id: str | None = None, rules: int = 3,
                ids: list[int] | None = None, limit: int = 450) -> list[dict]:
        """Players with ESPN's stats, scored by a league's rules or a default rule set."""
        base = f"/segments/0/leagues/{league_id}" if league_id else f"/segments/0/leaguedefaults/{rules}"
        filt = {"players": {"filterIds": {"value": ids}}} if ids else {"players": {
            "filterSlotIds": {"value": [0, 2, 4, 6, 16, 17]}, "limit": limit,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
        data = self._get(base, [("scoringPeriodId", str(week)), ("view", "kona_player_info")], filt, ttl=1800)
        return [e["player"] for e in data.get("players", [])]

    def league(self, league_id: str, week: int) -> dict:
        try:
            return self._get(f"/segments/0/leagues/{league_id}",
                             [("scoringPeriodId", str(week)), ("view", "mSettings"), ("view", "mTeam"),
                              ("view", "mRoster"), ("view", "mMatchup")], ttl=300)
        except APIError as exc:
            msg = str(exc)
            if "NOT_VISIBLE" in msg or "401" in msg:
                raise ESPNError("This ESPN league is private. Add your espn_s2 and SWID cookies "
                                "(see 'How do I find these?') and try again.") from exc
            if "404" in msg or "NOT_FOUND" in msg:
                raise ESPNError(f"No ESPN league with ID {league_id} in the {self.season} season.") from exc
            raise


def team_names(league: dict) -> list[LeagueTeam]:
    members = {m.get("id"): m.get("displayName", "") for m in league.get("members", [])}
    out = []
    for t in league.get("teams", []):
        name = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip() or t.get("abbrev", "")
        owner = members.get(t.get("primaryOwner") or (t.get("owners") or [None])[0], "")
        out.append(LeagueTeam(t["id"], name or f"Team {t['id']}", owner))
    return out


# --------------------------------------------------------------- conversion
def _weekly(player: dict, season: int, source: int) -> dict[int, float]:
    return {s["scoringPeriodId"]: float(s.get("appliedTotal") or 0) for s in player.get("stats", [])
            if s.get("seasonId") == season and s.get("statSourceId") == source and s.get("statSplitTypeId") == 1}


def to_players(pools: list[list[dict]], season: int, week: int, schedule: dict[int, dict],
               history_weeks: int = 6) -> list[Player]:
    """Combine one or more ESPN player lists (averaged, for Half-PPR) into simulator players."""
    abbrev = {tid: t.get("abbrev", "FA") for tid, t in schedule.items()}
    opponent = {}
    for tid, t in schedule.items():
        for g in (t.get("proGamesByScoringPeriod") or {}).get(str(week), []):
            opponent[tid] = g["awayProTeamId"] if g["homeProTeamId"] == tid else g["homeProTeamId"]

    by_id: dict[int, list[dict]] = {}
    for pool in pools:
        for p in pool:
            by_id.setdefault(p["id"], []).append(p)

    out = []
    for pid, versions in by_id.items():
        p = versions[0]
        pos = POSITIONS.get(p.get("defaultPositionId"))
        if pos is None:
            continue
        proj = sum(_weekly(v, season, PROJECTED).get(week, 0.0) for v in versions) / len(versions)
        actual = [_weekly(v, season, ACTUAL) for v in versions]
        recent = [w for w in range(max(1, week - history_weeks), week) if w in actual[0]]
        history = [sum(a.get(w, 0.0) for a in actual) / len(actual) for w in recent]
        team = p.get("proTeamId")
        playing = team in opponent
        mean, sd, hist_mean, n = estimate(proj, history, pos)
        status = INJURY.get(p.get("injuryStatus") or "ACTIVE", None) if p.get("injuryStatus") else None
        if not playing:
            status = status or "BYE"
        out.append(Player(
            player_id=str(pid), name=p.get("fullName", str(pid)), position=pos,
            team=abbrev.get(team), opponent=abbrev.get(opponent.get(team)) if playing else None,
            mean=mean if playing and proj > 0 else 0.0, sd=sd if playing and proj > 0 else 0.0,
            p_play=PLAY_PROBABILITY.get(status, 1.0) if playing else 0.0, injury_status=status,
            projection=proj, hist_mean=hist_mean, hist_games=n,
        ))
    return out


# ------------------------------------------------------------------ slates
def load_default(api: ESPNFantasy, rules: str = "ESPN PPR", slots: list[str] | None = None,
                 week: int | None = None, history_weeks: int = 6) -> Slate:
    """Every relevant NFL player, scored with ESPN's default rules (no league needed)."""
    week = week or api.current_week()
    pools = [api.players(week, rules=r) for r in DEFAULT_RULES[rules]]
    players = to_players(pools, api.season, week, api.pro_schedule(), history_weeks)
    players = [p for p in players if p.mean > 0.5]
    return Slate(api.season, week, rules, list(slots or DEFAULT_SLOTS), players,
                 notes=["Projections and points from ESPN, scored with ESPN's default rules."])


def load_league(api: ESPNFantasy, league_id: str, team_id: int | None = None, week: int | None = None,
                history_weeks: int = 6) -> tuple[Slate, list[LeagueTeam]]:
    """Your ESPN league: its scoring, lineup slots, your roster and this week's opponent."""
    week = week or api.current_week()
    league = api.league(league_id, week)
    teams = team_names(league)
    if team_id is None:
        return Slate(api.season, week, "", [], []), teams

    settings = league.get("settings", {})
    counts = settings.get("rosterSettings", {}).get("lineupSlotCounts", {})
    raw = [SLOTS.get(int(k), f"slot {k}") for k, n in counts.items() if int(k) not in BENCH_SLOTS for _ in range(n)]
    slots, skipped = parse_slots([s for s in raw if not s.startswith("slot ")])
    notes = []
    unsupported = sorted({s for s in raw if s.startswith("slot ")})
    if unsupported or skipped:
        notes.append("Some lineup slots in this league (e.g. IDP) aren't supported and were left out.")

    rosters = {t["id"]: t.get("roster", {}).get("entries", []) for t in league.get("teams", [])}
    mine = rosters.get(team_id, [])
    period = league.get("status", {}).get("currentMatchupPeriod") or week
    game = next((m for m in league.get("schedule", []) if m.get("matchupPeriodId") == period and
                 team_id in (m.get("home", {}).get("teamId"), m.get("away", {}).get("teamId"))), None)
    opp_id = None
    if game and game.get("away"):
        opp_id = game["away"]["teamId"] if game["home"]["teamId"] == team_id else game["home"]["teamId"]
    theirs = rosters.get(opp_id, []) if opp_id else []

    ids = [e["playerId"] for e in mine + theirs]
    pool = api.players(week, league_id=league_id, ids=ids) if ids else []
    players = to_players([pool], api.season, week, api.pro_schedule(), history_weeks)
    my_ids = {str(e["playerId"]) for e in mine}
    opp_ids = {str(e["playerId"]) for e in theirs}
    for p in players:
        if p.player_id in my_ids:
            p.tags.add("mine")
        if p.player_id in opp_ids:
            p.tags.add("opp")
    opp_starters = [str(e["playerId"]) for e in theirs if e.get("lineupSlotId") not in BENCH_SLOTS] or None
    names = {t.id: t.name for t in teams}
    if not opp_id:
        notes.append("No head-to-head opponent this week (bye or playoffs).")
    slate = Slate(api.season, week, f"your league ({settings.get('name', league_id)})", slots or list(DEFAULT_SLOTS),
                  players, my_ids, opp_ids, opp_starters, names.get(team_id, "Your team"),
                  names.get(opp_id) if opp_id else None, notes)
    return slate, teams
