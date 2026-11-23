"""Team ratings (strength of schedule) and the 'too far from the market' safeguard (no network)."""

import datetime as dt

from ffmc import bestbets, live, ratings

DAY = dt.date(2026, 11, 1)


def g(home, away, hs, as_, days_ago=10, neutral=False):
    return (DAY - dt.timedelta(days_ago), home, away, hs, as_, neutral)


def test_same_record_different_schedule():
    # A and B both go 4-0, but A beat strong teams and B beat weak ones.
    games = []
    for i in range(4):
        games += [g("A", f"Strong{i}", 24, 21), g("B", f"Weak{i}", 24, 21)]
        games += [g(f"Strong{i}", f"Weak{(i + 1) % 4}", 35, 10), g(f"Strong{i}", f"Weak{(i + 2) % 4}", 35, 10)]
    r = ratings.fit("NFL", games, DAY)
    assert r.rating["A"] > r.rating["B"] + 5


def test_lower_division_gets_its_own_average():
    # The small school wins every game against its own level, but loses badly to the big ones.
    games = []
    for i in range(5):
        games += [g("Small", f"Fcs{i}", 40, 10), g(f"Big{i}", "Small", 49, 7)]
        games += [g(f"Big{i}", f"Fcs{(i + 1) % 5}", 52, 3), g(f"Big{i}", f"Big{(i + 1) % 5}", 24, 21)]
    tier = {"Small"} | {f"Fcs{i}" for i in range(5)}
    r = ratings.fit("College Football", games, DAY, tier)
    assert r.margin("Big0", "Small") > 20          # big school at home is a heavy favourite


def test_needs_enough_games_and_skips_neutral_home_edge():
    r = ratings.fit("NBA", [g("A", "B", 100, 90, neutral=True)] * 12, DAY)
    assert r.margin("A", "C") is None              # C never played
    assert r.rating["A"] > r.rating["B"]


def side(name, kalshi, dk):
    return live.Side(name, name[:3].upper(), kalshi=kalshi, dk=dk)


def test_too_far_from_market_is_not_an_edge():
    start = dt.datetime(2026, 11, 21, 18, tzinfo=dt.timezone.utc)
    game = live.Game("1", "Football", "College Football", start, "pre", "", [side("Away", 0.06, 1400),
                                                                                 side("Home", 0.94, -5000)])
    assert bestbets.too_far(game, 0, 0.69, 0.06)       # 69% vs a 6% market: our blind spot
    assert not bestbets.too_far(game, 0, 0.12, 0.06)   # a few points off: fine


def test_team_notes_rank_schedule_and_this_season_only():
    old = [g("A", "B", 30, 0, days_ago=200), g("B", "A", 30, 0, days_ago=199)]        # last season
    now = [g("A", "C", 10, 7, days_ago=k) for k in range(1, 6)] + [g("B", "C", 3, 7, days_ago=k) for k in range(1, 6)]
    r = ratings.fit("NBA", old + now, DAY)
    a, b = r.notes["A"], r.notes["B"]
    assert (a.wins, a.losses) == (5, 0) and (b.wins, b.losses) == (0, 5)     # this season's games only
    assert a.rank < b.rank and a.of == 3 and a.last[0] == 3
