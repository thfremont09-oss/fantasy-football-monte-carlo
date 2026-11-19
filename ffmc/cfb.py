"""College football fantasy: projections for every FBS player, built from ESPN box scores.

ESPN has no college fantasy game, so there are no ready-made projections. We make our own:

* every FBS box score from the last few weeks (cached on disk: finished games never change),
* each player's fantasy points per game from those box scores, with your scoring (PPR, half or standard),
* nudged up or down by this week's matchup: the team's expected points from the betting line
  (over/under and spread) compared with a typical FBS team's,
* positions from ESPN's college stat lists (box scores don't say who's a TE and who's a WR).

The result is an ordinary Slate, so the NFL simulator and lineup optimizer work unchanged.
"""

from __future__ import annotations

import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .data import Slate
from .http import APIError, CachedJSON
from .model import Player, estimate

SITE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
BYATHLETE = "https://site.api.espn.com/apis/common/v3/sports/football/college-football/statistics/byathlete"
FBS = "80"
SKILL = {"QB", "RB", "WR", "TE"}
DEFAULT_SLOTS = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX"]
RULES = {"PPR": 1.0, "Half-PPR": 0.5, "Standard": 0.0}       # points per catch
AVG_TEAM_POINTS = 28.0          # a typical FBS team's points per game
MATCHUP_WEIGHT = 0.6            # how much of the betting-line edge carries into a player's projection
# A few big games can be a fluke: projections are pulled toward a typical starter at the position,
# as if he'd also played PRIOR_GAMES ordinary games.
TYPICAL = {"QB": 17.0, "RB": 11.0, "WR": 10.0, "TE": 7.0}
PRIOR_GAMES = 2.5


