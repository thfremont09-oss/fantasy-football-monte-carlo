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


def test_surname_matching_for_tennis():
    assert live._same("Fritz", "Taylor Fritz") and live._same("T. Fritz", "Taylor Fritz")
    assert not live._same("Fritz", "Musetti")
