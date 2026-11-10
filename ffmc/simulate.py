"""Monte Carlo engine: correlated fantasy-point draws for every player.

Each simulated week draws:
  * one "offense" factor per NFL team (did this offense have a big day?)
  * one "game" factor per game (shootout vs. slugfest)
  * an independent factor per player

A player's standard-normal score is a weighted mix of those factors, so a QB
and his WRs boom/bust together, and a defense suffers when the opposing
offense booms. The score is mapped onto a right-skewed (shifted log-normal)
distribution matching the player's mean and SD, then zeroed out if the
player is inactive (injury coin flip).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import POSITION_FLOOR, Player


@dataclass(frozen=True)
class Loadings:
    team: float = 0.0       # own offense factor
    game: float = 0.0       # shared game-environment factor
    opp: float = 0.0        # opposing offense factor (negative for DEF)


DEFAULT_LOADINGS = {
    "QB": Loadings(team=0.55, game=0.25),
    "WR": Loadings(team=0.40, game=0.20),
    "TE": Loadings(team=0.35, game=0.15),
    "RB": Loadings(team=0.35, game=0.10),
    "K": Loadings(team=0.30, game=0.10),
    "DEF": Loadings(opp=-0.45, game=-0.20),
}


def _lognormal_params(mean: np.ndarray, sd: np.ndarray, shift: np.ndarray):
    m = np.maximum(mean - shift, 1e-6)
    s2 = np.log1p((sd / m) ** 2)
    mu = np.log(m) - s2 / 2
    return mu, np.sqrt(s2)


def simulate(players: list[Player], n_sims: int = 10_000, seed: int | None = None,
             correlated: bool = True, loadings: dict[str, Loadings] | None = None) -> np.ndarray:
    """Return an (n_sims, n_players) float32 array of simulated fantasy points."""
    rng = np.random.default_rng(seed)
    loadings = loadings or DEFAULT_LOADINGS
    P = len(players)
    z = rng.standard_normal((n_sims, P))

    if correlated and P:
        teams = sorted({t for p in players for t in (p.team, p.opponent) if t})
        t_idx = {t: i for i, t in enumerate(teams)}
        games = sorted({tuple(sorted((p.team, p.opponent))) for p in players if p.team and p.opponent})
        g_idx = {g: i for i, g in enumerate(games)}
        team_f = rng.standard_normal((n_sims, len(teams)))
        game_f = rng.standard_normal((n_sims, len(games)))
        for j, p in enumerate(players):
            ld = loadings.get(p.position, Loadings())
            common = np.zeros(n_sims)
            used = 0.0
            if ld.team and p.team in t_idx:
                common += ld.team * team_f[:, t_idx[p.team]]
                used += ld.team**2
            if ld.opp and p.opponent in t_idx:
                common += ld.opp * team_f[:, t_idx[p.opponent]]
                used += ld.opp**2
            if ld.game and p.team and p.opponent:
                g = tuple(sorted((p.team, p.opponent)))
                common += ld.game * game_f[:, g_idx[g]]
                used += ld.game**2
            if used:
                z[:, j] = common + np.sqrt(max(1.0 - used, 0.0)) * z[:, j]

    mean = np.array([p.mean for p in players], dtype=float)
    sd = np.array([p.sd for p in players], dtype=float)
    shift = np.array([POSITION_FLOOR.get(p.position, 0.0) for p in players], dtype=float)
    p_play = np.array([p.p_play for p in players], dtype=float)

    mu, sigma = _lognormal_params(mean, sd, shift)
    pts = shift + np.exp(mu + sigma * z)
    pts[:, mean <= 0] = 0.0
    active = rng.random((n_sims, P)) < p_play
    return np.where(active, pts, 0.0).astype(np.float32)
