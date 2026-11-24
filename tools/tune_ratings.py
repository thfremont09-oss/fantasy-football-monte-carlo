"""Tune the team-rating settings per league with a rolling backtest, and print a TUNED table for ratings.py.

Each of the last WEEKS weeks is predicted using only games played before it (a fresh fit each week), so the
scores below are honest out-of-sample numbers. Settings are tuned one at a time (two passes) to minimise the
squared error of the predicted margin; then the margin-to-win-chance spread (sd) is fitted by log loss.

    python tools/tune_ratings.py            # all leagues
    python tools/tune_ratings.py NBA NHL    # some
"""

from __future__ import annotations

import datetime as dt
import math
import sys
from statistics import NormalDist

import numpy as np

sys.path.insert(0, ".")
from ffmc import live, ratings  # noqa: E402

WEEKS = 6
GRID = {
    "prior": [0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 30.0],
    "half_life": [21, 35, 60, 120, 365, 730],
}
CAPS = {"points": [8, 12, 16, 20, 28, 40], "goals": [1, 2, 3, 4, 6]}
EDGE_SCALE = [0.5, 0.75, 1.0, 1.5, 2.0]   # home advantage is real: never tuned away on a few weeks of games


def folds(games, today):
    starts = [today - dt.timedelta(days=7 * k) for k in range(WEEKS, 0, -1)]
    for ws in starts:
        test = [g for g in games if ws <= g[0] < ws + dt.timedelta(days=7)]
        train = [g for g in games if g[0] < ws]
        if test and len(train) > 30:
            yield ws, train, test


def _predict(name, data, tier, **kw):
    """(predicted home margin, actual margin, home won?) for every test game both teams are rated in."""
    out = []
    for ws, train, test in data:
        r = ratings.fit(name, train, ws, tier, **kw)
        if not r:
            continue
        for when, home, away, hs, as_, neutral in test:
            m = r.margin(home, away)
            if m is None:
                continue
            if neutral:
                m -= r.home_edge
            out.append((m, hs - as_, hs > as_, hs == as_))
    return out


def mse(rows):
    return float(np.mean([(m - y) ** 2 for m, y, _, _ in rows])) if rows else float("inf")


def logloss(rows, sd):
    ll = []
    for m, _, won, tie in rows:
        if tie:
            continue
        p = min(max(NormalDist().cdf(m / sd), 0.01), 0.99)
        ll.append(-math.log(p if won else 1 - p))
    return float(np.mean(ll)) if ll else float("inf")


MIN_TEST_GAMES = 80        # fewer than this and the "best" settings are mostly noise: keep the defaults


def tune(name, pool=None):
    """Tune one league, or (``pool``) several leagues together with shared settings (e.g. all soccer)."""
    today = dt.datetime.now(live.EASTERN).date()
    members = pool or [name]
    parts = []
    for lg in members:
        games = ratings.results(lg, today)
        if len(games) < 30:
            continue
        data = list(folds(games, today))
        if data:
            parts.append((lg, ratings.lower_tier(lg, games), data))
    if not parts:
        return None

    def predict(_name, _data, _tier, **kw):                 # all members, same settings
        return [row for lg, tier, data in parts for row in _predict(lg, data, tier, **kw)]
    name_for_base = members[0]
    data, tier = None, None
    base = ratings.params(name_for_base)
    unit = "goals" if base["cap"] <= 6 else "points"
    best = dict(base)
    score = mse(predict(name, data, tier, **best))
    start = score
    grid = dict(GRID, cap=CAPS[unit], home_edge=[round(base["home_edge"] * s, 3) for s in EDGE_SCALE])
    for _ in range(2):
        for key, values in grid.items():
            for v in values:
                trial = {**best, key: v}
                s = mse(predict(name, data, tier, **trial))
                if s < score - 1e-9:
                    score, best = s, trial
    rows = predict(name, data, tier, **best)
    if len(rows) < MIN_TEST_GAMES:
        print(f"{name:26s} only {len(rows)} test games: keeping the defaults", flush=True)
        return None
    sds = np.linspace(0.3, 25, 400) if unit == "points" else np.linspace(0.2, 4, 400)
    sd = float(min(sds, key=lambda x: logloss(rows, x)))
    hits = np.mean([(m > 0) == won for m, _, won, tie in rows if not tie and m != 0])
    print(f"{name:26s} games {len(rows):4d}  margin RMSE {math.sqrt(start):5.2f} -> {math.sqrt(score):5.2f}  "
          f"log loss {logloss(rows, sd):.3f}  picks right {hits:.1%}  {best} sd {sd:.2f}", flush=True)
    return {k: best[k] for k in ("cap", "prior", "home_edge", "half_life")} | {"sd": round(sd, 2)}


if __name__ == "__main__":
    soccer = [l[1] for l in live.LEAGUES if l[0] == "Soccer"]
    names = sys.argv[1:] or [l[1] for l in live.LEAGUES if l[0] not in ("Tennis", "MMA", "Soccer")] + ["Soccer"]
    table = {}
    for n in names:
        try:
            res = tune(n, soccer) if n == "Soccer" else tune(n)
        except Exception as exc:                      # one bad league shouldn't stop the rest
            print(n, "failed:", exc)
            res = None
        if res:
            table[n] = res
    print("\nTUNED = {")
    for n, v in table.items():
        print(f"    {n!r}: {v},")
    print("}")
