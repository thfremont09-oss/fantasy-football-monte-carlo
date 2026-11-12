"""Football Monte Carlo: simulate thousands of possible NFL weeks.

Every simulated week, each player gets a random "luck" number:
  * part of it is shared with his team (a QB and his receivers boom together),
  * part is shared with his game (shootouts help both offenses),
  * a defense gets the *opposite* of the offense it faces,
  * the rest is his own.
Luck is turned into fantasy points around his expected score, and injured
players sometimes sit out.
"""

from __future__ import annotations

import numpy as np

from .model import POSITION_FLOOR, Player

# How much of each position's luck comes from its own offense, its game, and the
# offense it faces. Whatever is left over is the player's individual luck.
SHARED_LUCK = {         # (own team, game, opposing offense)
    "QB":  (0.55, 0.25, 0.0),
    "WR":  (0.40, 0.20, 0.0),
    "TE":  (0.35, 0.15, 0.0),
    "RB":  (0.35, 0.10, 0.0),
    "K":   (0.30, 0.10, 0.0),
    "DEF": (0.00, -0.20, -0.45),
}


def simulate(players: list[Player], n_sims: int = 10_000, seed: int | None = None,
             correlated: bool = True) -> np.ndarray:
    """Return points[week, player] for ``n_sims`` simulated weeks."""
    rng = np.random.default_rng(seed)

    # 1. Each player's own luck, for every simulated week.
    luck = rng.standard_normal((n_sims, len(players)))

    # 2. Mix in luck shared with teammates, the game, and the opponent.
    if correlated:
        team_luck, game_luck = {}, {}
        for i, p in enumerate(players):
            if not (p.team and p.opponent):
                continue
            game = tuple(sorted((p.team, p.opponent)))
            for key, table in ((p.team, team_luck), (p.opponent, team_luck), (game, game_luck)):
                if key not in table:
                    table[key] = rng.standard_normal(n_sims)
            w_team, w_game, w_opp = SHARED_LUCK.get(p.position, (0, 0, 0))
            own = np.sqrt(max(1 - w_team**2 - w_game**2 - w_opp**2, 0))
            luck[:, i] = (w_team * team_luck[p.team] + w_game * game_luck[game]
                          + w_opp * team_luck[p.opponent] + own * luck[:, i])

    # 3. Turn luck into fantasy points (skewed: a 40-point game is possible, -10 isn't).
    points = np.column_stack([luck_to_points(luck[:, i], p) for i, p in enumerate(players)])

    # 4. Injury coin flip: a Questionable player sits out about 1 week in 5.
    plays = rng.random(points.shape) < np.array([p.p_play for p in players])
    return np.where(plays, points, 0.0).astype(np.float32)


def luck_to_points(luck: np.ndarray, p: Player) -> np.ndarray:
    """Map standard-normal luck onto a log-normal with the player's mean and SD."""
    if p.mean <= 0:
        return np.zeros_like(luck)
    floor = POSITION_FLOOR.get(p.position, 0.0)
    m = p.mean - floor                      # mean above the floor
    s2 = np.log1p((p.sd / m) ** 2)
    return floor + m * np.exp(np.sqrt(s2) * luck - s2 / 2)
