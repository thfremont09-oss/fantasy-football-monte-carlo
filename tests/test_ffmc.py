import itertools

import numpy as np
import pytest

from ffmc import engine
from ffmc.cli import main
from ffmc.data import load_live, resolve_names
from ffmc.demo import demo_slate
from ffmc.lineup import (DEFAULT_SLOTS, SLOT_ELIGIBILITY, best_lineup, hindsight_optimal, parse_slots)
from ffmc.model import Player, estimate
from ffmc.scoring import PRESETS, fantasy_points
from ffmc.simulate import simulate
from ffmc.sleeper import normalize_weekly


# ----------------------------------------------------------------- scoring
def test_fantasy_points_dot_product_and_presets():
    stats = {"pass_yd": 300, "pass_td": 2, "pass_int": 1, "rush_yd": 20, "rec": 0, "pts_ppr": 99.0}
    assert fantasy_points(stats, PRESETS["std"]) == pytest.approx(12 + 8 - 1 + 2)
    assert fantasy_points(stats, PRESETS["ppr"], preset="ppr") == 99.0
    wr = {"rec": 6, "rec_yd": 80, "rec_td": 1}
    assert fantasy_points(wr, PRESETS["half"]) == pytest.approx(3 + 8 + 6)
    assert fantasy_points(wr, PRESETS["ppr"]) == pytest.approx(6 + 8 + 6)


def test_kicker_and_def_use_precomputed_totals():
    assert fantasy_points({"pts_allow": 21.5, "pts_half_ppr": 6.5}, PRESETS["half"], "DEF") == 6.5


def test_normalize_weekly_handles_both_formats():
    rows = [{"player_id": "4046", "stats": {"pts_ppr": 20}, "team": "KC", "opponent": "BUF"}]
    assert normalize_weekly(rows)["4046"]["opponent"] == "BUF"
    assert normalize_weekly({"4046": {"pts_ppr": 20}})["4046"]["stats"]["pts_ppr"] == 20


# ------------------------------------------------------------------- model
def test_estimate_blends_and_shrinks():
    mean, sd, hmean, n = estimate(20.0, [10, 12, 14, 16], "WR")
    assert hmean == 13 and n == 4
    assert mean == pytest.approx(0.75 * 20 + 0.25 * 13)
    assert sd > 0
    # no history -> positional prior
    mean, sd, _, n = estimate(10.0, None, "QB")
    assert (mean, n) == (10.0, 0) and sd == pytest.approx(4.0)


# -------------------------------------------------------------- simulation
def _p(pid, pos, team, opp, mean, sd=None, p_play=1.0):
    return Player(pid, pid, pos, team, opp, mean, sd if sd is not None else 0.5 * mean, p_play)


def test_simulation_matches_mean_and_sd():
    players = [_p("a", "WR", "AAA", "BBB", 15, 8), _p("b", "RB", "CCC", "DDD", 10, 5)]
    sims = simulate(players, 200_000, seed=0)
    assert sims[:, 0].mean() == pytest.approx(15, rel=0.02)
    assert sims[:, 0].std() == pytest.approx(8, rel=0.05)
    assert sims[:, 1].mean() == pytest.approx(10, rel=0.02)


def test_simulation_correlations_and_injuries():
    players = [_p("qb", "QB", "AAA", "BBB", 20), _p("wr", "WR", "AAA", "BBB", 15),
               _p("def", "DEF", "BBB", "AAA", 8), _p("q", "RB", "CCC", "DDD", 10, p_play=0.5)]
    sims = simulate(players, 50_000, seed=1)
    c = np.corrcoef(sims.T)
    assert c[0, 1] > 0.15            # QB & his WR boom together
    assert c[0, 2] < -0.1            # opposing DEF suffers
    assert (sims[:, 3] == 0).mean() == pytest.approx(0.5, abs=0.02)
    indep = simulate(players, 50_000, seed=1, correlated=False)
    assert abs(np.corrcoef(indep.T)[0, 1]) < 0.03


# ----------------------------------------------------------------- lineups
def _brute_force(values, positions, slots):
    best = -np.inf
    for combo in itertools.permutations(range(len(values)), len(slots)):
        if all(positions[j] in SLOT_ELIGIBILITY[s] for j, s in zip(combo, slots)):
            best = max(best, sum(values[j] for j in combo))
    return best


@pytest.mark.parametrize("seed", range(5))
def test_greedy_lineup_is_optimal(seed):
    rng = np.random.default_rng(seed)
    positions = list(rng.choice(["QB", "RB", "WR", "TE"], size=9))
    positions[:5] = ["QB", "RB", "WR", "TE", "WR"]
    values = rng.uniform(0, 30, size=9)
    slots = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"]
    lineup = best_lineup(values, positions, slots)
    assert sum(values[j] for j in lineup) == pytest.approx(_brute_force(values, positions, slots))


def test_hindsight_matches_rowwise_greedy():
    rng = np.random.default_rng(3)
    positions = ["QB", "QB", "RB", "RB", "RB", "WR", "WR", "WR", "TE", "K", "DEF"]
    sims = rng.uniform(0, 30, size=(50, len(positions)))
    slots = parse_slots(["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF", "BN", "BN"])[0]
    assert slots == DEFAULT_SLOTS
    hs = hindsight_optimal(sims, positions, slots)
    for i in range(50):
        assert list(hs[i]) == best_lineup(sims[i], positions, slots)


