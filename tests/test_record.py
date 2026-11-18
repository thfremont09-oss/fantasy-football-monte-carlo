from ffmc import record


def test_pre_game_records_roll_back_one_result():
    assert record._pre_game_record("6-4", True, False, False, "") == "5-4"          # won this game
    assert record._pre_game_record("1-10", False, False, False, "") == "1-9"        # lost it
    assert record._pre_game_record("10-5-3", False, True, False, "") == "10-5-2"    # hockey overtime loss
    assert record._pre_game_record("10-5-3", False, False, False, "") == "10-4-3"   # hockey regulation loss
    assert record._pre_game_record("7-3-2", None, False, True, "soccer") == "7-2-2" # soccer draw (W-D-L)
    assert record._pre_game_record("7-3-2", True, False, False, "soccer") == "6-3-2"
