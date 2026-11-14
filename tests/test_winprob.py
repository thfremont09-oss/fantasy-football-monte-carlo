import copy
import datetime as dt

import pytest

from ffmc import live, winprob


def game(league, sport, away_rec, home_rec, state="pre", away_score="0", home_score="0", period=0, clock=0.0,
         detail=""):
    return live.Game(id="1", sport=sport, league=league, start=dt.datetime(2026, 11, 15, tzinfo=dt.timezone.utc),
                     state=state, detail=detail, period=period, clock=clock,
                     sides=[live.Side("Away", "AWY", score=away_score, record=away_rec),
                            live.Side("Home", "HOM", score=home_score, record=home_rec)])


N = 200_000


def test_equal_teams_pregame_slight_home_edge():
    for league, sport in (("NBA", "Basketball"), ("NFL", "Football"), ("NHL", "Hockey"), ("MLB", "Baseball")):
        rec = "10-10-2" if league == "NHL" else "10-10"
        o = winprob.own_odds(game(league, sport, rec, rec), N)
        assert 0.5 < o.home < 0.62 and o.away == pytest.approx(1 - o.home)


def test_better_record_is_favoured():
    o = winprob.own_odds(game("NBA", "Basketball", "15-3", "3-15"), N)
    assert o.away > 0.75


def test_big_late_lead_is_nearly_safe_but_not_certain():
    g = game("NBA", "Basketball", "5-5", "5-5", "in", "94", "100", period=4, clock=60)
    assert 0.94 < winprob.own_odds(g, N).home < 0.995


def test_lead_matters_less_early():
    early = game("NFL", "Football", "5-5", "5-5", "in", "14", "21", period=1, clock=600)
    late = copy.deepcopy(early)
    late.period, late.clock = 4, 120
    assert winprob.own_odds(late, N).home > winprob.own_odds(early, N).home > 0.6


def test_soccer_has_draws_and_late_lead():
    pre = winprob.own_odds(game("Premier League", "Soccer", "5-3-2", "5-3-2"), N)
    assert 0.2 < pre.draw < 0.32 and pre.home > pre.away
    late = winprob.own_odds(game("Premier League", "Soccer", "5-3-2", "5-3-2", "in", "0", "1", period=2,
                                 clock=85 * 60), N)
    assert late.home > 0.85 and late.home + late.draw + late.away == pytest.approx(1)


def test_baseball_innings_left():
    g = game("MLB", "Baseball", "50-50", "50-50", "in", "2", "5", period=8, detail="Top 8th")
    assert winprob.own_odds(g, N).home > 0.85


def test_not_modelled_or_finished():
    assert winprob.own_odds(game("ATP", "Tennis", "", "")) is None
    assert winprob.own_odds(game("NBA", "Basketball", "1-1", "1-1", state="post")) is None


def test_record_parsing():
    assert winprob._share("6-4") == (0.6, 10)
    assert winprob._share("10-5-5", "soccer") == (0.625, 20)      # W-D-L
    assert winprob._share("10-5-5") == (0.625, 20)                # hockey W-L-OTL
    assert winprob._share("") is None