def season_now(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.year if today.month >= 6 else today.year - 1


def fantasy_points(s: dict, ppr: float) -> float:
    """Standard fantasy scoring from a box-score line."""
    return (0.04 * s.get("passYds", 0) + 4 * s.get("passTD", 0) - 2 * s.get("int", 0)
            + 0.1 * s.get("rushYds", 0) + 6 * s.get("rushTD", 0)
            + 0.1 * s.get("recYds", 0) + 6 * s.get("recTD", 0) + ppr * s.get("rec", 0)
            - 2 * s.get("fumLost", 0))


def _int(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return 0.0


def box_lines(summary: dict) -> dict[str, dict]:
    """athlete id -> {name, team, team_id, passYds, passTD, ...} for one game."""
    out: dict[str, dict] = {}
    fields = {
        "passing": {"passingYards": "passYds", "passingTouchdowns": "passTD", "interceptions": "int"},
        "rushing": {"rushingAttempts": "rushAtt", "rushingYards": "rushYds", "rushingTouchdowns": "rushTD"},
        "receiving": {"receptions": "rec", "receivingYards": "recYds", "receivingTouchdowns": "recTD"},
        "fumbles": {"fumblesLost": "fumLost"},
    }
    for team in (summary.get("boxscore") or {}).get("players") or []:
        t = team.get("team") or {}
        for cat in team.get("statistics") or []:
            want = fields.get(cat.get("name"))
            if not want:
                continue
            keys = cat.get("keys") or []
            for a in cat.get("athletes") or []:
                who = a.get("athlete") or {}
                if not who.get("id"):
                    continue
                row = out.setdefault(str(who["id"]), {"name": who.get("displayName", ""), "team": t.get("abbreviation", ""),
                                                      "team_id": str(t.get("id", ""))})
                for k, v in zip(keys, a.get("stats") or []):
                    if k == "completions/passingAttempts":
                        row["passAtt"] = _int(str(v).split("/")[-1])
                    elif k in want:
                        row[want[k]] = _int(v)
    return out


class CollegeData:
    def __init__(self, cache_dir: str | Path = ".ffmc_cache"):
        self.http = CachedJSON(cache_dir)
        self.box_dir = Path(cache_dir) / "cfb_box"
        self.box_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- schedule
    def scoreboard(self, week: int | None = None, season: int | None = None) -> dict:
        params = [("groups", FBS), ("limit", "400")]
        if week:
            params.append(("week", str(week)))
        if season:
            params += [("dates", str(season)), ("seasontype", "2")]
        return self.http.get(f"{SITE}/scoreboard", params, ttl=600)

    def current(self) -> tuple[int, int]:
        sb = self.scoreboard()
        return int((sb.get("season") or {}).get("year") or season_now()), int((sb.get("week") or {}).get("number") or 1)

    def week_games(self, season: int, week: int) -> dict[str, dict]:
        """team id -> {opp, home, start, implied (expected points from the betting line)} for this week."""
        out = {}
        for ev in self.scoreboard(week, season).get("events") or []:
            comp = (ev.get("competitions") or [{}])[0]
            teams = comp.get("competitors") or []
            if len(teams) != 2:
                continue
            odds = (comp.get("odds") or [{}])[0]
            total, spread = odds.get("overUnder"), odds.get("spread")
            fav = None
            for side in ("homeTeamOdds", "awayTeamOdds"):
                if (odds.get(side) or {}).get("favorite"):
                    fav = "home" if side == "homeTeamOdds" else "away"
            for c in teams:
                other = next(x for x in teams if x is not c)
                implied = None
                if total and spread is not None:
                    # spread is quoted for the favourite (e.g. -7.5): they score more, the underdog less
                    edge = abs(float(spread)) / 2
                    implied = float(total) / 2 + (edge if c.get("homeAway") == fav else -edge)
                out[str((c.get("team") or {}).get("id"))] = {
                    "opp": (other.get("team") or {}).get("abbreviation", ""),
                    "home": c.get("homeAway") == "home",
                    "start": ev.get("date", ""), "implied": implied,
                    "state": ((ev.get("status") or {}).get("type") or {}).get("state", "pre"),
                }
        return out

    # --------------------------------------------------------------- box scores
    def _box(self, event_id: str) -> dict[str, dict]:
        f = self.box_dir / f"{event_id}.json"
        try:
            return json.loads(f.read_text())
        except (OSError, ValueError):
            pass
        try:
            lines = box_lines(self.http.get(f"{SITE}/summary", [("event", event_id)]))
        except APIError:
            return {}
        f.write_text(json.dumps(lines))
        return lines

    def history(self, season: int, week: int, weeks: int = 5) -> list[dict[str, dict]]:
        """Box-score lines for every finished FBS game in the ``weeks`` weeks before ``week``, newest first."""
        ids = []
        for w in range(week - 1, max(0, week - 1 - weeks), -1):
            try:
                events = self.scoreboard(w, season).get("events") or []
            except APIError:
                continue
            ids.append([e["id"] for e in events
                        if ((e.get("status") or {}).get("type") or {}).get("state") == "post"])
        with ThreadPoolExecutor(12) as pool:
            out = []
            for week_ids in ids:
                merged: dict[str, dict] = {}
                for lines in pool.map(self._box, week_ids):
                    merged.update(lines)
                out.append(merged)
        return out

    def fbs_teams(self) -> set[str]:
        """ESPN team ids of every FBS team (FCS opponents show up in FBS box scores too)."""
        data = self.http.get("https://site.api.espn.com/apis/v2/sports/football/college-football/standings",
                             [("group", FBS)], ttl=7 * 86400)
        ids: set[str] = set()

        def walk(o):
            if isinstance(o, dict):
                for e in (o.get("standings") or {}).get("entries") or []:
                    ids.add(str((e.get("team") or {}).get("id")))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(data)
        return ids

    # ----------------------------------------------------------------- positions
    def positions(self) -> dict[str, str]:
        """athlete id -> QB / RB / WR / TE, from ESPN's college stat lists (top passers, rushers and receivers)."""
        out: dict[str, str] = {}
        for sort in ("passing.passingYards", "rushing.rushingYards", "receiving.receivingYards"):
            try:
                data = self.http.get(BYATHLETE, [("limit", "1000"), ("isqualified", "false"), ("sort", f"{sort}:desc")],
                                     ttl=24 * 3600)
            except APIError:
                continue
            for a in data.get("athletes") or []:
                ath = a.get("athlete") or {}
                pos = (ath.get("position") or {}).get("abbreviation", "")
                if pos in SKILL:
                    out.setdefault(str(ath.get("id")), pos)
        return out


def _guess_position(lines: list[dict]) -> str | None:
    """When ESPN's lists don't have a player: passer -> QB, mostly runs -> RB, mostly catches -> WR."""
    att = sum(l.get("passAtt", 0) for l in lines)
    rush = sum(l.get("rushAtt", 0) for l in lines)
    rec = sum(l.get("rec", 0) for l in lines)
    if att >= 5 * len(lines):
        return "QB"
    if rush + rec == 0:
        return None
    return "RB" if rush > rec else "WR"


def build_players(history: list[dict[str, dict]], positions: dict[str, str], games: dict[str, dict],
                  ppr: float, fbs: set[str] | None = None) -> list[Player]:
    """One simulator Player per FBS skill player who played recently and whose team plays this week."""
    per_player: dict[str, list[dict]] = {}
    for week_lines in history:                       # newest week first
        for pid, line in week_lines.items():
            per_player.setdefault(pid, []).append(line)
    out = []
    for pid, lines in per_player.items():
        pos = positions.get(pid) or _guess_position(lines)
        if pos not in SKILL:
            continue
        pts = [fantasy_points(l, ppr) for l in lines]
        if len(pts) < 2 and (not pts or pts[0] < 8):
            continue                                  # one quiet game isn't enough to go on
        last = lines[0]
        if fbs and last.get("team_id") not in fbs:
            continue
        g = games.get(last.get("team_id", ""))
        # recent games count more: weights 1, .85, .72, ...
        w = 0.85 ** np.arange(len(pts))
        avg = float(np.dot(w, pts) / w.sum())
        typical = TYPICAL[pos] * (1 + 0.6 * (ppr - 1) if pos in ("WR", "TE", "RB") else 1)
        avg = (w.sum() * avg + PRIOR_GAMES * typical) / (w.sum() + PRIOR_GAMES)
        factor = 1.0
        if g and g.get("implied"):
            factor = 1 + MATCHUP_WEIGHT * (g["implied"] / AVG_TEAM_POINTS - 1)
            factor = float(np.clip(factor, 0.7, 1.35))
        proj = avg * factor
        mean, sd, hist_mean, n = estimate(proj, pts, pos)
        playing = bool(g) and g.get("state") == "pre"
        out.append(Player(
            player_id=pid, name=last.get("name", pid), position=pos, team=last.get("team"),
            opponent=g.get("opp") if g else None,
            mean=mean if playing else 0.0, sd=sd if playing else 0.0, p_play=1.0 if playing else 0.0,
            injury_status=None if playing else ("BYE" if not g else "Started"),
            projection=round(proj, 1), hist_mean=hist_mean, hist_games=n,
        ))
    return out


def load_slate(data: CollegeData, rules: str = "PPR", slots: list[str] | None = None, season: int | None = None,
               week: int | None = None, history_weeks: int = 5) -> Slate:
    if not season or not week:
        s, w = data.current()
        season, week = season or s, week or w
    games = data.week_games(season, week)
    history = data.history(season, week, max(2, min(history_weeks, 6)))
    if not any(history):
        raise APIError("No college box scores found for the weeks before this one yet.")
    try:
        fbs = data.fbs_teams()
    except APIError:
        fbs = None
    players = build_players(history, data.positions(), games, RULES[rules], fbs)
    players = [p for p in players if p.mean > 1.0]
    notes = [f"Projections are ours: each FBS player's points per game over the last {len(history)} weeks of box "
             "scores, adjusted for this week's betting line. College injury reports aren't public, so check "
             "who's playing before kickoff."]
    return Slate(season, week, f"College {rules}", list(slots or DEFAULT_SLOTS), players, notes=notes)
