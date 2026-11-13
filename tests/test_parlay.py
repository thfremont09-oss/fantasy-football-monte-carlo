import datetime as dt
import math

import pytest

from ffmc import parlay as pl

T0 = dt.datetime(2026, 11, 15, 18, tzinfo=dt.timezone.utc)


def leg(i, p, dk=None, ask=None, game=None, market="Moneyline", sport="Football", pick=None):
    return pl.Leg(key=f"l{i}", game=game or f"g{i}", sport=sport, league="L", matchup=f"m{i}", start=T0,
                  market=market, pick=pick or f"Team {i} win", p=p, kappa=200, dk_odds=dk, kalshi_ask=ask,
                  kalshi_mid=ask, sources=["DraftKings"] if dk else ["Kalshi"])


def test_odds_conversions_and_devig():
    assert pl.american_to_decimal(-150) == pytest.approx(1.6667, abs=1e-4)
    assert pl.american_to_decimal(130) == pytest.approx(2.3)
    assert pl.decimal_to_american(2.5) == "+150" and pl.decimal_to_american(1.5) == "-200"
    fair = pl._devig([-150, 130])
    assert sum(fair) == pytest.approx(1) and fair[0] == pytest.approx(0.5798, abs=1e-3)
    assert pl._devig([-110, None]) is None
    assert pl._odds("EVEN") == 100 and pl._odds("+250") == 250 and pl._odds("abc") is None


def test_market_types():
    assert pl.kalshi_market_type("KXNBAGAME") == "Moneyline"
    assert pl.kalshi_market_type("KXNCAAFSPREAD") == "Spread"
    assert pl.kalshi_market_type("KXNBATOTALPRECISE") == "Total"
    assert pl.kalshi_market_type("KXNFLRECYDS") == "Player props"


def test_risk_maps_to_minimum_hit_chance():
    assert pl.min_hit_chance(1) == pytest.approx(0.45)
    assert pl.min_hit_chance(10) == pytest.approx(0.005)
    assert pl.min_hit_chance(3) > pl.min_hit_chance(7)


def test_candidates_respect_settings():
    legs = [leg(i, p, dk=o) for i, (p, o) in enumerate([(.6, -160), (.55, -130), (.5, 100), (.4, 145), (.3, 220),
                                                       (.65, -190), (.45, 115)])]
    legs.append(leg(99, .5, dk=100, game="g0"))                    # same game as leg 0
    s = pl.Settings(app="DraftKings", risk=8, payout_range=(3, 20), legs_range=(2, 3))
    cands = pl.candidates(legs, s)
    assert cands
    for c in cands:
        assert 2 <= len(c.legs) <= 3 and 3 <= c.payout <= 20
        assert len({legs[i].game for i in c.legs}) == len(c.legs)   # one leg per game
        assert c.payout == pytest.approx(math.prod(legs[i].dk_decimal for i in c.legs))


def test_kalshi_only_legs_need_kalshi_app():
    legs = [leg(i, .5, ask=.52) for i in range(5)]
    assert pl.candidates(legs, pl.Settings(app="DraftKings", risk=8, payout_range=(2, 20))) == []
    assert pl.candidates(legs, pl.Settings(app="Kalshi", risk=8, payout_range=(2, 20)))


def test_simulated_hit_rate_matches_independent_product():
    legs = [leg(i, p, dk=100) for i, p in enumerate([.5, .6, .7])]
    par = pl.Parlay([0, 1, 2], payout=8.0, app="DraftKings", dk_payout=8.0, kalshi_payout=None)
    sim = pl.simulate(legs, [par], pl.Settings(n_show=1, stake=10), n_sims=400_000, seed=3)
    assert sim.parlays[0].hit == pytest.approx(.5 * .6 * .7, abs=0.004)
    assert sim.parlays[0].ev == pytest.approx(sim.parlays[0].hit * 8 - 1)
    assert sim.portfolio_profit.shape == (400_000,)
    assert set(sim.portfolio_profit.round(2)) <= {70.0, -10.0}


