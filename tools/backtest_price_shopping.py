"""Does buying on Kalshi when it's cheaper than DraftKings' fair price make money? A backtest.

For every finished game of the last DAYS days with both a DraftKings closing moneyline (from ESPN's game
summary) and a Kalshi price from the hour before the start, for each side:

    fair  = DraftKings' chance with the bookmaker's cut removed
    ask   = what one Kalshi contract cost
    edge  = fair - ask

Bets with edge >= each threshold are graded on the final score, with Kalshi's fee. Also reports which price
predicted results better (log loss): DraftKings fair, Kalshi, or their average.

    python tools/backtest_price_shopping.py [days]
"""

from __future__ import annotations

import collections
import copy
import datetime as dt
import math
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, ".")
from ffmc import bestbets, live, record  # noqa: E402
from ffmc.http import APIError, CachedJSON  # noqa: E402


def implied(ml: float) -> float:
    return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)


def closing_ml(http, g) -> tuple[float, float] | None:
    """(away, home) DraftKings closing moneylines from ESPN's game summary."""
    try:
        s = http.get(f"https://site.api.espn.com/apis/site/v2/sports/{g.path}/summary", [("event", g.event_id)],
                     ttl=30 * 86400)
    except APIError:
        return None
    for pc in s.get("pickcenter") or []:
        a = (pc.get("awayTeamOdds") or {}).get("moneyLine")
        h = (pc.get("homeTeamOdds") or {}).get("moneyLine")
        if a is not None and h is not None:
            return float(a), float(h)
    return None


def main(days: int):
    http = CachedJSON(".ffmc_cache")
    now = dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(live.EASTERN).date()
    leagues = [l for l in live.LEAGUES if l[0] not in ("Tennis", "MMA", "Soccer")]   # two-way markets only
    with ThreadPoolExecutor(4) as pool:
        found = list(pool.map(lambda j: (j[0], record._finished_games(http, j[0], j[1], today)),
                              [(lg, today - dt.timedelta(k)) for lg in leagues for k in range(1, days + 1)]))
    by = collections.defaultdict(list)
    for lg, gs in found:
        by[lg].extend(gs)
    games = []
    for lg, gs in by.items():
        gs = list({g.key: g for g in gs}.values())
        att = [copy.deepcopy(g) for g in gs]
        live.attach_kalshi(att, record._settled_markets(http, lg[3], now - dt.timedelta(days=days + 2)), lg[3])
        games += [(lg[1], g) for g in att if all(s.kalshi_ticker for s in g.sides) and len(g.sides) == 2]

    def gather(item):
        league, g = item
        ml = closing_ml(http, g)
        if not ml:
            return None
        prices = [record._price_before(http, g.kalshi_series, s.kalshi_ticker, g.start) for s in g.sides]
        if not all(prices):
            return None
        fa, fh = implied(ml[0]), implied(ml[1])
        fair = (fa / (fa + fh), fh / (fa + fh))
        return league, g, fair, prices
    with ThreadPoolExecutor(4) as pool:
        rows = [r for r in pool.map(gather, games) if r]
    print(f"{len(rows)} games with a DraftKings close and Kalshi prices on both sides, last {days} days\n")

    # which price predicts best?
    def ll(p, y):
        p = min(max(p, 0.01), 0.99)
        return -(y * math.log(p) + (1 - y) * math.log(1 - p))
    sums = collections.Counter()
    for league, g, fair, prices in rows:
        y = 1.0 if g.sides[1].winner else 0.0
        k = prices[1][0]
        sums["DraftKings fair"] += ll(fair[1], y)
        sums["Kalshi"] += ll(k, y)
        sums["average of both"] += ll((fair[1] + k) / 2, y)
    for name, v in sums.items():
        print(f"  log loss {name:16s} {v / len(rows):.4f}")
    print()

    for thr in (0.0, 0.02, 0.03, 0.05, 0.08):
        bets = []
        for league, g, fair, prices in rows:
            for i, s in enumerate(g.sides):
                mid, ask = prices[i]
                if 0.05 <= ask <= 0.95 and fair[i] - ask >= thr:
                    t = bestbets.ticket(bestbets.Bet(g, s.name, "Kalshi", "", 1 / ask, ask, fair[i], ask=ask), 10.0)
                    if t.contracts:
                        bets.append((fair[i], ask, s.winner, t.profit if s.winner else -t.spent, t.spent))
        if not bets:
            print(f"  edge >= {thr:.0%}: no bets")
            continue
        won = sum(b[2] for b in bets)
        staked = sum(b[4] for b in bets)
        profit = sum(b[3] for b in bets)
        print(f"  edge >= {thr:4.0%}: {len(bets):4d} bets, won {won} (fair said {sum(b[0] for b in bets):.1f}, "
              f"price said {sum(b[1] for b in bets):.1f}), profit {profit:+.2f} on {staked:.0f} ({profit / staked:+.1%})")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 21)
