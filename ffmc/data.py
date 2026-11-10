"""Assemble everything needed for one week's simulation (a "slate")."""

from __future__ import annotations

import difflib
import re
import sys
from dataclasses import dataclass, field

from .lineup import DEFAULT_SLOTS, parse_slots
from .model import Player, build_players, history_points, player_name
from .scoring import PRESETS
from .sleeper import POSITIONS, SleeperClient, SleeperError


@dataclass
class Slate:
    season: int
    week: int
    scoring_name: str
    slots: list[str]
    players: list[Player]
    my_ids: set[str] = field(default_factory=set)
    opp_ids: set[str] = field(default_factory=set)
    opp_starters: list[str] | None = None
    my_name: str = "Your team"
    opp_name: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def has_roster(self) -> bool:
        return bool(self.my_ids)

    @property
    def has_opponent(self) -> bool:
        return bool(self.opp_ids)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- name lookup
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def normalize_name(name: str) -> str:
    name = name.lower().replace(".", "").replace("'", "").replace("-", " ")
    name = _SUFFIX.sub("", name)
    return " ".join(name.split())


def resolve_names(names: list[str], players_db: dict[str, dict],
                  prefer_ids: set[str]) -> tuple[list[str], list[str]]:
    """Map free-text player names (or team abbreviations for defenses) to Sleeper ids."""
    index: dict[str, list[str]] = {}
    for pid, info in players_db.items():
        if info.get("position") not in POSITIONS:
            continue
        keys = {normalize_name(player_name(info))}
        if info.get("position") == "DEF":
            keys |= {normalize_name(pid), normalize_name(f"{pid} def"), normalize_name(f"{pid} dst"),
                     normalize_name(info.get("last_name", "")), normalize_name(f"{info.get('last_name', '')} def")}
        for k in keys:
            if k:
                index.setdefault(k, []).append(pid)

    ids, notes = [], []
    for raw in names:
        raw = raw.strip()
        if not raw:
            continue
        key = normalize_name(raw)
        match_key = key if key in index else None
        if match_key is None:
            close = difflib.get_close_matches(key, index.keys(), n=1, cutoff=0.8)
            if close:
                match_key = close[0]
                notes.append(f"'{raw}' matched to '{player_name(players_db[index[match_key][0]])}'")
        if match_key is None:
            notes.append(f"could not find a player named '{raw}' - skipped")
            continue
        cands = index[match_key]
        # Prefer players who actually have a projection / are on an NFL team.
        cands = sorted(cands, key=lambda p: (p not in prefer_ids, not players_db[p].get("team")))
        ids.append(cands[0])
    return ids, notes


