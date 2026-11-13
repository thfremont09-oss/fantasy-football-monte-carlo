import datetime as dt

import pytest

from ffmc import live


def team(name, abbr, home_away, score="0", winner=False):
    return {"homeAway": home_away, "score": score, "winner": winner,
            "team": {"displayName": name, "abbreviation": abbr, "logo": f"https://x/{abbr}.png"},
            "records": [{"summary": "7-2"}]}


def event(state="in", detail="Q3 5:12", with_odds=True, draw=False):
    comp = {"id": "1", "date": "2026-11-15T18:00Z", "status": {"type": {"state": state, "shortDetail": detail}},
            "competitors": [team("Detroit Lions", "DET", "home", "21"), team("New England Patriots", "NE", "away", "17")]}
    if with_odds:
        ml = {"home": {"close": {"odds": "-155"}}, "away": {"close": {"odds": "+130"}}}
        if draw:
            ml["draw"] = {"close": {"odds": "+240"}}
        comp["odds"] = [{"provider": {"name": "DraftKings"}, "moneyline": ml,
                         "pointSpread": {"home": {"close": {"line": "-2.5", "odds": "-120"}}},
                         "total": {"over": {"close": {"line": "o51.5", "odds": "+100"}},
                                   "under": {"close": {"line": "u51.5", "odds": "-120"}}}}]
    return {"id": "1", "date": comp["date"], "competitions": [comp]}


def test_game_parsing_orders_away_first_and_reads_draftkings():
    e = event()
    g = live._game(e["competitions"][0], e, "Football", "NFL")
    assert [s.short for s in g.sides] == ["NE", "DET"]
    assert g.sides[0].dk == 130 and g.sides[1].dk == -155
    assert g.sides[1].score == "21" and g.sides[1].record == "7-2"
    assert g.state == "in" and g.detail == "Q3 5:12"
    assert g.spread == "DET -2.5 (-120)" and g.total.startswith("O/U 51.5")
    fair = g.dk_fair()
    assert sum(fair) == pytest.approx(1) and fair[1] > fair[0]


def test_tennis_set_scores():
    side = live._side({"athlete": {"displayName": "Taylor Fritz"}, "linescores": [{"value": 6}, {"value": 3}]})
    assert side.name == "Taylor Fritz" and side.score == "6 3"


def test_kalshi_attaches_by_team_names_including_draw():
    e = event(draw=True)
    g = live._game(e["competitions"][0], e, "Soccer", "Premier League")
    t = "2026-11-15T20:00:00Z"
    events = {"KXEPLGAME-X": [
        {"ticker": "A", "yes_sub_title": "Detroit", "yes_bid_dollars": "0.55", "yes_ask_dollars": "0.57", "occurrence_datetime": t},
        {"ticker": "B", "yes_sub_title": "New England", "yes_bid_dollars": "0.20", "yes_ask_dollars": "0.22", "occurrence_datetime": t},
        {"ticker": "C", "yes_sub_title": "Tie", "yes_bid_dollars": "0.22", "yes_ask_dollars": "0.24", "occurrence_datetime": t}]}
    live.attach_kalshi([g], events, "KXEPLGAME")
    assert g.kalshi_updated and g.kalshi_series == "KXEPLGAME"
    assert g.sides[1].kalshi == pytest.approx(0.56) and g.sides[1].kalshi_ticker == "A"
    assert g.sides[0].kalshi == pytest.approx(0.21)
    assert g.draw_kalshi == pytest.approx(0.23) and g.draw_ticker == "C"


def test_kalshi_ignores_other_games():
    e = event()
    g = live._game(e["competitions"][0], e, "Football", "NFL")
    events = {"X": [{"ticker": "A", "yes_sub_title": "Chicago", "yes_bid_dollars": "0.5", "yes_ask_dollars": "0.52"},
                    {"ticker": "B", "yes_sub_title": "Green Bay", "yes_bid_dollars": "0.47", "yes_ask_dollars": "0.49"}]}
    live.attach_kalshi([g], events)
    assert not g.kalshi_updated and all(s.kalshi is None for s in g.sides)


def test_search_matches_teams_and_leagues():
    e = event()
    g = live._game(e["competitions"][0], e, "Football", "NFL")
    assert g.matches("lions") and g.matches("nfl patriots") and g.matches("NE")
    assert not g.matches("lakers")


