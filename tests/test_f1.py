import numpy as np
import pytest

from ffmc import f1


def drivers_and_teams():
    teams = ["Fast", "Mid", "Slow"]
    drivers, cons = [], []
    for t, (team, base, price) in enumerate(zip(teams, [2.0, 9.0, 17.0], [30.0, 15.0, 5.0])):
        cons.append(f1.Asset(id=f"c{t}", name=team, kind="constructor", team=team, price=price))
        for k in range(2):
            d = f1.Asset(id=f"d{t}{k}", name=f"{team} Driver {k}", kind="driver", team=team, price=price - 2 * k)
            d.exp_finish = d.exp_grid = base + 2 * k
            drivers.append(d)
    return drivers, cons


def test_points_tables():
    pos = np.array([[1, 2, 10, 11]], dtype=np.int16)
    assert f1._table(pos, f1.RACE_POINTS).tolist() == [[25, 18, 1, 0]]
    assert f1._table(pos, f1.QUALI_POINTS).tolist() == [[10, 9, 1, 0]]


def test_order_ranks_best_first():
    perf = np.array([[0.1, 3.0, -2.0]])
    assert f1._order(perf).tolist() == [[2, 1, 3]]


def test_simulated_points_follow_pace():
    drivers, cons = drivers_and_teams()
    teams = [c.team for c in cons]
    team_of = np.array([teams.index(d.team) for d in drivers])
    pts = f1.simulate_batch(np.random.default_rng(0), drivers, teams, team_of, 20_000, False, np.zeros(3))
    m = pts.mean(axis=0)
    assert pts.shape == (20_000, 9)
    assert m[0] > m[2] > m[4]                       # faster team's drivers score more
    assert m[6] > m[7] > m[8]                       # and so do their constructors
    assert pts[:, :6].min() >= f1.DNF_POINTS - 1    # nothing worse than a DNF


def test_best_team_respects_budget_and_boost():
    # 6 drivers + 3 constructors; means and prices
    means = np.array([30, 25, 20, 15, 10, 5, 50, 30, 10], dtype=float)
    prices = np.array([30, 25, 20, 10, 5, 3, 30, 15, 5], dtype=float)
    unlimited = f1.best_teams(means, prices, 6, None)[0]
    assert sorted(unlimited.drivers) == [0, 1, 2, 3, 4] and sorted(unlimited.constructors) == [6, 7]
    assert unlimited.boost == 0 and unlimited.mean == pytest.approx(100 + 30 + 80)
    capped = f1.best_teams(means, prices, 6, 100.0)[0]
    assert capped.cost <= 100
    must = f1.best_teams(means, prices, 6, 100.0, must={5})[0]
    assert 5 in must.drivers


def test_implied_finish_from_market():
    favourite = f1.implied_finish(0.5, 0.85, 0.95, 0.99, 22)
    backmarker = f1.implied_finish(0.0, 0.0, 0.01, 0.05, 22)
    assert 1 < favourite < 3 and backmarker > 13


def test_names_match_across_sources():
    assert f1._surname("Carlos Sainz Jr.") == f1._surname("Carlos Sainz") == "sainz"
    assert f1._surname("Rafael Câmara") == "camara"
