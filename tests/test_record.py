from ffmc import record


def test_pre_game_records_roll_back_one_result():
    assert record._pre_game_record("6-4", True, False, False, "") == "5-4"          # won this game
    assert record._pre_game_record("1-10", False, False, False, "") == "1-9"        # lost it
    assert record._pre_game_record("10-5-3", False, True, False, "") == "10-5-2"    # hockey overtime loss
    assert record._pre_game_record("10-5-3", False, False, False, "") == "10-4-3"   # hockey regulation loss
    assert record._pre_game_record("7-3-2", None, False, True, "soccer") == "7-2-2" # soccer draw (W-D-L)
    assert record._pre_game_record("7-3-2", True, False, False, "soccer") == "6-3-2"


def test_top_calls_uses_latest_days_ranked_before_games():
    import datetime as dt
    d1, d2 = dt.date(2026, 11, 15), dt.date(2026, 11, 16)
    mk = lambda day, gap, won: record.GradedPick(day, "NBA", "X", "Y", 0.5 + gap, 0.5, 0.5, won, 1.0, "")
    rec = record.BetsRecord(picks=[mk(d2, 0.10, False)] * 4 + [mk(d1, g / 100, True) for g in range(1, 12)])
    top, days = record.top_calls(rec, 10)
    assert days == [d1, d2] and len(top) == 10            # yesterday had 4, so the day before fills it up
    assert [round(p.ours - p.ask, 2) for p in top][:5] == [0.11, 0.10, 0.10, 0.10, 0.10]
