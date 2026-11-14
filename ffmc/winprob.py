"""Our own Monte Carlo win chances for a game, to compare with Kalshi and DraftKings.

It deliberately knows only a little: each side's record this season, home advantage,
and (once the game starts) the score and the clock. It then plays the rest of the
game out 1,000,000 times:

* Football and basketball: the final margin is the current margin plus the
  expected edge for the time left, plus random swings that shrink as the clock
  runs down. A tie at the end goes to overtime.
* Hockey and soccer: goals arrive at random (Poisson) at each side's scoring
  rate for the minutes left. Hockey ties go to overtime/shootout; soccer can draw.
* Baseball: runs arrive at random for the innings each side has left; ties go
  to extra innings.

Tennis and UFC aren't modelled (records don't say enough about one-off matches).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

N_SIMS = 1_000_000

# league: (spread of the final margin over a full game, periods, seconds per period, home edge in log-odds,
#          games of shrinkage toward .500 for the records)
MARGIN = {
    "NFL": (13.5, 4, 900, 0.18, 6),
    "College Football": (16.0, 4, 900, 0.35, 6),
    "NBA": (12.0, 4, 720, 0.30, 10),
    "WNBA": (11.0, 4, 600, 0.25, 10),
    "Men's College Basketball": (11.0, 2, 1200, 0.45, 8),
}
LATE_SWING = {"Basketball": 2.5, "Football": 3.5}   # points of swing that remain however little time is left
HOCKEY = {"NHL": (3.05, 3, 1200, 0.12, 10)}         # goals per team per game
BASEBALL = {"MLB": (4.5, 9, 0.15, 20)}             # runs per team per 9 innings
SOCCER_HOME, SOCCER_AWAY = 1.50, 1.15              # goals per 90 minutes for an average home / away side
SOCCER_SHRINK = 6


@dataclass
class OwnOdds:
    away: float
    home: float
    draw: float | None
    n_sims: int
    basis: str            # plain-English note on what went in


def _share(record: str, three_way: str = "") -> tuple[float, int] | None:
    """Win share and games played from 'W-L', 'W-L-OTL' (hockey) or 'W-D-L' (soccer)."""
    try:
        parts = [int(x) for x in record.split("-")]
    except ValueError:
        return None
    if len(parts) == 2:
        w, l = parts
        return (w / (w + l) if w + l else 0.5), w + l
    if len(parts) == 3:
        if three_way == "soccer":
            w, d, l = parts
        else:                                       # hockey: overtime losses count as half
            w, l, d = parts
        gp = w + d + l
        return ((w + 0.5 * d) / gp if gp else 0.5), gp
    return None


def _strength(record: str, shrink: int, three_way: str = "") -> float:
    s = _share(record, three_way)
    if s is None:
        return 0.0
    share, gp = s
    shrunk = (share * gp + 0.5 * shrink) / (gp + shrink)
    shrunk = min(max(shrunk, 0.03), 0.97)
    return math.log(shrunk / (1 - shrunk))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _score(s: str) -> int:
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def _tiebreak(rng, ties: np.ndarray, pre_home: float, n: int) -> np.ndarray:
    """Overtime / shootout / extra innings: close to a coin flip, tilted toward the better side."""
    return ties & (rng.random(n) < 0.5 + 0.5 * (pre_home - 0.5))


def margin_sport(g, rng, n: int) -> OwnOdds:
    sd, periods, length, edge, shrink = MARGIN[g.league]
    away, home = g.sides
    pre = _sigmoid(_strength(home.record, shrink) - _strength(away.record, shrink) + edge)
    full = periods * length
    if g.state == "in":
        left = g.clock + max(0, periods - g.period) * length if g.period <= periods else g.clock
        frac = min(max(left / full, 0.0), 1.0)
    else:
        frac = 1.0
    mu = sd * NormalDist().inv_cdf(min(max(pre, 1e-4), 1 - 1e-4))
    cur = _score(home.score) - _score(away.score) if g.state == "in" else 0
    # Late-game chaos (fouling, threes, onside kicks) keeps some swing even as the clock runs out.
    spread = math.sqrt(sd * sd * frac + (LATE_SWING.get(g.sport, 2.0) ** 2 if 0 < frac < 1 else 0.0))
    final = np.rint(cur + mu * frac + spread * rng.standard_normal(n))
    home_win = (final > 0) | _tiebreak(rng, final == 0, pre, n)
    p = float(home_win.mean())
    return OwnOdds(1 - p, p, None, n, _basis(g, frac))


def _poisson_game(rng, n: int, lam_home: float, lam_away: float, cur_home: int, cur_away: int):
    h = cur_home + rng.poisson(lam_home, n)
    a = cur_away + rng.poisson(lam_away, n)
    return h, a


def _solve_delta(pre: float, base_h: float, base_a: float) -> float:
    """Strength gap (log scale) that makes a full game's home win chance (ties split) match ``pre``."""
    k = np.arange(30)
    lo, hi = -4.0, 4.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lh, la = base_h * math.exp(mid / 2), base_a * math.exp(-mid / 2)
        ph = np.exp(-lh) * lh ** k / np.array([math.factorial(int(i)) for i in k])
        pa = np.exp(-la) * la ** k / np.array([math.factorial(int(i)) for i in k])
        joint = np.outer(ph, pa)
        win = np.tril(joint, -1).sum() + 0.5 * np.trace(joint)
        lo, hi = (mid, hi) if win < pre else (lo, mid)
    return (lo + hi) / 2


