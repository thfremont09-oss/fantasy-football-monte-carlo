"""Synthetic data so the tool can be tried (and tested) without network access."""

from __future__ import annotations

import numpy as np

from .data import Slate
from .lineup import DEFAULT_SLOTS
from .model import build_players, history_points
from .scoring import PRESETS

# position -> list of (typical projected points) for each depth-chart spot
DEPTH = {"QB": [19], "RB": [15, 9, 4], "WR": [15, 11, 7, 3], "TE": [9, 4], "K": [8], "DEF": [7]}


def _stat_line(pos: str, pts: float, scoring: str) -> dict:
    # Only the pre-computed totals matter for the demo.
    rec = {"RB": 0.12, "WR": 0.28, "TE": 0.30}.get(pos, 0.0) * pts
    return {"pts_std": pts - rec, "pts_half_ppr": pts - rec / 2, "pts_ppr": pts, "gp": 1}


def demo_slate(seed: int = 7, scoring: str = "ppr", week: int = 10, roster_size: int = 15,
               with_roster: bool = True) -> Slate:
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(1, 17)]
    order = rng.permutation(teams)
    opponent = {}
    for a, b in zip(order[::2], order[1::2]):
        opponent[a], opponent[b] = b, a

    players_db, projections = {}, {}
    weekly = [dict() for _ in range(6)]
    for team in teams:
        strength = rng.normal(1.0, 0.12)
        for pos, depth in DEPTH.items():
            for d, base in enumerate(depth, start=1):
                pid = team if pos == "DEF" else f"{team}-{pos}{d}"
                name = f"{team} Defense" if pos == "DEF" else f"{team} {pos}{d}"
                status = rng.choice([None, "Questionable", "Doubtful", "Out"], p=[0.86, 0.09, 0.02, 0.03])
                players_db[pid] = {"player_id": pid, "full_name": name, "position": pos, "team": team,
                                   "injury_status": status}
                proj = max(0.0, base * strength * rng.normal(1.0, 0.18))
                projections[pid] = {"stats": _stat_line(pos, proj, scoring), "team": team,
                                    "opponent": opponent[team]}
                cv = {"QB": 0.4, "RB": 0.55, "WR": 0.65, "TE": 0.7, "K": 0.45, "DEF": 0.7}[pos]
                for w in weekly:
                    pts = max(-3.0, rng.normal(proj, cv * max(proj, 2) * rng.uniform(0.7, 1.3)))
                    w[pid] = {"stats": _stat_line(pos, pts, scoring), "team": team, "opponent": None}

    positions = {pid: info["position"] for pid, info in players_db.items()}
    history = history_points(weekly, PRESETS[scoring], positions, scoring)

    my_ids: set[str] = set()
    opp_ids: set[str] = set()
    if with_roster:
        # Draft two plausible rosters by alternating picks from a noisy board.
        need = {"QB": 2, "RB": 5, "WR": 5, "TE": 1, "K": 1, "DEF": 1}
        board = sorted(projections, key=lambda p: -projections[p]["stats"]["pts_ppr"] * rng.uniform(0.6, 1.4))
        counts = [dict.fromkeys(need, 0), dict.fromkeys(need, 0)]
        rosters = [my_ids, opp_ids]
        turn = 0
        for pid in board:
            pos = positions[pid]
            if counts[turn][pos] < need[pos]:
                rosters[turn].add(pid)
                counts[turn][pos] += 1
                turn = 1 - turn
            if all(len(r) >= roster_size for r in rosters):
                break

    players = build_players(projections, players_db, PRESETS[scoring], scoring, history,
                            include_ids=my_ids | opp_ids)
    for p in players:
        if p.player_id in my_ids:
            p.tags.add("mine")
        if p.player_id in opp_ids:
            p.tags.add("opp")
    return Slate(season=2026, week=week, scoring_name=f"{scoring.upper()} (demo data)",
                 slots=list(DEFAULT_SLOTS), players=players, my_ids=my_ids, opp_ids=opp_ids,
                 my_name="Demo Squad", opp_name="Demo Rival" if opp_ids else None,
                 notes=["using synthetic demo data - no API calls were made"])
