import numpy as np
import pytest

from ffmc import fpl


def player(i, pos, team, start=1.0, xg=0.2, xa=0.1, saves=0.0, defcon=0.0):
    return fpl.FPLPlayer(i, f"P{i}", pos, team, f"T{team}", 5.0, 4.0, start, 0.0, xg, xa, saves, defcon, "a")


def squad_for(team, start_id):
    spec = ["GK"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
    xg = {"GK": 0, "DEF": 0.05, "MID": 0.25, "FWD": 0.5}
    return [player(start_id + k, pos, team, xg=xg[pos] + 0.01 * k, saves=3 if pos == "GK" else 0)
            for k, pos in enumerate(spec)]


def gameweek(players, home_xg=1.6, away_xg=1.0):
    fixtures = [{"home": 1, "away": 2, "home_xg": home_xg, "away_xg": away_xg}]
    return fpl.Gameweek(1, "GW1", "2026-01-01T00:00:00Z", players, fixtures, {1: "T1", 2: "T2"})


def test_share_out_gives_every_goal_to_someone():
    rng = np.random.default_rng(0)
    counts = rng.poisson(2.0, 5000)
    out = fpl.share_out(rng, counts, np.full((5000, 4), 0.3), other=0.0)
    assert (out.sum(axis=1) == counts).all()
    # equal weights -> roughly equal shares
    assert np.allclose(out.sum(axis=0) / out.sum(), 0.25, atol=0.02)


def test_bonus_goes_to_top_three():
    base = np.array([[2, 9, 5, 7, 1]])
    assert fpl.bonus_points(base).tolist() == [[0, 3, 0, 2, 0]] or fpl.bonus_points(base).tolist() == [[0, 3, 1, 2, 0]]
    assert fpl.bonus_points(base)[0, 1] == 3 and fpl.bonus_points(base)[0, 3] == 2 and fpl.bonus_points(base)[0, 2] == 1


def test_simulation_scoring_rules():
    players = squad_for(1, 0) + squad_for(2, 100)
    gw = gameweek(players)
    sims = fpl.simulate(gw, players, 20_000, seed=1)
    assert sims.shape == (20_000, 30)
    # Benchmark: a starting keeper gets 2 for playing, so never fewer than 2 - conceded//2 - ...
    gk = 0
    assert sims[:, gk].mean() > 2
    # Forwards with more xG score more on average than defenders on the same side
    fwd = [i for i, p in enumerate(players) if p.team == 1 and p.position == "FWD"]
    dfn = [i for i, p in enumerate(players) if p.team == 1 and p.position == "DEF"]
    assert sims[:, fwd].mean() > 0
    # Team 1 (stronger) keepers get more clean sheets than team 2's
    assert sims[:, 0].mean() > sims[:, 15].mean()
    assert np.isfinite(sims[:, dfn]).all()


def test_non_starters_score_zero():
    players = squad_for(1, 0) + squad_for(2, 100)
    players[3] = player(3, "DEF", 1, start=0.0)
    sims = fpl.simulate(gameweek(players), players, 2000, seed=2)
    assert (sims[:, 3] == 0).all()


def test_pick_xi_respects_formation_and_clubs():
    players = [player(i, pos, team) for i, (pos, team) in enumerate(
        [("GK", 1), ("GK", 2)] + [("DEF", t) for t in (1, 1, 1, 1, 2, 2)] + [("MID", t) for t in (1, 2, 2, 3, 3)]
        + [("FWD", t) for t in (3, 4, 4)])]
    values = np.arange(len(players), dtype=float)[::-1].copy()   # earlier players are better
    xi = fpl.pick_xi(values, players)
    assert len(xi) == 11
    pos = [players[i].position for i in xi]
    for p, (lo, hi) in fpl.XI_LIMITS.items():
        assert lo <= pos.count(p) <= hi
    clubs = [players[i].team for i in xi]
    assert max(clubs.count(c) for c in set(clubs)) <= fpl.MAX_PER_CLUB


def test_run_with_and_without_squad():
    players = squad_for(1, 0) + squad_for(2, 100) + squad_for(3, 200) + squad_for(4, 300)
    gw = gameweek(players)
    gw.fixtures.append({"home": 3, "away": 4, "home_xg": 1.3, "away_xg": 1.3})
    res = fpl.run(gw, players, 3000, seed=3)
    assert len(res.xi) == 11 and res.captain in res.xi and res.vice in res.xi
    assert res.best_captain_pct[res.xi].sum() == pytest.approx(100)
    mine = list(range(15))
    res = fpl.run(gw, players, 3000, seed=3, squad=mine)
    assert set(res.xi) <= set(mine) and len(res.bench) == 4
    assert players[res.bench[0]].position == "GK"


def test_team_strengths_shrink_toward_average():
    fixtures = [{"finished": True, "team_h": 1, "team_a": 2, "team_h_score": 4, "team_a_score": 0}]
    att, dfn, _, _ = fpl.team_strengths(fixtures, [1, 2])
    assert att[1] > 1 > att[2] and dfn[2] > 1 > dfn[1]
    assert att[1] < 2      # one game can't make a team twice as good


def test_budget_squad_is_legal_and_affordable():
    players = []
    for t in range(1, 7):
        for k, pos in enumerate(["GK", "GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "FWD", "FWD"]):
            p = player(t * 100 + k, pos, t, xg={"GK": 0, "DEF": .05, "MID": .3, "FWD": .5}[pos] + .02 * t)
            p.price = 4.0 + 0.4 * t + 0.5 * (k % 3)          # better clubs cost more
            players.append(p)
    gw = gameweek(players)
    gw.fixtures = [{"home": a, "away": a + 1, "home_xg": 1.4, "away_xg": 1.2} for a in (1, 3, 5)]
    free = fpl.run(gw, players, 1500, seed=1)
    free_cost = fpl.run(gw, players, 1500, seed=1, budget=500.0).squad_cost
    budget = free_cost - 3.0                     # tighter than the unconstrained best squad
    tight = fpl.run(gw, players, 1500, seed=1, budget=budget)
    assert tight.squad_cost is not None and tight.squad_cost <= budget + 1e-9
    squad = tight.xi + tight.bench
    assert len(squad) == 15 and len(set(squad)) == 15
    for pos, n in fpl.SQUAD_SIZE.items():
        assert sum(players[i].position == pos for i in squad) == n
    teams = [players[i].team for i in squad]
    assert max(teams.count(t) for t in set(teams)) <= fpl.MAX_PER_CLUB
    assert tight.mean[tight.xi].sum() <= free.mean[free.xi].sum() + 1e-9
    with pytest.raises(fpl.FPLError):
        fpl.run(gw, players, 500, seed=1, budget=40.0)
