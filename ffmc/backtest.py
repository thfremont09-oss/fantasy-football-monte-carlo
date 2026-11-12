"""Backtest: compare the simulator's pick for a past week with what actually happened."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import engine
from .data import load_live
from .lineup import best_lineup
from .model import POSITION_CV, player_name
from .scoring import PRESETS, fantasy_points
from .sleeper import SleeperClient


@dataclass
class Row:
    slot: str
    name: str
    position: str
    team: str
    predicted: float        # simulated average before the games
    actual: float           # real points scored that week


@dataclass
class Backtest:
    season: int
    week: int
    scoring: str
    predicted: list[Row]
    actual_best: list[Row]

    @property
    def predicted_total(self) -> float:
        return sum(r.actual for r in self.predicted)

    @property
    def best_total(self) -> float:
        return sum(r.actual for r in self.actual_best)

    @property
    def overlap(self) -> int:
        return len({r.name for r in self.predicted} & {r.name for r in self.actual_best})


def run_backtest(client: SleeperClient, season: int, week: int, scoring: str = "ppr",
                 slots: list[str] | None = None, n_sims: int = 10_000, seed: int | None = None,
                 history_weeks: int = 6) -> Backtest:
    # 1) Predict using only what was known before the week: that week's projections
    #    and stats from earlier weeks (load_live only reads weeks < `week`).
    slate = load_live(client, season=season, week=week, scoring=scoring, slots=slots,
                      history_weeks=history_weeks)
    # Sleeper only exposes *today's* injury report, which would leak the future
    # (a player hurt in that game may be on IR now). Players who were really out
    # that week already have ~0 projection, so ignore current injury tags.
    for p in slate.players:
        if p.mean > 0:
            p.p_play, p.injury_status = 1.0, None
    result = engine.run(slate, n_sims=n_sims, objective="mean", seed=seed, dream=True)

    # 2) Score what actually happened.
    players_db = client.players()
    rules = PRESETS[scoring]
    actual: dict[str, float] = {}
    for pid, row in client.stats(season, week).items():
        pos = players_db.get(pid, {}).get("position")
        if pos in POSITION_CV:
            actual[pid] = fantasy_points(row["stats"], rules, pos, scoring)
    pred_mean = {p.player_id: p.mean for p in slate.players}

    predicted = [Row(slot, r.player.name, r.player.position, r.player.team or "FA",
                     pred_mean[r.player.player_id],
                     actual.get(r.player.player_id, 0.0))
                 for slot, r in zip(result.slots, result.lineup) if r]

    # 3) The perfect-hindsight lineup from every player's real score.
    ids = list(actual)
    positions = [players_db[pid]["position"] for pid in ids]
    best = best_lineup(np.array([actual[i] for i in ids]), positions, slate.slots)
    actual_best = [Row(slot, player_name(players_db[ids[j]]), positions[j],
                       players_db[ids[j]].get("team") or "FA", pred_mean.get(ids[j], 0.0), actual[ids[j]])
                   for slot, j in zip(slate.slots, best) if j >= 0]
    return Backtest(season, week, slate.scoring_name, predicted, actual_best)


def render_backtest(bt: Backtest) -> str:
    def table(rows: list[Row]) -> list[str]:
        out = [f"  {'SLOT':<6} {'PLAYER':<26} {'TEAM':<5} {'PREDICTED':>9} {'ACTUAL':>8}",
               "  " + "-" * 58]
        for r in rows:
            out.append(f"  {r.slot:<6} {r.name[:26]:<26} {r.team:<5} {r.predicted:9.1f} {r.actual:8.1f}")
        out.append(f"  {'TOTAL':<6} {'':<26} {'':<5} {sum(r.predicted for r in rows):9.1f} "
                   f"{sum(r.actual for r in rows):8.1f}")
        return out

    lines = [f"\nBACKTEST - {bt.season} week {bt.week} ({bt.scoring} scoring)", "",
             "SIMULATOR'S PICK (made with pre-game data only)"]
    lines += table(bt.predicted)
    lines += ["", "ACTUAL BEST LINEUP (perfect hindsight)"]
    lines += table(bt.actual_best)
    pct = 100 * bt.predicted_total / bt.best_total if bt.best_total else 0
    lines += ["", f"  Simulator's lineup scored {bt.predicted_total:.1f} of a possible {bt.best_total:.1f} "
                  f"({pct:.0f}%), with {bt.overlap} of {len(bt.actual_best)} players in common.",
              "  PREDICTED = expected points before kickoff (0.0 = not projected to play)."]
    return "\n".join(lines)
