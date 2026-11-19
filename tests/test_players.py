"""Player Stats: search ranking, reading ESPN's rows, game logs, key numbers and fun facts (no network)."""

import datetime as dt

from ffmc import players
from ffmc.http import APIError


class FakeHTTP:
    def __init__(self, routes):
        self.routes = routes

    def get(self, url, params=None, ttl=0, **kw):
        q = dict(params or [])
        key = url.rsplit("/", 1)[-1] + (f"?{q['query']}" if "query" in q else "") + \
            (f"?season={q['season']}" if "season" in q else "")
        if key not in self.routes:
            raise APIError(f"no route {key}")
        return self.routes[key]


def item(name, pid, league="nfl", sport="football", team="New England Patriots", pos="QB"):
    return {"type": "player", "id": pid, "displayName": name, "sport": sport, "league": league,
            "label": f"{league.upper()} - {team}", "position": {"abbreviation": pos},
            "teamRelationships": [{"type": "team", "displayName": team, "core": {"id": "17", "abbreviation": "NE"}}]}


def test_search_survives_typos_by_searching_each_word():
    http = FakeHTTP({"search?drak maye": {"items": []},
                     "search?drak": {"items": [item("Drake London", "1", team="Atlanta Falcons"), item("Drake Maye", "2")]},
                     "search?maye": {"items": [item("Drake Maye", "2"), item("Luke Maye", "3", "nba-development",
                                                                           "basketball", "Wisconsin Herd", "F")]}})
    found = players.search("drak maye", http)
    assert found[0].name == "Drake Maye"
    assert len({p.key for p in found}) == len(found)


def test_value_reads_made_attempted_columns():
    names = ["minutes", "fieldGoalsMade-fieldGoalsAttempted", "points"]
    vals = ["31", "8-16", "22"]
    assert players._value(names, vals, "fieldGoalsMade") == "8"
    assert players._value(names, vals, "fieldGoalsAttempted") == "16"
    assert players._value(names, vals, "points") == "22"
    assert players._num("2,330") == 2330 and players._num("-") is None


def test_milestones_only_when_close():
    assert players._milestone(9000) == 10000
    assert players._milestone(4861) == 5000
    assert players._milestone(6000) is None
    assert players._milestone(20) is None


def log(games):
    """A gamelog feed: games = [(id, iso date, opp, atVs, result, score, passingYards, passingTDs)]."""
    return {
        "names": ["passingYards", "passingTouchdowns"],
        "labels": ["YDS", "TD"], "displayNames": ["Passing Yards", "Passing Touchdowns"],
        "events": {g[0]: {"gameDate": g[1], "opponent": {"displayName": g[2], "abbreviation": g[2]}, "atVs": g[3],
                          "gameResult": g[4], "score": g[5]} for g in games},
        "seasonTypes": [{"displayName": "2026 Regular Season", "categories": [
            {"type": "event", "displayName": "Regular Season Stats",
             "events": [{"eventId": g[0], "stats": [str(g[6]), str(g[7])]} for g in games]}]},
            {"displayName": "2026 Preseason", "categories": [
                {"type": "event", "displayName": "Preseason", "events": [{"eventId": "pre", "stats": ["999", "9"]}]}]}],
    }


def test_profile_key_numbers_and_facts():
    games = [("6", "2026-11-15T18:00:00Z", "DET", "vs", "L", "35-10", 150, 1),
             ("5", "2026-11-08T18:00:00Z", "GB", "vs", "W", "27-20", 300, 2),
             ("4", "2026-11-01T18:00:00Z", "MIA", "@", "W", "24-19", 280, 3),
             ("3", "2026-10-25T18:00:00Z", "CHI", "@", "L", "30-24", 200, 1),
             ("2", "2026-10-18T18:00:00Z", "NYJ", "vs", "W", "26-19", 310, 2),
             ("1", "2026-10-11T18:00:00Z", "LV", "@", "L", "20-17", 180, 0)]
    data = log(games)
    data["events"]["pre"] = {"gameDate": "2026-08-20T18:00:00Z", "opponent": {"abbreviation": "X"}}
    stats = {"categories": [{"name": "passing", "displayName": "Passing", "labels": ["GP", "YDS", "TD"],
                             "names": ["gamesPlayed", "passingYards", "passingTouchdowns"],
                             "totals": ["40", "9,500", "64"],
                             "statistics": [{"season": {"displayName": "2026"}, "stats": ["6", "1,420", "9"]}]}]}
    overview = {"statistics": {"names": ["passingYards"], "labels": ["YDS"], "displayNames": ["Passing Yards"],
                               "splits": [{"displayName": "Projected", "stats": ["3,900"]}]}}
    http = FakeHTTP({"overview": overview, "stats": stats, "gamelog": data})
    p = players.Player("2", "Drake Maye", "football", "nfl", "NFL - New England Patriots", "New England Patriots", "")
    pr = players.profile(p, http)
    assert len(pr.games) == 6 and pr.last_game.opp_abbr == "DET"          # preseason left out, newest first
    yards = pr.keys[0]
    assert (yards.name, yards.season, yards.last, yards.career) == ("passingYards", "1,420", "150", "9,500")
    text = " ".join(pr.facts)
    assert "Season high: **310 passing yards** vs NYJ" in text
    assert "3-3 in games Maye has played" in text
    assert "On pace for **3,900 passing yards**" in text
    assert "500 passing yards away from **10,000 career passing yards**" in text
    assert [t.rows[-1][0] for t in pr.seasons] == ["Career"]


def test_suggestions_merge_leaders_and_popular_names():
    leader = {"leaders": {"categories": [{"leaders": [
        {"athlete": {"id": "3139477", "displayName": "Patrick Mahomes", "position": {"abbreviation": "QB"}},
         "team": {"abbreviation": "KC"}},
        {"athlete": {"id": "3139477", "displayName": "Patrick Mahomes", "position": {"abbreviation": "QB"}},
         "team": {"abbreviation": "KC"}}]}]}}
    http = FakeHTTP({"leaders": leader})
    s = players.suggestions(http)
    mahomes = [x for x in s if x.name == "Patrick Mahomes"]
    assert len(mahomes) == 1 and mahomes[0].label.endswith("NFL QB · KC") and mahomes[0].key.endswith("3139477")
    assert any(x.label == "Erling Haaland · Soccer" for x in s)
    assert len({x.label for x in s}) == len(s)
