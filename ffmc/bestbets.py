"""Best bets right now: moneyline picks where one app's price looks too generous.

For a bet on DraftKings, the fair chance comes mainly from Kalshi's price for the
same game; for a bet on Kalshi, from DraftKings' line with the bookmaker's cut
removed. Our own Monte Carlo (records + home advantage) is blended in lightly.

Each candidate is then simulated 1,000,000 times. Every run first draws how likely
the pick really is (the fair chance is only an estimate, more uncertain when the
sources disagree) and then whether it wins, so we get its win chance, the average
profit per bet, and how confident we can be that it beats its price.

Only games that haven't started are used: DraftKings' line here is pre-game, so it
goes stale once play begins.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import winprob
from .live import Game

N_SIMS = 1_000_000
OUR_WEIGHT = 0.1          # share of our own Monte Carlo in the fair chance (it only knows records, so kept small)
MIN_SD = 0.03             # least uncertainty about any fair chance
KALSHI_FEE = 0.07         # Kalshi's trading fee: 0.07 x price x (1 - price) per contract


@dataclass
class Bet:
    game: Game
    pick: str              # team / player name, or "Draw"
    book: str              # "Kalshi" or "DraftKings"
    price: str             # "+150" or "42¢"
    payout: float          # total returned per $1 staked if it wins
    implied: float         # the chance the price implies (break-even)
    fair: float            # our fair chance
    win: float = 0.0       # simulated win chance
    ev: float = 0.0        # average profit per $1
    confidence: float = 0.0   # share of simulations where the true chance beats break-even
    value: bool = False    # clearly better than its price (positive return, 55%+ confidence)
    sources: str = ""


def _decimal(american: int) -> float:
    return 1 + (american / 100 if american > 0 else 100 / -american)


def _norm(xs: list[float | None]) -> list[float] | None:
    if any(x is None for x in xs) or not xs:
        return None
    t = sum(xs)
    return [x / t for x in xs] if t > 0 else None


def candidates(games: list[Game], book: str, our_sims: int = 100_000) -> list[Bet]:
    out = []
    for g in games:
        if g.state != "pre" or len(g.sides) != 2:
            continue
        three = g.draw_dk is not None or g.draw_kalshi is not None
        names = [s.name for s in g.sides] + (["Draw"] if three else [])
        kalshi = _norm([s.kalshi for s in g.sides] + ([g.draw_kalshi] if three else []))
        dk = g.dk_fair()
        if dk is not None and len(dk) != len(names):
            dk = None
        mine = winprob.own_odds(g, our_sims)
        ours = None
        if mine:
            ours = [mine.away, mine.home] + ([mine.draw] if three and mine.draw is not None else [])
            if len(ours) != len(names):
                ours = None
        ref, ref_name = (kalshi, "Kalshi") if book == "DraftKings" else (dk, "DraftKings (cut removed)")
        if ref is None:
            continue
        fair = [(1 - OUR_WEIGHT) * r + OUR_WEIGHT * o for r, o in zip(ref, ours)] if ours else list(ref)
        # The more the three views disagree, the less sure we are of the fair chance.
        spread = []
        for i in range(len(names)):
            vals = [v[i] for v in (kalshi, dk, ours) if v is not None]
            spread.append(max(MIN_SD, (max(vals) - min(vals)) / 2))
        for i, name in enumerate(names):
            if book == "DraftKings":
                line = g.sides[i].dk if i < 2 else g.draw_dk
                if line is None:
                    continue
                payout, price = _decimal(line), (f"+{line}" if line > 0 else str(line))
            else:
                ask = g.sides[i].kalshi_ask if i < 2 else g.draw_kalshi_ask
                if ask is None:
                    continue
                cost = ask + KALSHI_FEE * ask * (1 - ask)
                payout, price = 1 / cost, f"{ask * 100:.0f}¢"
            src = f"{ref_name}" + (" + our Monte Carlo" if ours else "")
            b = Bet(g, name, book, price, payout, 1 / payout, fair[i], sources=src)
            b.ev = fair[i] * payout - 1
            b.confidence = spread[i]           # temporarily: the uncertainty, used by simulate()
            out.append(b)
    return out


def simulate(bets: list[Bet], n: int = N_SIMS, seed: int = 5) -> list[Bet]:
    """Play each bet out ``n`` times, with the fair chance itself uncertain."""
    rng = np.random.default_rng(seed)
    for b in bets:
        p, sd = min(max(b.fair, 0.01), 0.99), b.confidence
        k = max(p * (1 - p) / (sd * sd) - 1, 2.0)           # Beta concentration with that spread
        true_p = rng.beta(p * k, (1 - p) * k, n)
        wins = rng.random(n) < true_p
        b.win = float(wins.mean())
        b.ev = float((wins * b.payout).mean() - 1)
        b.confidence = float((true_p > b.implied).mean())
    return bets


def best_bets(games: list[Game], book: str, sort: str = "value", top: int = 10, n: int = N_SIMS,
              min_win: float = 0.0) -> tuple[list[Bet], int]:
    """(the best bets, how many were checked). Bets far worse than their price are left out."""
    cands = candidates(games, book)
    hopeful = [b for b in cands if b.ev > -0.04 and b.fair >= min_win - 0.02]           # skip clear losers before the heavy simulation
    simulate(hopeful, n)
    good = [b for b in hopeful if b.ev > -0.03 and b.win >= min_win]     # value bets, or close to a fair price
    for b in good:
        b.value = b.ev > 0 and b.confidence >= 0.55
    if sort != "value":       # "most likely": favourites, but only at about a fair price or better
        good = [b for b in good if b.ev >= -0.01]
    key = (lambda b: (not b.value, -b.ev)) if sort == "value" else (lambda b: (not b.value, -b.win))
    return sorted(good, key=key)[:top], len(cands)
