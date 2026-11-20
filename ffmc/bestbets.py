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

import math
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
    american: int | None = None    # DraftKings line
    ask: float | None = None       # Kalshi price per contract (dollars)

    def ticket(self, stake: float) -> "Ticket":
        return ticket(self, stake)


@dataclass
class Ticket:
    """Exactly what a bet of a given amount costs and pays."""
    spent: float           # money that leaves your account
    returned: float        # paid back if it wins (your stake included)
    profit: float          # returned - spent
    contracts: int = 0     # Kalshi only
    fee: float = 0.0       # Kalshi only


def _cents_up(x: float) -> float:
    return math.ceil(round(x * 100, 6)) / 100


def ticket(b: "Bet", stake: float) -> Ticket:
    """DraftKings: the stake times the odds. Kalshi: whole $1 contracts at the ask, plus Kalshi's fee
    (0.07 x contracts x price x (1 - price), rounded up to the cent), as many as the stake covers."""
    if b.book == "DraftKings" and b.american is not None:
        win = stake * (b.american / 100 if b.american > 0 else 100 / -b.american)
        win = math.floor(win * 100 + 1e-6) / 100
        return Ticket(stake, round(stake + win, 2), win)
    p = b.ask or 0.0
    if p <= 0:
        return Ticket(0.0, 0.0, 0.0)
    n = int(stake // p)
    while n > 0 and n * p + _cents_up(KALSHI_FEE * n * p * (1 - p)) > stake + 1e-9:
        n -= 1
    fee = _cents_up(KALSHI_FEE * n * p * (1 - p)) if n else 0.0
    spent = round(n * p + fee, 2)
    return Ticket(spent, float(n), round(n - spent, 2), n, fee)


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
            line = ask = None
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
            b = Bet(g, name, book, price, payout, 1 / payout, fair[i], sources=src,
                    american=line if book == "DraftKings" else None, ask=ask if book == "Kalshi" else None)
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


FAIR_BAND = 0.03          # within 3% of fair counts as a fair price
SIM_POOL = 40             # how many of the best-priced bets get the full 1,000,000-run simulation


def best_bets(games: list[Game], book: str, sort: str = "value", top: int = 10, n: int = N_SIMS,
              min_win: float = 0.0) -> tuple[list[Bet], int]:
    """(the best bets, how many were checked).

    Always returns the best-priced bets that meet the minimum win chance, so the page is never empty when
    there are bets to show. Each one is labelled by ``rating``: value, fair price, or overpriced.
    """
    cands = [b for b in candidates(games, book) if b.fair >= min_win - 0.02]
    if sort == "value":
        pool = sorted(cands, key=lambda b: -b.ev)[:SIM_POOL]
    else:                     # "most likely": the likeliest winners, best price first among similar ones
        pool = sorted(cands, key=lambda b: (-round(b.fair, 2), -b.ev))[:SIM_POOL]
    simulate(pool, n)
    pool = [b for b in pool if b.win >= min_win]
    for b in pool:
        b.value = b.ev > 0 and b.confidence >= 0.55
    if sort == "value":
        key = lambda b: (not b.value, -b.ev)
    else:
        key = lambda b: (b.ev < -FAIR_BAND, -b.win)      # likeliest first, overpriced ones last
    return sorted(pool, key=key)[:top], len(candidates(games, book))


def rating(b: Bet) -> str:
    """'value', 'fair' or 'overpriced'."""
    if b.value:
        return "value"
    return "fair" if b.ev >= -FAIR_BAND else "overpriced"


# ------------------------------------------------------------------ our sim vs Kalshi
@dataclass
class Edge:
    """A team our simulations rate higher than Kalshi does."""
    game: Game
    side: object           # live.Side
    ours: float            # our simulated win chance
    kalshi: float          # Kalshi's win chance (middle of buy and sell)
    ask: float             # what one $1 Kalshi contract costs right now

    @property
    def gap(self) -> float:
        """How much higher our chance is than the price you'd pay, in percentage points / 100."""
        return self.ours - self.ask

    def ticket(self, stake: float) -> Ticket:
        return ticket(Bet(self.game, self.side.name, "Kalshi", f"{self.ask * 100:.0f}¢", 1 / self.ask, self.ask,
                          self.ours, ask=self.ask), stake)


MIN_GAMES = 8              # teams need this many games played: early-season records say too little
MAX_DISAGREEMENT = 0.25    # further than this from both Kalshi and DraftKings, and it's our blind spot, not an edge


def too_far(g: Game, i: int, ours: float, kalshi: float | None) -> bool:
    """True when our chance is more than 25 points from Kalshi's and from DraftKings' (when it has a line).

    A gap that big almost always means the model is missing something (an injury, a backup quarterback, a team
    from a lower division with an inflated record), so it isn't offered as a bet."""
    fair = g.dk_fair()
    far_kalshi = kalshi is not None and abs(ours - kalshi) > MAX_DISAGREEMENT
    far_dk = fair is None or len(fair) <= i or abs(ours - fair[i]) > MAX_DISAGREEMENT
    return far_kalshi and far_dk


def model_edges(games: list[Game], ours, top: int = 12) -> list[Edge]:
    """Teams in games that haven't started where our Monte Carlo gives a better chance than Kalshi's price.

    ``ours(game)`` returns our simulated odds (winprob.OwnOdds) or None. Only teams with a real record, and
    Kalshi prices that aren't near-certain either way, so the comparison means something.
    """
    out = []
    for g in games:
        if g.state != "pre" or len(g.sides) != 2 or g.sport in ("Tennis", "MMA"):
            continue
        if min((winprob._share(s.record) or (0, 0))[1] for s in g.sides) < MIN_GAMES:
            continue
        mine = ours(g)
        if not mine:
            continue
        for s, p in ((g.sides[0], mine.away), (g.sides[1], mine.home)):
            if s.kalshi is None or s.kalshi_ask is None or not 0.05 <= s.kalshi <= 0.95:
                continue
            if too_far(g, 0 if s is g.sides[0] else 1, p, s.kalshi):
                continue
            e = Edge(g, s, p, s.kalshi, s.kalshi_ask)
            if e.gap > 0:
                out.append(e)
    return sorted(out, key=lambda e: -e.gap)[:top]
