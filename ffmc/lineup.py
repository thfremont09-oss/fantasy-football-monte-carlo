"""Lineup slots and optimizers."""

from __future__ import annotations

from typing import Callable

import numpy as np

SLOT_ELIGIBILITY: dict[str, frozenset[str]] = {
    "QB": frozenset({"QB"}),
    "RB": frozenset({"RB"}),
    "WR": frozenset({"WR"}),
    "TE": frozenset({"TE"}),
    "K": frozenset({"K"}),
    "DEF": frozenset({"DEF"}),
    "FLEX": frozenset({"RB", "WR", "TE"}),
    "WRRB_FLEX": frozenset({"RB", "WR"}),
    "REC_FLEX": frozenset({"WR", "TE"}),
    "SUPER_FLEX": frozenset({"QB", "RB", "WR", "TE"}),
}
SLOT_ALIASES = {"W/R/T": "FLEX", "SFLEX": "SUPER_FLEX", "SF": "SUPER_FLEX", "OP": "SUPER_FLEX",
                "D/ST": "DEF", "DST": "DEF", "W/R": "WRRB_FLEX", "W/T": "REC_FLEX"}
NON_STARTING = {"BN", "IR", "TAXI"}

DEFAULT_SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"]

Objective = Callable[[np.ndarray], float]


def parse_slots(raw: list[str]) -> tuple[list[str], list[str]]:
    """Return (supported starting slots, unsupported slots that were skipped)."""
    slots, skipped = [], []
    for s in raw:
        s = SLOT_ALIASES.get(s.strip().upper(), s.strip().upper())
        if s in NON_STARTING:
            continue
        (slots if s in SLOT_ELIGIBILITY else skipped).append(s)
    return slots, skipped


def fill_order(slots: list[str]) -> list[int]:
    """Fill dedicated slots first, then flex slots from most to least restrictive.

    With nested flex sets this greedy order yields the optimal lineup.
    """
    return sorted(range(len(slots)), key=lambda i: len(SLOT_ELIGIBILITY[slots[i]]))


def eligibility_matrix(slots: list[str], positions: list[str]) -> np.ndarray:
    return np.array([[pos in SLOT_ELIGIBILITY[s] for pos in positions] for s in slots], dtype=bool)


def best_lineup(values: np.ndarray, positions: list[str], slots: list[str],
                allowed: np.ndarray | None = None) -> list[int]:
    """Greedy optimal lineup for a single value vector. Returns player index per slot (-1 = empty)."""
    elig = eligibility_matrix(slots, positions)
    if allowed is not None:
        elig &= allowed[None, :]
    used = np.zeros(len(positions), dtype=bool)
    lineup = [-1] * len(slots)
    for si in fill_order(slots):
        cand = np.where(elig[si] & ~used, values, -np.inf)
        j = int(np.argmax(cand)) if cand.size else -1
        if j >= 0 and np.isfinite(cand[j]):
            lineup[si] = j
            used[j] = True
    return lineup


def hindsight_optimal(sims: np.ndarray, positions: list[str], slots: list[str],
                      allowed: np.ndarray | None = None) -> np.ndarray:
    """For every simulated week, the lineup that would have been optimal.

    Returns an (n_sims, n_slots) int array of player indices (-1 = empty).
    """
    n, P = sims.shape
    elig = eligibility_matrix(slots, positions)
    if allowed is not None:
        elig &= allowed[None, :]
    used = np.zeros((n, P), dtype=bool)
    out = np.full((n, len(slots)), -1, dtype=int)
    rows = np.arange(n)
    for si in fill_order(slots):
        cand = np.where(elig[si][None, :] & ~used, sims, -np.inf)
        j = np.argmax(cand, axis=1)
        ok = np.isfinite(cand[rows, j])
        out[ok, si] = j[ok]
        used[rows[ok], j[ok]] = True
    return out


def lineup_totals(sims: np.ndarray, lineup: list[int]) -> np.ndarray:
    idx = [j for j in lineup if j >= 0]
    return sims[:, idx].sum(axis=1) if idx else np.zeros(sims.shape[0], dtype=sims.dtype)


def objective_fn(name: str, opponent_totals: np.ndarray | None = None) -> Objective:
    if name == "mean":
        return lambda t: float(t.mean())
    if name == "floor":
        return lambda t: float(np.percentile(t, 10)) + 1e-6 * float(t.mean())
    if name == "ceiling":
        return lambda t: float(np.percentile(t, 90)) + 1e-6 * float(t.mean())
    if name == "win":
        if opponent_totals is None:
            raise ValueError("objective 'win' needs an opponent")
        return lambda t: float((t > opponent_totals).mean() + 0.5 * (t == opponent_totals).mean()
                               + 1e-6 * t.mean())
    raise ValueError(f"unknown objective {name!r}")


def local_search(sims: np.ndarray, positions: list[str], slots: list[str], start: list[int],
                 objective: Objective, allowed: np.ndarray | None = None, max_rounds: int = 25) -> list[int]:
    """Improve a lineup by single-player swaps judged on the simulated totals.

    Used for non-linear objectives (win probability, floor, ceiling) where
    the max-expected-points lineup isn't necessarily best.
    """
    elig = eligibility_matrix(slots, positions)
    if allowed is not None:
        elig &= allowed[None, :]
    lineup = list(start)
    best = objective(lineup_totals(sims, lineup))
    for _ in range(max_rounds):
        improved = False
        base = lineup_totals(sims, lineup)
        in_lineup = set(lineup)
        for si, cur in enumerate(lineup):
            without = base - (sims[:, cur] if cur >= 0 else 0)
            for j in np.flatnonzero(elig[si]):
                if j in in_lineup:
                    continue
                score = objective(without + sims[:, j])
                if score > best + 1e-9:
                    best, lineup[si], improved = score, int(j), True
                    break
            if improved:
                break
        if not improved:
            break
    return lineup
