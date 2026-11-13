from ffmc import matchup as mu


def player(pid, pos_id, team, weeks):
    return {"id": pid, "defaultPositionId": pos_id, "proTeamId": team,
            "stats": [{"seasonId": 2026, "statSourceId": 0, "statSplitTypeId": 1, "scoringPeriodId": w,
                       "appliedTotal": pts} for w, pts in weeks.items()]}


# Team 1 plays team 2 in week 1 and team 3 in week 2.
SCHEDULE = {
    1: {"abbrev": "AAA", "proGamesByScoringPeriod": {"1": [{"homeProTeamId": 1, "awayProTeamId": 2}],
                                                   "2": [{"homeProTeamId": 3, "awayProTeamId": 1}]}},
    2: {"abbrev": "BBB", "proGamesByScoringPeriod": {"1": [{"homeProTeamId": 1, "awayProTeamId": 2}]}},
    3: {"abbrev": "CCC", "proGamesByScoringPeriod": {"2": [{"homeProTeamId": 3, "awayProTeamId": 1}]}},
}


def test_points_allowed_per_game_and_rank():
    pool = [player(10, 3, 1, {1: 20.0, 2: 8.0}),     # WR on team 1
            player(11, 3, 1, {1: 10.0, 2: 4.0}),     # another WR on team 1
            player(12, 2, 1, {1: 15.0})]             # RB on team 1
    allowed = mu.allowed_by_position(pool, SCHEDULE, 2026, week=3)
    assert allowed[(2, "WR")] == 30.0 and allowed[(3, "WR")] == 12.0 and allowed[(2, "RB")] == 15.0
    assert mu.rank_of(allowed, 2, "WR") == (30.0, 1, 2)
    assert mu.rank_of(allowed, 3, "WR") == (12.0, 2, 2)
    # Weeks from this week on don't count yet.
    assert (3, "WR") not in mu.allowed_by_position(pool, SCHEDULE, 2026, week=2)


def test_verdict_and_ordinal():
    assert mu.verdict(3, 32) == "a good matchup"
    assert mu.verdict(30, 32) == "a tough matchup"
    assert mu.verdict(16, 32) == "an average matchup"
    assert [mu.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd"]