def test_merge_combines_same_bet_and_refuses_mismatched_rules():
    def dk_game(gid, home, away, ph, draw=None):
        base = dict(game=gid, sport="Soccer", league="L", matchup=f"{away} @ {home}", start=T0, market="Moneyline")
        out = [pl.Leg(key=f"{gid}:h", pick=f"{home} win", p=ph, kappa=150, dk_odds=-150, sources=["DraftKings"], **base),
               pl.Leg(key=f"{gid}:a", pick=f"{away} win", p=1 - ph - (draw or 0), kappa=150, dk_odds=200, sources=["DraftKings"], **base)]
        if draw:
            out.append(pl.Leg(key=f"{gid}:d", pick="Draw", p=draw, kappa=150, dk_odds=250, sources=["DraftKings"], **base))
        return out

    def k_game(ev, teams_p):
        return [pl.Leg(key=f"kalshi:{ev}-{t[:3].upper()}", game=f"kalshi:{ev}", sport="Soccer", league="L", matchup="x",
                       start=T0, market="Moneyline", pick=f"{t} win", p=p, kappa=100, kalshi_ask=p + .01,
                       kalshi_mid=p, sources=["Kalshi"]) for t, p in teams_p]

    # Same game, same rules (2-way), close prices -> combined.
    dk = dk_game("espn:1", "Detroit", "New England", .58)
    ks = k_game("KXNFLGAME-26NOV15NEDET", [("Detroit", .60), ("New England", .40)])
    out = pl.merge(dk, ks)
    det = next(l for l in out if l.key == "espn:1:h")
    assert det.sources == ["DraftKings", "Kalshi"] and det.p == pytest.approx(.59) and det.kalshi_ask == pytest.approx(.61)
    assert not any(l.key.startswith("kalshi:") for l in out)

    # 3-way DraftKings line (draw possible) vs 2-way Kalshi "advances" market -> kept apart.
    dk = dk_game("espn:2", "Washington", "Utah", .55, draw=.25)
    ks = k_game("KXNWSLGAME-26NOV14UTAWAS", [("Washington", .84), ("Utah", .16)])
    out = pl.merge(dk, ks)
    assert all(l.sources == ["DraftKings"] for l in out if l.key.startswith("espn:"))
    assert all(l.game == "espn:2" for l in out if l.key.startswith("kalshi:"))     # still the same game


def test_niche_scores_order_leagues_by_obscurity():
    s = pl.niche_score
    assert s("Football", "NFL") == 0 and s("Basketball", "NBA 3rd Quarter Total") == 0
    assert s("Soccer", "Premier League") == 0 and s("Soccer", "Italy Serie A") == 0
    assert s("Soccer", "German Women's Bundesliga") > 0          # women's leagues aren't "mainstream"
    assert s("Basketball", "WNBA") < s("Basketball", "Bosnia Division I") < s("Table Tennis", "Russia Liga Pro Match")
    japan_wta = s("Tennis", "ITF Women's Match - Japan (Kyoto)")
    assert japan_wta >= pl.NICHE_LEVELS[5][1]                    # the top of the Niche-o-meter
    assert s("Esports", "Valorant Map Winner") >= pl.NICHE_LEVELS[3][1]


def test_within_filters_by_days_and_market_depth():
    now = T0
    legs = [leg(1, .5, ask=.5), leg(2, .5, ask=.5), leg(3, .5, ask=.5)]
    legs[0].start = now + dt.timedelta(hours=10)
    legs[1].start = now + dt.timedelta(days=4)
    legs[2].start = now + dt.timedelta(hours=5)
    legs[2].spread = 0.25
    assert [l.key for l in pl.within(legs, 2, now=now)] == ["l1", "l3"]
    assert [l.key for l in pl.within(legs, 7, max_spread=0.2, now=now)] == ["l1", "l2"]


def test_single_bets_allowed():
    legs = [leg(i, p, ask=p + .01) for i, p in enumerate([.3, .4, .2])]
    cands = pl.candidates(legs, pl.Settings(app="Kalshi", risk=9, payout_range=(2, 10), legs_range=(1, 1)))
    assert cands and all(len(c.legs) == 1 for c in cands)
