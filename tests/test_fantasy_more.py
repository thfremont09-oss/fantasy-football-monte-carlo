"""College football projections and the ESPN basketball/hockey daily engine (no network)."""

import datetime as dt
import itertools

import numpy as np

from ffmc import cfb
from ffmc import espn_daily as ed


def test_box_lines_and_fantasy_points():
    summary = {"boxscore": {"players": [{"team": {"abbreviation": "OSU", "id": "194"}, "statistics": [
        {"name": "passing", "keys": ["completions/passingAttempts", "passingYards", "yardsPerPassAttempt",
                                     "passingTouchdowns", "interceptions"],
         "athletes": [{"athlete": {"id": "1", "displayName": "QB One"}, "stats": ["20/30", "300", "10", "3", "1"]}]},
        {"name": "receiving", "keys": ["receptions", "receivingYards", "yardsPerReception", "receivingTouchdowns"],
         "athletes": [{"athlete": {"id": "2", "displayName": "WR Two"}, "stats": ["8", "120", "15", "1"]}]},
    ]}]}}
    lines = cfb.box_lines(summary)
    assert lines["1"]["passAtt"] == 30 and lines["1"]["team"] == "OSU"
    assert cfb.fantasy_points(lines["1"], 1.0) == 0.04 * 300 + 4 * 3 - 2
    assert cfb.fantasy_points(lines["2"], 1.0) == 12 + 6 + 8
    assert cfb.fantasy_points(lines["2"], 0.0) == 18


def test_college_players_shrink_and_matchup_and_fbs_only():
    line = {"name": "Star", "team": "OSU", "team_id": "194", "rec": 10, "recYds": 200, "recTD": 2}
    fcs = {"name": "Small", "team": "XYZ", "team_id": "999", "rec": 10, "recYds": 200, "recTD": 2}
    history = [{"2": line, "3": fcs}, {"2": line, "3": fcs}]
    games = {"194": {"opp": "MICH", "home": True, "start": "", "implied": 35.0, "state": "pre"}}
    players = cfb.build_players(history, {"2": "WR", "3": "WR"}, games, 1.0, fbs={"194"})
    assert [p.name for p in players] == ["Star"]
    p = players[0]
    raw = 10 + 20 + 12                                 # 42 points a game
    assert p.projection < raw * 1.2 and p.projection > cfb.TYPICAL["WR"]   # pulled toward a typical WR, then
    assert p.opponent == "MICH" and p.mean > 0                             # lifted by a good betting line
    games["194"]["state"] = "in"                                           # already kicked off: can't start him
    assert cfb.build_players(history, {"2": "WR"}, games, 1.0, fbs={"194"})[0].mean == 0


def test_assign_is_exact():
    rng = np.random.default_rng(3)
    for _ in range(100):
        s, n = int(rng.integers(1, 5)), int(rng.integers(1, 6))
        vals, elig = rng.random(n) * 10, rng.random((s, n)) < 0.5
        got = ed.assign(vals, elig)
        best = max(sum(vals[j] for j in perm if j >= 0) for perm in itertools.product(range(-1, n), repeat=s)
                   if len({j for j in perm if j >= 0}) == sum(j >= 0 for j in perm)
                   and all(j < 0 or elig[i, j] for i, j in enumerate(perm)))
        assert abs(sum(vals[j] for j in got if j >= 0) - best) < 1e-9


def player(pid, team, avg, slots, pos="PG", p_play=1.0):
    return ed.DPlayer(pid, f"P{pid}", pos, f"T{team}", team, frozenset(slots), avg, avg * 0.3, p_play)


def test_daily_lineup_and_week_simulation():
    days = [ed.Day(10, dt.date(2026, 11, 20), {1: ("B", True), 2: ("A", False)}),
            ed.Day(11, dt.date(2026, 11, 21), {1: ("C", True)})]
    slots = ["PG", "UTIL"]
    a = player("a", 1, 40, {"PG", "UTIL"})
    b = player("b", 2, 30, {"PG", "UTIL"})
    c = player("c", 1, 25, {"UTIL"})
    lu = ed.day_lineup([a, b, c], slots, days[0])
    assert {p.id for p in lu} == {"a", "b"}            # c sits: a and b are better and both fit
    assert ed.week_starts([a, b, c], slots, days) == {"a": 2, "b": 1, "c": 1}
    board = ed.Board(ed.NBA, 2027, 10, days, slots, [a, b, c, player("x", 2, 10, {"PG", "UTIL"})], "test")
    board = ed.with_rosters(board, {"a", "b", "c"}, {"x"})
    out = ed.simulate_week(board, n_sims=20_000)
    assert out.win_prob > 0.99 and abs(out.my_total.mean() - (2 * 40 + 30 + 25)) < 2


def test_week_runs_to_sunday():
    sched = {1: {"abbrev": "AAA", "proGamesByScoringPeriod": {"5": [{"homeProTeamId": 1, "awayProTeamId": 2,
                                                                     "date": 1795140000000}]}},
             2: {"abbrev": "BBB", "proGamesByScoringPeriod": {"5": [{"homeProTeamId": 1, "awayProTeamId": 2,
                                                                     "date": 1795140000000}]}}}
    days = ed.week_days(sched, 5, dt.date(2026, 11, 19))            # a Thursday
    assert [d.date.weekday() for d in days] == [3, 4, 5, 6]
    assert days[0].games[1] == ("BBB", True) and days[0].games[2] == ("AAA", False)
