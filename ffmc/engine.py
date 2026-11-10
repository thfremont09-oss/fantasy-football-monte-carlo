"""Run the Monte Carlo analysis for a slate and pick the lineup."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .data import Slate
from .lineup import (SLOT_ELIGIBILITY, best_lineup, hindsight_optimal, lineup_totals, local_search,
                     objective_fn)
from .model import Player
from .simulate import simulate


@dataclass
class PlayerResult:
    player: Player
    sim_mean: float
    p10: float
    p90: float
    start_pct: float          # % of simulations where this player was in the optimal lineup


@dataclass
class Result:
    slate: Slate
    objective: str
    n_sims: int
    slots: list[str]
    lineup: list[PlayerResult | None]
    bench: list[PlayerResult]
    totals: np.ndarray
    opp_lineup: list[PlayerResult | None] | None = None
    opp_totals: np.ndarray | None = None
    win_prob: float | None = None
    mean_lineup_points: float | None = None   # expected points of the max-mean lineup, for comparison


def prune_pool(players: list[Player], slots: list[str], keep: set[str]) -> list[Player]:
    """For the "dream team" (all NFL players), keep only plausible starters per position."""
    per_pos: dict[str, int] = {}
    for s in slots:
        for pos in SLOT_ELIGIBILITY[s]:
            per_pos[pos] = per_pos.get(pos, 0) + 1
    by_pos: dict[str, list[Player]] = {}
    for p in players:
        by_pos.setdefault(p.position, []).append(p)
    out = [p for p in players if p.player_id in keep]
    for pos, n in per_pos.items():
        ranked = sorted(by_pos.get(pos, []), key=lambda p: -p.mean * p.p_play)
        out += [p for p in ranked[: max(8, 4 * n)] if p.player_id not in keep]
    return out


def run(slate: Slate, n_sims: int = 10_000, objective: str = "auto", seed: int | None = None,
        correlated: bool = True, dream: bool = False) -> Result:
    if objective == "auto":
        objective = "win" if slate.has_opponent and not dream else "mean"
    if objective == "win" and (dream or not slate.has_opponent):
        raise ValueError("objective 'win' needs an opponent (use --league/--user or --opponent)")

    keep = set() if dream else (slate.my_ids | slate.opp_ids)
    players = prune_pool(slate.players, slate.slots, keep) if dream or not slate.has_roster else \
        [p for p in slate.players if p.player_id in keep]
    if not players:
        raise ValueError("no players to simulate")
    positions = [p.position for p in players]
    mine = np.array([dream or not slate.has_roster or "mine" in p.tags for p in players])
    opp = np.array([(not dream) and "opp" in p.tags for p in players])

    # Optimise on one set of simulations, report on an independent set so the
    # reported numbers aren't flattered by the search overfitting the noise.
    rng = np.random.default_rng(seed)
    opt_seed, eval_seed = rng.integers(0, 2**32, size=2)
    sims = simulate(players, n_sims, seed=int(opt_seed), correlated=correlated)
    eval_sims = simulate(players, n_sims, seed=int(eval_seed), correlated=correlated)

    expected = np.array([p.mean * p.p_play for p in players])
    lineup_idx = best_lineup(expected, positions, slate.slots, allowed=mine)
    mean_points = float(lineup_totals(eval_sims, lineup_idx).mean())

    opp_idx = None
    if opp.any():
        id_to_idx = {p.player_id: i for i, p in enumerate(players)}
        if slate.opp_starters:
            opp_idx = [id_to_idx.get(pid, -1) for pid in slate.opp_starters]
        else:
            opp_idx = best_lineup(expected, positions, slate.slots, allowed=opp)

    if objective != "mean":
        opp_tot = lineup_totals(sims, opp_idx) if opp_idx is not None else None
        lineup_idx = local_search(sims, positions, slate.slots, lineup_idx,
                                  objective_fn(objective, opp_tot), allowed=mine)

    totals = lineup_totals(eval_sims, lineup_idx)
    hindsight = hindsight_optimal(eval_sims, positions, slate.slots, allowed=mine)
    counts = np.bincount(hindsight[hindsight >= 0].ravel(), minlength=len(players))

    def pres(i: int) -> PlayerResult:
        col = eval_sims[:, i]
        return PlayerResult(players[i], float(col.mean()), float(np.percentile(col, 10)),
                            float(np.percentile(col, 90)), 100.0 * counts[i] / n_sims)

    lineup = [pres(i) if i >= 0 else None for i in lineup_idx]
    started = set(lineup_idx)
    bench = []
    if not dream and slate.has_roster:
        bench = sorted((pres(i) for i in np.flatnonzero(mine) if i not in started),
                       key=lambda r: -r.sim_mean)

    result = Result(slate, objective, n_sims, slate.slots, lineup, bench, totals,
                    mean_lineup_points=mean_points)
    if opp_idx is not None:
        result.opp_totals = lineup_totals(eval_sims, opp_idx)
        result.opp_lineup = [pres(i) if i >= 0 else None for i in opp_idx]
        result.win_prob = float((totals > result.opp_totals).mean()
                                + 0.5 * (totals == result.opp_totals).mean())
    return result