def hockey(g, rng, n: int) -> OwnOdds:
    rate, periods, length, edge, shrink = HOCKEY[g.league]
    away, home = g.sides
    pre = _sigmoid(_strength(home.record, shrink) - _strength(away.record, shrink) + edge)
    delta = _solve_delta(pre, rate, rate)
    full = periods * length
    if g.state == "in":
        left = g.clock + max(0, periods - g.period) * length if g.period <= periods else 0.0
        frac = min(max(left / full, 0.0), 1.0)
    else:
        frac = 1.0
    h, a = _poisson_game(rng, n, rate * math.exp(delta / 2) * frac, rate * math.exp(-delta / 2) * frac,
                         _score(home.score) if g.state == "in" else 0, _score(away.score) if g.state == "in" else 0)
    home_win = (h > a) | _tiebreak(rng, h == a, pre, n)
    p = float(home_win.mean())
    return OwnOdds(1 - p, p, None, n, _basis(g, frac))


def _innings_left(g) -> tuple[float, float]:
    """Half-innings left for (away, home), from 'Top 5th' / 'Bot 5th' / 'Mid 5th' / 'End 5th'."""
    if g.state != "in":
        return 9.0, 9.0
    inn = max(g.period, 1)
    d = g.detail.lower()
    if d.startswith("top"):
        away, home = 9 - inn + 0.5, 9 - inn + 1
    elif d.startswith("mid"):
        away, home = 9 - inn, 9 - inn + 1
    elif d.startswith("bot"):
        away, home = 9 - inn, 9 - inn + 0.5
    else:                                            # end of an inning
        away, home = 9 - inn, 9 - inn
    return max(away, 0.0), max(home, 0.0)


def baseball(g, rng, n: int) -> OwnOdds:
    rate, innings, edge, shrink = BASEBALL[g.league]
    away, home = g.sides
    pre = _sigmoid(_strength(home.record, shrink) - _strength(away.record, shrink) + edge)
    delta = _solve_delta(pre, rate, rate)
    a_left, h_left = _innings_left(g)
    live = g.state == "in"
    h, a = _poisson_game(rng, n, rate * math.exp(delta / 2) * h_left / innings,
                         rate * math.exp(-delta / 2) * a_left / innings,
                         _score(home.score) if live else 0, _score(away.score) if live else 0)
    home_win = (h > a) | _tiebreak(rng, h == a, pre, n)
    p = float(home_win.mean())
    return OwnOdds(1 - p, p, None, n, _basis(g, (a_left + h_left) / (2 * innings)))


def soccer(g, rng, n: int) -> OwnOdds:
    away, home = g.sides
    delta = _strength(home.record, SOCCER_SHRINK, "soccer") - _strength(away.record, SOCCER_SHRINK, "soccer")
    if g.state == "in":
        frac = min(max((5400 - g.clock) / 5400, 0.02), 1.0)
    else:
        frac = 1.0
    live = g.state == "in"
    h, a = _poisson_game(rng, n, SOCCER_HOME * math.exp(delta / 2) * frac, SOCCER_AWAY * math.exp(-delta / 2) * frac,
                         _score(home.score) if live else 0, _score(away.score) if live else 0)
    return OwnOdds(float((a > h).mean()), float((h > a).mean()), float((h == a).mean()), n, _basis(g, frac))


def _basis(g, frac: float) -> str:
    recs = " and ".join(s.record for s in g.sides if s.record) or "no records yet"
    if g.state == "in":
        return f"records ({recs}), home advantage, the score and about {frac:.0%} of the game left"
    return f"records ({recs}) and home advantage"


def own_odds(g, n_sims: int = N_SIMS, seed: int = 11) -> OwnOdds | None:
    """Our Monte Carlo win chances for a game, or None if we don't model that sport (or it's over)."""
    if g.state == "post" or len(g.sides) != 2:
        return None
    rng = np.random.default_rng(seed)
    if g.league in MARGIN:
        return margin_sport(g, rng, n_sims)
    if g.league in HOCKEY:
        return hockey(g, rng, n_sims)
    if g.league in BASEBALL:
        return baseball(g, rng, n_sims)
    if g.sport == "Soccer":
        return soccer(g, rng, n_sims)
    return None
