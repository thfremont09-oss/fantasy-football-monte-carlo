import datetime as dt

import pytest

from ffmc import bestbets, live


def game(dk_away, dk_home, k_away, k_home, ask_away=None, ask_home=None, rec=("5-5", "5-5")):
    g = live.Game(id="1", sport="Basketball", league="NBA", start=dt.datetime(2026, 11, 20, tzinfo=dt.timezone.utc),
                  state="pre", detail="", sides=[live.Side("Away", "AWY", record=rec[0], dk=dk_away, kalshi=k_away,
                                                           kalshi_ask=ask_away),
                                                 live.Side("Home", "HOM", record=rec[1], dk=dk_home, kalshi=k_home,
                                                           kalshi_ask=ask_home)])
    return g


def test_draftkings_bet_priced_too_generously_is_found():
    # Kalshi says the away side wins 50%; DraftKings pays +150 (40% break-even): clear value.
    g = game(150, -180, 0.50, 0.50)
    bets, checked = bestbets.best_bets([g], "DraftKings", n=200_000)
    assert checked == 2
    top = bets[0]
    assert top.pick == "Away" and top.value and top.ev > 0.1
    assert top.implied == pytest.approx(0.4)


def test_kalshi_bet_uses_draftkings_fair_chance_and_fees():
    # DraftKings (cut removed) has home about 66%; Kalshi sells home at 55 cents.
    g = game(170, -200, 0.44, 0.56, ask_away=0.46, ask_home=0.55)
    bets, _ = bestbets.best_bets([g], "Kalshi", n=200_000)
    assert bets[0].pick == "Home" and bets[0].value
    assert bets[0].payout < 1 / 0.55                     # the fee makes it pay a little less


def test_started_games_and_missing_prices_are_skipped():
    g = game(150, -180, 0.5, 0.5)
    g.state = "in"
    assert bestbets.best_bets([g], "DraftKings", n=10_000) == ([], 0)
    g2 = game(150, -180, None, None)
    assert bestbets.best_bets([g2], "DraftKings", n=10_000)[1] == 0


def test_bad_prices_are_left_out():
    g = game(100, -300, 0.30, 0.70)                     # DraftKings pays even money on a 30% shot
    bets, _ = bestbets.best_bets([g], "DraftKings", n=100_000)
    assert all(b.pick != "Away" for b in bets)


def bet(book, american=None, ask=None):
    g = game(150, -180, 0.5, 0.5)
    return bestbets.Bet(g, "Away", book, "", 2.0, 0.5, 0.5, american=american, ask=ask)


def test_draftkings_exact_payout():
    t = bet("DraftKings", american=150).ticket(10)
    assert (t.spent, t.profit, t.returned) == (10, 15.0, 25.0)
    t = bet("DraftKings", american=-200).ticket(10)
    assert (t.spent, t.profit, t.returned) == (10, 5.0, 15.0)
    t = bet("DraftKings", american=-115).ticket(10)
    assert t.profit == 8.69                                    # 10 x 100/115 = 8.6956..., rounded down


def test_kalshi_exact_payout_with_fee():
    t = bet("Kalshi", ask=0.24).ticket(10)
    # 40 contracts: 40 x 0.24 = 9.60, fee = ceil(0.07 x 40 x 0.24 x 0.76 = 0.51072) = 0.52 -> 10.12, too much
    # 39 contracts: 9.36 + ceil(0.4979...) = 0.50 -> 9.86
    assert (t.contracts, t.fee, t.spent, t.returned) == (39, 0.50, 9.86, 39.0)
    assert t.profit == pytest.approx(29.14)
    assert bet("Kalshi", ask=0.24).ticket(0.20).contracts == 0
