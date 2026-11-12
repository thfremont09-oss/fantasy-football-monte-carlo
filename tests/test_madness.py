import datetime as dt

import numpy as np
import pytest

from ffmc import madness as mm
from ffmc.espn import Game


def game(home, away, hs, as_, neutral=True):
    return Game(dt.date(2026, 1, 1), home, away, hs, as_, neutral, True)


def test_fit_ratings_recovers_true_strengths():
    rng = np.random.default_rng(0)
    true = {t: r for t, r in zip("ABCDEF", [10, 5, 0, -2, -5, -8])}
    games = []
    for _ in range(40):
        for a in true:
            for b in true:
                if a < b:
                    games.append(game(a, b, 70 + true[a] - true[b] + rng.normal(0, 3), 70, neutral=True))
    est = mm.fit_ratings(games, prior_games=0.01)
    for t in true:
        assert est[t] == pytest.approx(true[t] - np.mean(list(true.values())), abs=0.5)


def test_win_probability():
    assert mm.win_probability(5, 5) == pytest.approx(0.5)
    assert mm.win_probability(11, 0) == pytest.approx(0.841, abs=0.01)   # one SD better


def test_simulation_favorite_always_wins():
    p = np.full((64, 64), 0.5)
    p[0, :], p[:, 0] = 1.0, 0.0
    odds = mm.advancement(mm.simulate_bracket(p, 2000, seed=1))
    assert odds[0].tolist() == [1.0] * 6
    assert odds[1:, 5].sum() == 0


def test_coin_flip_bracket_is_fair():
    odds = mm.advancement(mm.simulate_bracket(np.full((64, 64), 0.5), 64_000, seed=2))
    assert odds[:, 0].mean() == pytest.approx(0.5, abs=0.01)
    assert odds[:, 5].max() < 0.025 and odds[:, 5].sum() == pytest.approx(1.0)


def test_locked_results_are_respected():
    p = np.full((64, 64), 0.5)
    locked = [[1] + [-1] * 31]                     # team 1 already beat team 0
    rounds = mm.simulate_bracket(p, 500, seed=3, locked=locked)
    assert (rounds[0][:, 0] == 1).all()


def test_best_bracket_and_scoring():
    odds = np.zeros((64, 6))
    odds[:, :] = np.linspace(1, 0, 64)[:, None]   # lower index = better every round
    picks = mm.best_bracket(odds)
    assert picks[0][:2] == [0, 2] and picks[5] == [0]
    assert mm.bracket_score(picks, picks) == (1920, 1920)
    results = [[-1] * len(r) for r in picks]
    results[0][0] = 1                              # one wrong first-round pick
    assert mm.bracket_score(picks, results) == (0, 10)


def test_run_end_to_end():
    teams = [mm.Team(str(i), f"T{i}", "", 1, "East", 20 - i * 0.5) for i in range(64)]
    bracket = mm.Bracket(2026, teams, list(mm.DEFAULT_REGIONS), official=False)
    odds, picks = mm.run(bracket, 3000, seed=0)
    assert odds.shape == (64, 6)
    assert np.allclose(odds[:, 5].sum(), 1.0)
    assert picks[5][0] == int(np.argmax(odds[:, 5])) or odds[picks[5][0], 5] > 0.05
