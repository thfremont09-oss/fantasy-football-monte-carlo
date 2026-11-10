"""Plain-text report."""

from __future__ import annotations

import numpy as np

from .engine import PlayerResult, Result

OBJECTIVE_TEXT = {
    "mean": "maximize expected points",
    "win": "maximize probability of beating your opponent",
    "floor": "maximize 10th-percentile score (safe)",
    "ceiling": "maximize 90th-percentile score (boom)",
}


def _row(slot: str, r: PlayerResult | None, show_start: bool = True) -> str:
    if r is None:
        return f"  {slot:<10} {'(empty)':<32}"
    p = r.player
    status = "" if not p.injury_status else p.injury_status
    opp = f"vs {p.opponent}" if p.opponent else ""
    line = (f"  {slot:<10} {p.name[:30]:<30} {p.team or 'FA':<4} {opp:<7} "
            f"{p.projection:6.1f} {r.sim_mean:6.1f} {r.p10:6.1f} {r.p90:6.1f}")
    if show_start:
        line += f" {r.start_pct:6.0f}%"
    return line + (f"  {status}" if status else "")


def _header(show_start: bool = True) -> str:
    h = f"  {'SLOT':<10} {'PLAYER':<30} {'TEAM':<4} {'GAME':<7} {'PROJ':>6} {'SIM':>6} {'P10':>6} {'P90':>6}"
    if show_start:
        h += f" {'START':>7}"
    return h + "\n  " + "-" * (len(h) - 2)


def _summary(label: str, totals: np.ndarray) -> str:
    p10, p50, p90 = np.percentile(totals, [10, 50, 90])
    return (f"  {label}: mean {totals.mean():.1f}  median {p50:.1f}  "
            f"10th-90th pct {p10:.1f}-{p90:.1f}  sd {totals.std():.1f}")


def render(result: Result, dream: bool = False) -> str:
    s = result.slate
    out = []
    title = "BEST POSSIBLE LINEUP (all NFL players)" if dream or not s.has_roster else \
        f"OPTIMAL LINEUP - {s.my_name}"
    out.append(f"\n{title}")
    out.append(f"Season {s.season}, week {s.week} | scoring: {s.scoring_name} | "
               f"{result.n_sims:,} simulations | goal: {OBJECTIVE_TEXT[result.objective]}")
    for note in s.notes:
        out.append(f"  note: {note}")
    out.append("")
    out.append(_header())
    for slot, r in zip(result.slots, result.lineup):
        out.append(_row(slot, r))
    out.append("")
    out.append(_summary("Lineup total", result.totals))
    if result.objective != "mean" and result.mean_lineup_points is not None:
        out.append(f"  (max-expected-points lineup would average {result.mean_lineup_points:.1f})")

    if result.bench:
        out.append("\nBENCH")
        out.append(_header())
        for r in result.bench:
            out.append(_row("BN", r))

    if result.opp_lineup is not None:
        out.append(f"\nOPPONENT - {s.opp_name or 'Opponent'}")
        out.append(_header(show_start=False))
        for slot, r in zip(result.slots, result.opp_lineup):
            out.append(_row(slot, r, show_start=False))
        out.append("")
        out.append(_summary("Opponent total", result.opp_totals))
        margin = result.totals - result.opp_totals
        out.append(f"\n  WIN PROBABILITY: {100 * result.win_prob:.1f}%   "
                   f"(expected margin {margin.mean():+.1f}, "
                   f"10th-90th pct {np.percentile(margin, 10):+.1f} to {np.percentile(margin, 90):+.1f})")

    out.append("\nPROJ = this week's projection, SIM = simulated mean (projection blended with")
    out.append("recent form, includes injury risk),")
    out.append("P10/P90 = bad/good-week outcomes, START = % of simulations in which the")
    out.append("player was part of the best possible lineup in hindsight.")
    return "\n".join(out)