def test_parse_slots_reports_unsupported():
    slots, skipped = parse_slots(["QB", "W/R/T", "IDP_FLEX", "BN", "IR"])
    assert slots == ["QB", "FLEX"] and skipped == ["IDP_FLEX"]


# ------------------------------------------------------------------ engine
def test_engine_demo_matchup():
    slate = demo_slate(seed=2)
    res = engine.run(slate, n_sims=3000, seed=5)
    assert res.objective == "win"
    assert 0 <= res.win_prob <= 1
    ids = [r.player.player_id for r in res.lineup if r]
    assert len(ids) == len(set(ids)) == len(slate.slots)
    assert set(ids) <= slate.my_ids
    for slot, r in zip(res.slots, res.lineup):
        assert r.player.position in SLOT_ELIGIBILITY[slot]


def test_engine_mean_objective_takes_top_expected_players():
    slate = demo_slate(seed=2)
    res = engine.run(slate, n_sims=2000, seed=5, objective="mean")
    starters = {r.player.player_id for r in res.lineup}
    exp = {p.player_id: p.mean * p.p_play for p in slate.players}
    best_qb = max((p for p in slate.players if "mine" in p.tags and p.position == "QB"),
                  key=lambda p: exp[p.player_id])
    assert best_qb.player_id in starters


def test_dream_team_uses_all_players():
    slate = demo_slate(seed=2, with_roster=False)
    res = engine.run(slate, n_sims=2000, seed=1, dream=True)
    assert res.objective == "mean" and res.opp_lineup is None
    top_qb = max((p for p in slate.players if p.position == "QB"), key=lambda p: p.mean * p.p_play)
    assert res.lineup[0].player.player_id == top_qb.player_id


def test_cli_demo_runs(capsys):
    assert main(["--demo", "--sims", "1000", "--seed", "1"]) == 0
    assert "WIN PROBABILITY" in capsys.readouterr().out


# ------------------------------------------------- live path with fake API
class FakeClient:
    players_db = {
        "1": {"full_name": "Joe Quarterback", "position": "QB", "team": "AAA"},
        "2": {"full_name": "Rex Runner Jr.", "position": "RB", "team": "AAA"},
        "3": {"full_name": "Willy Wideout", "position": "WR", "team": "BBB", "injury_status": "Questionable"},
        "4": {"full_name": "Ted Tightend", "position": "TE", "team": "BBB"},
        "5": {"full_name": "Opp QB", "position": "QB", "team": "BBB"},
        "6": {"full_name": "Opp RB", "position": "RB", "team": "BBB"},
        "BBB": {"first_name": "Bee", "last_name": "Bees", "position": "DEF", "team": "BBB"},
    }

    def state(self):
        return {"season": "2026", "week": 10, "season_type": "regular"}

    def players(self):
        return self.players_db

    def projections(self, season, week):
        pts = {"1": 20, "2": 14, "3": 12, "4": 8, "5": 18, "6": 11, "BBB": 7}
        return {pid: {"stats": {"pts_ppr": v, "rec": 1}, "team": self.players_db[pid]["team"],
                      "opponent": "BBB" if self.players_db[pid]["team"] == "AAA" else "AAA"}
                for pid, v in pts.items()}

    def stats(self, season, week):
        return {pid: {"stats": {"pts_ppr": 10 + week % 3, "gp": 1}} for pid in self.players_db}

    def user(self, name):
        return {"user_id": "u1"}

    def league(self, lid):
        return {"name": "Test League", "scoring_settings": {"rec": 1, "pass_td": 4},
                "roster_positions": ["QB", "RB", "WR", "FLEX", "BN"]}

    def league_users(self, lid):
        return [{"user_id": "u1", "display_name": "me"}, {"user_id": "u2", "metadata": {"team_name": "Rivals"}}]

    def league_rosters(self, lid):
        return [{"roster_id": 1, "owner_id": "u1", "players": ["1", "2", "3", "4"]},
                {"roster_id": 2, "owner_id": "u2", "players": ["5", "6", "BBB"]}]

    def matchups(self, lid, week):
        return [{"roster_id": 1, "matchup_id": 7, "players": ["1", "2", "3", "4"], "starters": []},
                {"roster_id": 2, "matchup_id": 7, "players": ["5", "6", "BBB"], "starters": ["5", "6", "0", "0"]}]


def test_load_live_league_flow():
    slate = load_live(FakeClient(), league_id="L1", username="me")
    assert slate.slots == ["QB", "RB", "WR", "FLEX"]
    assert slate.my_ids == {"1", "2", "3", "4"}
    assert slate.opp_starters == ["5", "6"] and slate.opp_name == "Rivals"
    res = engine.run(slate, n_sims=2000, seed=0)
    assert [r.player.player_id for r in res.lineup] == ["1", "2", "3", "4"]
    assert res.win_prob is not None


def test_resolve_names():
    db = FakeClient.players_db
    ids, notes = resolve_names(["joe quarterback", "Rex Runner", "BBB", "Willy Widout", "Nobody"], db, set(db))
    assert ids == ["1", "2", "BBB", "3"]
    assert any("Nobody" in n for n in notes)
