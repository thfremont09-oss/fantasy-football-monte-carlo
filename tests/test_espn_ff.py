import pytest

from ffmc import engine
from ffmc import espn_ff as ef

SEASON, WEEK = 2026, 10


def espn_player(pid, name, pos_id, team, proj, actual=(10, 12, 8, 14, 11, 9), injury="ACTIVE"):
    stats = [{"seasonId": SEASON, "scoringPeriodId": WEEK, "statSourceId": 1, "statSplitTypeId": 1, "appliedTotal": proj}]
    for k, pts in enumerate(actual):
        stats.append({"seasonId": SEASON, "scoringPeriodId": WEEK - 6 + k, "statSourceId": 0,
                      "statSplitTypeId": 1, "appliedTotal": pts})
    return {"id": pid, "fullName": name, "defaultPositionId": pos_id, "proTeamId": team,
            "injuryStatus": injury, "stats": stats}


SCHEDULE = {
    1: {"id": 1, "abbrev": "ATL", "proGamesByScoringPeriod": {"10": [{"homeProTeamId": 1, "awayProTeamId": 12}]}},
    12: {"id": 12, "abbrev": "KC", "proGamesByScoringPeriod": {"10": [{"homeProTeamId": 1, "awayProTeamId": 12}]}},
    8: {"id": 8, "abbrev": "DET", "proGamesByScoringPeriod": {}},           # on bye in week 10
}

PLAYERS = [
    espn_player(101, "Kay Cee QB", 1, 12, 22.0),
    espn_player(102, "Kay Cee RB", 2, 12, 15.0, injury="QUESTIONABLE"),
    espn_player(103, "Falcon WR", 3, 1, 14.0),
    espn_player(104, "Falcon TE", 4, 1, 9.0),
    espn_player(105, "Lion RB", 2, 8, 18.0),                           # bye
    espn_player(-16012, "Chiefs D/ST", 16, 12, 7.0),
    espn_player(106, "Falcon WR2", 3, 1, 6.0),
    espn_player(201, "Falcon QB", 1, 1, 17.0),
    espn_player(202, "Falcon RB", 2, 1, 12.0),
]

LEAGUE = {
    "settings": {"name": "Test League", "rosterSettings": {"lineupSlotCounts": {
        "0": 1, "2": 1, "4": 1, "6": 1, "23": 1, "16": 1, "17": 0, "20": 6, "21": 1, "10": 1}}},
    "status": {"currentMatchupPeriod": WEEK},
    "members": [{"id": "{A}", "displayName": "alex"}, {"id": "{B}", "displayName": "sam"}],
    "teams": [
        {"id": 1, "name": "Alex's Team", "primaryOwner": "{A}", "roster": {"entries": [
            {"playerId": 101, "lineupSlotId": 0}, {"playerId": 102, "lineupSlotId": 2},
            {"playerId": 103, "lineupSlotId": 4}, {"playerId": 104, "lineupSlotId": 6},
            {"playerId": 105, "lineupSlotId": 20}, {"playerId": -16012, "lineupSlotId": 16},
            {"playerId": 106, "lineupSlotId": 20}]}},
        {"id": 2, "location": "Sam's", "nickname": "Squad", "primaryOwner": "{B}", "roster": {"entries": [
            {"playerId": 201, "lineupSlotId": 0}, {"playerId": 202, "lineupSlotId": 2}]}},
    ],
    "schedule": [{"matchupPeriodId": WEEK, "home": {"teamId": 2}, "away": {"teamId": 1}},
                 {"matchupPeriodId": WEEK + 1, "home": {"teamId": 1}, "away": {"teamId": 2}}],
}


class FakeAPI(ef.ESPNFantasy):
    def __init__(self):
        super().__init__(SEASON, cache_dir=None)
        self.calls = []

    def current_week(self):
        return WEEK

    def pro_schedule(self):
        return SCHEDULE

    def league(self, league_id, week):
        return LEAGUE

    def players(self, week, *, league_id=None, rules=3, ids=None, limit=450):
        self.calls.append((league_id, rules, tuple(ids or [])))
        pool = [p for p in PLAYERS if not ids or p["id"] in ids]
        if rules == 1 and not league_id:                 # "standard" scoring: a bit lower
            pool = [{**p, "stats": [{**s, "appliedTotal": s["appliedTotal"] - 2} for s in p["stats"]]} for p in pool]
        return pool


def test_players_get_team_opponent_injury_and_bye():
    players = {p.name: p for p in ef.to_players([PLAYERS], SEASON, WEEK, SCHEDULE)}
    qb = players["Kay Cee QB"]
    assert (qb.team, qb.opponent, qb.projection, qb.hist_games) == ("KC", "ATL", 22.0, 6)
    assert players["Kay Cee RB"].injury_status == "Questionable" and players["Kay Cee RB"].p_play == 0.8
    bye = players["Lion RB"]
    assert bye.mean == 0 and bye.p_play == 0 and bye.injury_status == "BYE"
    assert players["Chiefs D/ST"].position == "DEF"


def test_half_ppr_averages_standard_and_ppr():
    api = FakeAPI()
    slate = ef.load_default(api, "ESPN Half-PPR")
    qb = next(p for p in slate.players if p.name == "Kay Cee QB")
    assert qb.projection == pytest.approx(21.0)            # (22 + 20) / 2
    assert {c[1] for c in api.calls} == {1, 3}


def test_league_slots_roster_and_opponent():
    slate, teams = ef.load_league(FakeAPI(), "123", team_id=1)
    assert [t.name for t in teams] == ["Alex's Team", "Sam's Squad"] and teams[0].owner == "alex"
    assert sorted(slate.slots) == sorted(["QB", "RB", "WR", "TE", "FLEX", "DEF"])   # LB (IDP) slot dropped
    assert any("aren't supported" in n for n in slate.notes)
    assert slate.my_ids == {"101", "102", "103", "104", "105", "-16012", "106"}
    assert slate.opp_ids == {"201", "202"} and slate.opp_name == "Sam's Squad"
    assert slate.opp_starters == ["201", "202"]
    res = engine.run(slate, n_sims=2000, seed=1)
    assert res.win_prob is not None
    started = {r.player.name for r in res.lineup if r}
    assert "Lion RB" not in started                         # on bye, should sit


def test_team_list_only_when_no_team_chosen():
    slate, teams = ef.load_league(FakeAPI(), "123", team_id=None)
    assert len(teams) == 2 and slate.players == []


def test_cookies_normalised_and_never_cached():
    api = ef.ESPNFantasy(SEASON, cache_dir=None, espn_s2="abc", swid="1234-ABCD")
    assert api.cookies == {"espn_s2": "abc", "SWID": "{1234-ABCD}"}
    assert ef.ESPNFantasy(SEASON, cache_dir=None, espn_s2="abc", swid="").cookies is None
