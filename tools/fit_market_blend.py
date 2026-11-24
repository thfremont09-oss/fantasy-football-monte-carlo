"""How much should our model move a price? Fit the weight on finished games with real Kalshi prices.

For every finished game of the last DAYS days that Kalshi priced, take Kalshi's price an hour before kick-off
and our model's pre-game chance (team ratings from games before it), and find the weight w that best predicts
the results:

    logit(fair) = logit(kalshi) + w * (logit(ours) - logit(kalshi))

w = 0 means "trust the market", w = 1 "trust our model". The fitted w per sport goes into bestbets.BLEND, and
Best Bets then shows the fair chance this implies, so an edge is what we actually expect to be real.

    python tools/fit_market_blend.py [days]
"""

from __future__ import annotations

import collections
import copy
import datetime as dt
import math
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, ".")
from ffmc import live, record, winprob  # noqa: E402
from ffmc.http import CachedJSON  # noqa: E402

FAMILY = {"Football": "Football", "Basketball": "Basketball", "Hockey": "Hockey", "Soccer": "Soccer",
          "Baseball": "Baseball"}


def logit(p):
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def collect(days: int):
    http = CachedJSON(".ffmc_cache")
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(live.EASTERN).date()
    span = [today - dt.timedelta(k) for k in range(1, days + 1)]
    leagues = [l for l in live.LEAGUES if l[0] not in ("Tennis", "MMA")]
    with ThreadPoolExecutor(4) as pool:
        found = list(pool.map(lambda j: (j[0], record._finished_games(http, j[0], j[1], today)),
                              [(lg, d) for lg in leagues for d in span]))
    by = collections.defaultdict(list)
    for lg, gs in found:
        by[lg].extend(gs)
    rows = []
    winprob.USE_INJURIES = False                  # no injury reports for past games
    for lg, gs in by.items():
        gs = list({g.key: g for g in gs}.values())
        att = [copy.deepcopy(g) for g in gs]
        live.attach_kalshi(att, record._settled_markets(http, lg[3], now - dt.timedelta(days=days + 2)), lg[3])
        for g in att:
            h = g.sides[1]
            if not h.kalshi_ticker:
                continue
            three = "soccer" if g.sport == "Soccer" else ""
            draw = g.sport == "Soccer" and not any(s.winner for s in g.sides)
            ot = any(x in (g.detail or "") for x in ("OT", "SO"))
            pre = copy.deepcopy(g)
            pre.state, pre.period, pre.clock = "pre", 0, 0.0
            for s in pre.sides:
                s.record = record._pre_game_record(s.record, None if draw else bool(s.winner), ot and not s.winner,
                                                   draw, three)
                s.score = "0"
            if not winprob.rated_margin(pre):
                continue                         # only games our ratings cover
            o = winprob.own_odds(pre, 100_000)
            if o:
                rows.append((lg[0], g, o.home, 1.0 if h.winner else 0.0))

    def price(r):
        return record._price_before(http, r[1].kalshi_series, r[1].sides[1].kalshi_ticker, r[1].start)
    with ThreadPoolExecutor(3) as pool:
        prices = list(pool.map(price, rows))
    return [(fam, ours, pr[0], y) for (fam, g, ours, y), pr in zip(rows, prices) if pr]


def fit_w(data):
    ws = np.linspace(0, 1.5, 151)

    def ll(w):
        tot = 0.0
        for _, ours, k, y in data:
            z = logit(k) + w * (logit(ours) - logit(k))
            p = min(max(1 / (1 + math.exp(-z)), 0.005), 0.995)
            tot -= y * math.log(p) + (1 - y) * math.log(1 - p)
        return tot / len(data)
    best = min(ws, key=ll)
    return float(best), ll(0.0), ll(float(best)), ll(1.0)


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 21
    data = collect(days)
    print(f"{len(data)} finished games with a Kalshi price and a rated pre-game number, last {days} days\n")
    out = {}
    for fam in sorted({d[0] for d in data}) + ["ALL"]:
        sub = [d for d in data if fam in ("ALL", d[0])]
        if len(sub) < 40:
            print(f"{fam:12s} {len(sub):4d} games: too few to fit")
            continue
        w, ll_k, ll_w, ll_o = fit_w(sub)
        print(f"{fam:12s} {len(sub):4d} games  log loss: Kalshi {ll_k:.4f} | ours {ll_o:.4f} | blend {ll_w:.4f}"
              f"  best weight on ours {w:.2f}")
        out[fam] = round(w, 2)
    print("\nBLEND =", out)