SUMMARY = {
    "header": {"competitions": [{"status": {"type": {"state": "in"}}}]},
    "boxscore": {"teams": [
        {"homeAway": "home", "statistics": [{"label": "Total Yards", "displayValue": "310"}]},
        {"homeAway": "away", "statistics": [{"label": "Total Yards", "displayValue": "255"}]}]},
    "leaders": [{"team": {"abbreviation": "DET"}, "leaders": [{"displayName": "Passing Yards", "leaders": [
        {"athlete": {"displayName": "Jared Goff"}, "displayValue": "201 YDS"}]}]},
        {"team": {"abbreviation": "NE"}, "leaders": [{"displayName": "Passing Yards", "leaders": [
            {"athlete": {"displayName": "Drake Maye"}, "displayValue": "180 YDS"}]}]}],
    "predictor": {"awayTeam": {"gameProjection": "38.0"}, "homeTeam": {"gameProjection": "62.0"}},
    "plays": [{"id": "1", "wallclock": "2026-11-15T18:05:00Z", "text": "Kickoff", "period": {"number": 1},
               "clock": {"displayValue": "15:00"}},
              {"id": "2", "wallclock": "2026-11-15T18:06:00Z", "text": "Goff pass complete", "period": {"number": 1},
               "clock": {"displayValue": "14:20"}}],
    "winprobability": [{"playId": "1", "homeWinPercentage": 0.6}, {"playId": "2", "homeWinPercentage": 0.63}],
    "lastFiveGames": [{"team": {"abbreviation": "DET"}, "events": [
        {"gameResult": "W", "score": "31-20", "atVs": "vs", "opponent": {"abbreviation": "CHI"}}]}],
    "gameInfo": {"venue": {"fullName": "Ford Field"}},
    "broadcasts": [{"media": {"shortName": "FOX"}}],
}


def test_game_details_parses_espn_summary(monkeypatch):
    monkeypatch.setattr(live.CachedJSON, "get", lambda self, url, params=None, **kw: SUMMARY)
    d = live.game_details("football/nfl", "1")
    assert d.team_stats == [("Total Yards", "255", "310")] and d.stats_kind == "Game stats"
    assert d.leaders == [("Passing Yards", [("DET", "Jared Goff", "201 YDS"), ("NE", "Drake Maye", "180 YDS")])]
    assert d.predictor == pytest.approx((0.38, 0.62))
    assert [p for _, p in d.win_prob] == [0.6, 0.63] and d.win_prob[0][0].tzinfo is not None
    assert d.plays[0] == ("P1 14:20", "Goff pass complete")
    assert d.last_five == [("DET", ["W 31-20 vs CHI"])]
    assert d.venue == "Ford Field" and d.broadcast == "FOX"


def test_game_details_handles_missing_summary(monkeypatch):
    def boom(self, *a, **kw):
        raise live.APIError("404")
    monkeypatch.setattr(live.CachedJSON, "get", boom)
    d = live.game_details("mma/ufc", "1")
    assert not d.team_stats and d.predictor is None and not d.plays


def test_game_key_round_trips():
    e = event()
    g = live._game(e["competitions"][0], e, "Football", "NFL")
    g.path, g.event_id = "football/nfl", "1"
    assert g.key == "football/nfl~1~1"


def test_surname_matching_for_tennis():
    assert live._same("Fritz", "Taylor Fritz") and live._same("T. Fritz", "Taylor Fritz")
    assert not live._same("Fritz", "Musetti")


INDEX = [("Bundesliga", "132", ["Bayern Munich", "Bayern", "Munich", "", "Bayern Munich", "MUN"]),
         ("Men's College Basketball", "9", ["Grand Valley State Lakers", "GVSU", "Lakers", "Lakers"]),
         ("NBA", "13", ["Los Angeles Lakers", "Lakers", "Lakers", "Lakers", "Los Angeles", "LAL"]),
         ("Premier League", "359", ["Arsenal", "Arsenal", "Arsenal", "Arsenal", "Arsenal", "ARS"])]


def test_find_teams_prefers_pro_teams():
    assert live.find_teams("lakers", INDEX)[0] == ("NBA", "13", "Los Angeles Lakers")
    assert live.find_teams("bayern", INDEX) == [("Bundesliga", "132", "Bayern Munich")]
    assert live.find_teams("ba", INDEX) == []          # too short


def test_spelling_correction():
    assert live.correct("bayren", INDEX) == "Bayern Munich"
    assert live.correct("arsnal", INDEX) == "Arsenal"
    assert live.correct("arsenal", INDEX) is None        # already fine
    assert live.correct("qwxzv", INDEX) is None


def test_schedule_keeps_only_that_eastern_day(monkeypatch):
    e1, e2 = event(state="pre"), event(state="pre")
    e2["id"] = e2["competitions"][0]["id"] = "2"
    e1["competitions"][0]["date"] = "2026-11-15T18:00Z"     # Sun 1pm ET
    e2["competitions"][0]["date"] = "2026-11-16T03:00Z"     # Sun 10pm ET, filed under Monday by ESPN
    def fake_games(http, path, sport, name, days):
        return [g for g in (live._game(e["competitions"][0], e, sport, name) for e in (e1, e2))]
    monkeypatch.setattr(live, "espn_games", fake_games)
    monkeypatch.setattr(live, "kalshi_prices", lambda http, s: {})
    games = live.load_schedule("NFL", dt.date(2026, 11, 15))
    assert [g.id for g in games] == ["1", "2"]
    assert live.load_schedule("NFL", dt.date(2026, 11, 16)) == []
