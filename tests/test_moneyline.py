from ffmc.live_view import ml_meaning, to_moneyline


def test_win_chance_to_moneyline():
    assert to_moneyline(0.76) == -317 and to_moneyline(0.24) == 317
    assert to_moneyline(0.6) == -150 and to_moneyline(0.4) == 150
    assert to_moneyline(None) is None and to_moneyline(1.0) is None


def test_moneyline_in_plain_words():
    assert ml_meaning("BOS", -360) == "BOS -360: bet $36 to win $10"
    assert ml_meaning("ORL", 287) == "ORL +287: bet $10 to win $28.70"
    assert ml_meaning("X", 102) == "X +102: bet $10 to win $10.20"
    assert ml_meaning("LAC", -229) == "LAC -229: bet $22.90 to win $10"


def test_hover_text_explains_the_money():
    from ffmc.live_view import money_tip, spread_tip, total_tip
    assert "Bet $10 and if TOR wins you win $19.90, so you get back $29.90" in money_tip(199, "TOR")
    assert "Bet $19.90 to win $10; if NY wins you get back $29.90" in money_tip(-199, "NY")
    assert money_tip(None, "X") == ""
    assert "lose by less than 2.5" in spread_tip("TENN +2.5 (-110)")
    assert "win by more than 7.5" in spread_tip("KC -7.5 (-105)")
    assert "more than 149.5" in total_tip("O/U 149.5 (o -110 / u -110)")
