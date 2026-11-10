"""Turn projections + recent history into a per-player points distribution."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .scoring import fantasy_points

# Typical week-to-week coefficient of variation by position. Used as a prior
# for the standard deviation and shrunk toward each player's observed spread.
POSITION_CV = {"QB": 0.40, "RB": 0.55, "WR": 0.62, "TE": 0.70, "K": 0.45, "DEF": 0.70}

# How far below zero a player can realistically score (interceptions, fumbles,
# points allowed). The simulated distribution is shifted by this amount.
POSITION_FLOOR = {"QB": -3.0, "RB": -2.0, "WR": -2.0, "TE": -2.0, "K": -2.0, "DEF": -5.0}

# Probability the player is active, by Sleeper injury_status.
PLAY_PROBABILITY = {
    None: 1.0, "": 1.0, "Questionable": 0.80, "Doubtful": 0.20,
    "Out": 0.0, "IR": 0.0, "PUP": 0.0, "Sus": 0.0, "NA": 0.0, "COV": 0.0,
}

PROJECTION_WEIGHT = 0.75   # weight on this week's projection vs. recent average
PRIOR_GAMES = 4            # pseudo-games of the positional prior for the SD


@dataclass
class Player:
    player_id: str
    name: str
    position: str
    team: str | None
    opponent: str | None
    mean: float                 # expected points *if the player is active*
    sd: float
    p_play: float = 1.0
    injury_status: str | None = None
    projection: float = 0.0
    hist_mean: float | None = None
    hist_games: int = 0
    tags: set[str] = field(default_factory=set)   # e.g. {"mine"}, {"opp"}

    def label(self) -> str:
        team = self.team or "FA"
        return f"{self.name} ({self.position}, {team})"


def player_name(info: dict) -> str:
    if info.get("full_name"):
        return info["full_name"]
    first, last = info.get("first_name", ""), info.get("last_name", "")
    return f"{first} {last}".strip() or str(info.get("player_id", "?"))


def played(stats: dict) -> bool:
    if "gp" in stats:
        return (stats.get("gp") or 0) > 0
    return any(isinstance(v, (int, float)) and v != 0 for v in stats.values())


def history_points(weekly: list[dict[str, dict]], scoring: dict, positions: dict[str, str],
                   preset: str | None) -> dict[str, list[float]]:
    """Points scored per game for each player across the supplied weeks."""
    out: dict[str, list[float]] = {}
    for week in weekly:
        for pid, row in week.items():
            stats = row["stats"]
            pos = positions.get(pid)
            if pos is None or not played(stats):
                continue
            out.setdefault(pid, []).append(fantasy_points(stats, scoring, pos, preset))
    return out


def estimate(projection: float, history: list[float] | None, position: str) -> tuple[float, float, float | None, int]:
    """Blend projection with history; return (mean, sd, hist_mean, n_games)."""
    hist = history or []
    n = len(hist)
    hist_mean = float(np.mean(hist)) if n else None
    if n >= 3 and projection > 0:
        mean = PROJECTION_WEIGHT * projection + (1 - PROJECTION_WEIGHT) * hist_mean
    elif projection > 0:
        mean = projection
    else:
        mean = hist_mean or 0.0
    mean = max(mean, 0.0)

    prior_sd = POSITION_CV.get(position, 0.6) * max(mean, 2.0)
    if n >= 2:
        sample_var = float(np.var(hist, ddof=1))
        # Scale the observed spread to this week's mean so a player whose role
        # changed doesn't keep an outdated SD.
        if hist_mean and hist_mean > 1:
            sample_var *= (max(mean, 1.0) / hist_mean) ** 2
        sd = math.sqrt((n * sample_var + PRIOR_GAMES * prior_sd**2) / (n + PRIOR_GAMES))
    else:
        sd = prior_sd
    return mean, sd, hist_mean, n


def build_players(projections: dict[str, dict], players_db: dict[str, dict], scoring: dict,
                  preset: str | None, history: dict[str, list[float]] | None = None,
                  include_ids: set[str] | None = None, min_points: float = 1.0) -> list[Player]:
    """Create Player objects for everyone projected this week.

    ``include_ids`` are always kept (e.g. your roster) even if projected for
    zero points (bye week, injured) so they show up on the bench.
    """
    history = history or {}
    include_ids = include_ids or set()
    out: list[Player] = []
    for pid, row in projections.items():
        info = players_db.get(pid, {})
        pos = info.get("position") or (row.get("stats", {}).get("position"))
        if pos not in POSITION_CV:
            continue
        proj = fantasy_points(row["stats"], scoring, pos, preset)
        if proj < min_points and pid not in include_ids:
            continue
        mean, sd, hmean, n = estimate(proj, history.get(pid), pos)
        status = info.get("injury_status")
        out.append(Player(
            player_id=pid, name=player_name(info), position=pos,
            team=row.get("team") or info.get("team"), opponent=row.get("opponent"),
            mean=mean if proj > 0 else 0.0, sd=sd if proj > 0 else 0.0,
            p_play=PLAY_PROBABILITY.get(status, 1.0), injury_status=status,
            projection=proj, hist_mean=hmean, hist_games=n,
        ))
    # Rostered players with no projection row at all (bye week etc.)
    seen = {p.player_id for p in out}
    for pid in include_ids - seen:
        info = players_db.get(pid, {})
        pos = info.get("position")
        if pos not in POSITION_CV:
            continue
        out.append(Player(pid, player_name(info), pos, info.get("team"), None, 0.0, 0.0,
                          p_play=0.0, injury_status=info.get("injury_status") or "BYE"))
    return out