# ------------------------------------------------------------------ live data
def load_live(client: SleeperClient, *, season: int | None = None, week: int | None = None,
              scoring: str = "ppr", slots: list[str] | None = None, league_id: str | None = None,
              username: str | None = None, roster_names: list[str] | None = None,
              opponent_names: list[str] | None = None, history_weeks: int = 6) -> Slate:
    notes: list[str] = []
    state = client.state()
    season = season or int(state.get("league_season") or state.get("season"))
    if week is None:
        week = int(state.get("week") or state.get("display_week") or 1)
        if state.get("season_type") != "regular" or week < 1:
            week = max(week, 1)
            notes.append(f"NFL state is '{state.get('season_type')}', using week {week}")
    _log(f"Season {season}, week {week}")

    # Scoring & slots ---------------------------------------------------------
    league = None
    if league_id:
        league = client.league(league_id)
        scoring_settings = {k: float(v) for k, v in (league.get("scoring_settings") or {}).items()}
        preset = None
        scoring_name = f"league '{league.get('name', league_id)}'"
        raw_slots = league.get("roster_positions") or DEFAULT_SLOTS
    else:
        scoring_settings = PRESETS[scoring]
        preset = scoring
        scoring_name = scoring.upper()
        raw_slots = slots or DEFAULT_SLOTS
    slot_list, skipped = parse_slots(raw_slots)
    if skipped:
        notes.append(f"unsupported slots ignored: {', '.join(skipped)}")

    # Players, projections, history ------------------------------------------
    _log("Loading player database...")
    players_db = client.players()
    _log("Loading projections...")
    projections = client.projections(season, week)
    if not projections:
        raise SleeperError(f"no projections available for {season} week {week}")

    weekly = []
    for w in range(max(1, week - history_weeks), week):
        try:
            weekly.append(client.stats(season, w))
        except SleeperError as exc:
            notes.append(f"history for week {w} unavailable ({exc})")
    if weekly:
        _log(f"Loaded {len(weekly)} weeks of history for variance estimates")
    positions = {pid: info.get("position") for pid, info in players_db.items()}
    history = history_points(weekly, scoring_settings, positions, preset)

    # Rosters ---------------------------------------------------------------
    my_ids: set[str] = set()
    opp_ids: set[str] = set()
    opp_starters = None
    my_name, opp_name = "Your team", None
    if league_id:
        if not username:
            raise SleeperError("--user is required with --league")
        user = client.user(username)
        uid = user["user_id"]
        users = {u["user_id"]: u for u in client.league_users(league_id)}
        rosters = client.league_rosters(league_id)
        mine = next((r for r in rosters if r.get("owner_id") == uid or uid in (r.get("co_owners") or [])), None)
        if mine is None:
            raise SleeperError(f"user '{username}' has no roster in league {league_id}")
        my_ids = set(mine.get("players") or [])
        my_name = _team_name(users.get(uid), username)
        try:
            matchups = client.matchups(league_id, week)
        except SleeperError:
            matchups = []
        me = next((m for m in matchups if m.get("roster_id") == mine["roster_id"]), None)
        if me and me.get("matchup_id") is not None:
            opp = next((m for m in matchups if m.get("matchup_id") == me["matchup_id"]
                        and m.get("roster_id") != mine["roster_id"]), None)
            if opp:
                opp_ids = set(opp.get("players") or [])
                starters = [s for s in (opp.get("starters") or []) if s and s != "0"]
                opp_starters = starters or None
                opp_roster = next((r for r in rosters if r.get("roster_id") == opp["roster_id"]), {})
                opp_name = _team_name(users.get(opp_roster.get("owner_id")), "Opponent")
        if not opp_ids:
            notes.append("no head-to-head opponent found for this week")
    if roster_names:
        ids, n = resolve_names(roster_names, players_db, set(projections))
        my_ids |= set(ids)
        notes += n
    if opponent_names:
        ids, n = resolve_names(opponent_names, players_db, set(projections))
        opp_ids |= set(ids)
        opp_name = opp_name or "Opponent"
        notes += n

    players = build_players(projections, players_db, scoring_settings, preset, history,
                            include_ids=my_ids | opp_ids)
    for p in players:
        if p.player_id in my_ids:
            p.tags.add("mine")
        if p.player_id in opp_ids:
            p.tags.add("opp")
    return Slate(season, week, scoring_name, slot_list, players, my_ids, opp_ids, opp_starters,
                 my_name, opp_name, notes)


def _team_name(user: dict | None, fallback: str) -> str:
    if not user:
        return fallback
    return (user.get("metadata") or {}).get("team_name") or user.get("display_name") or fallback


def with_rosters(slate: Slate, my_ids: set[str], opp_ids: set[str] | None = None,
                 my_name: str = "Your team", opp_name: str | None = "Opponent") -> Slate:
    """Copy of ``slate`` with the given players tagged as yours / your opponent's."""
    from dataclasses import replace

    opp_ids = opp_ids or set()
    players = []
    for p in slate.players:
        tags = set()
        if p.player_id in my_ids:
            tags.add("mine")
        if p.player_id in opp_ids:
            tags.add("opp")
        players.append(replace(p, tags=tags))
    return replace(slate, players=players, my_ids=set(my_ids), opp_ids=set(opp_ids),
                   opp_starters=None, my_name=my_name, opp_name=opp_name if opp_ids else None,
                   notes=list(slate.notes))
