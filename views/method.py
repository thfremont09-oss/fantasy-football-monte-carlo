"""How it works: what the simulators do, in plain English, with the core code."""

from __future__ import annotations

import inspect

import streamlit as st

from ffmc import f1, fpl, madness, parlay, simulate
from ffmc.ui import APP_VERSION, SPORTS, banner


def eyebrow(text: str) -> None:
    st.markdown(f'<p class="eyebrow">{text}</p>', unsafe_allow_html=True)


def real_code(*fns) -> None:
    with st.expander("See the actual code"):
        for fn in fns:
            st.code(inspect.getsource(fn).rstrip(), language="python")


banner("lab", "How it works",
       "Projections give you one number. Every tool here plays the week, the race weekend or the whole tournament "
       "out a million times with real data, then shows you which choice comes out ahead most often. Here's how, "
       "in plain English, with the real code one click away.",
       chips=["The method", "How many simulations", "What goes in", "The code", "Track record"])

# ------------------------------------------------------------ how it works
eyebrow("The method")
st.header("Three steps, every sport")
steps = [
    ("1. Build a picture", "Start from real data: projections, recent games, injuries, team strength. Turn it "
                           "into a realistic range for each player or team, not just one number."),
    ("2. Play it out", "Let the computer play the games a million times. Some runs a star has a huge day, "
                       "some runs they're quiet, and some runs the underdog wins. Like real life."),
    ("3. Count the wins", "Look at all those results and count. The lineup, bracket or captain that comes "
                          "out on top most often is your best bet, and you see the odds behind it."),
]
st.markdown('<div class="grid">' + "".join(f'<div class="tile step"><b>{title}</b><p>{text}</p></div>'
                                           for title, text in steps) + "</div>", unsafe_allow_html=True)

# ------------------------------------------------------ how many simulations
st.write("")
eyebrow("Simulations")
st.header("How many simulations?")
st.write("Each run is random, so the odds wobble a little from one run to the next. The more times the "
         "games are played, the less they wobble. Every tool now plays the games a million times, which makes "
         "the odds rock-steady. A million games would fill gigabytes of memory, so they're played in batches "
         "and only the running totals are kept.")


def wobble(n: int) -> str:
    return f"±{196 * (0.25 / n) ** 0.5:.1f}"      # 95% margin on a 50% chance, in percentage points


sims = [("nfl", "NFL lineups", "weeks", "a few seconds"), ("ncaa", "March Madness", "tournaments", "about a second"),
        ("epl", "Premier League", "gameweeks", "a minute or two"), ("f1", "F1 Fantasy", "race weekends", "about 10 seconds"),
        ("bets", "Parlay Lab", "slates", "under a minute"), ("live", "Best Bets", "games per bet", "a few seconds")]
st.markdown('<div class="grid g3">' + "".join(
    f'<div class="tile" style="border-top:4px solid {SPORTS[sport]["color"]}">'
    f'<p class="eyebrow" style="color:{SPORTS[sport]["color"]}">{name}</p><div class="big">1,000,000</div>'
    f'<p>{unit} per run · takes {speed}</p>'
    f'<p>A 50% chance comes out within <b>{wobble(1_000_000)} points</b>.</p></div>'
    for sport, name, unit, speed in sims) + "</div>", unsafe_allow_html=True)
st.caption("Want a faster answer? Pick fewer simulations under Simulation settings on each tool.")

# -------------------------------------------------------------- what's used
st.write("")
eyebrow("The inputs")
st.header("What each simulator looks at")
inputs = {
    "nfl": ["ESPN's projection for every player this week", "Points scored in each of the last 6 games",
            "Injury report (questionable players sit out about 1 week in 5)", "Who plays who, so teammates and "
            "opponents rise and fall together", "Your ESPN league's scoring and lineup rules (or ESPN's defaults)"],
    "ncaa": ["The final score of every Division I game this season", "Whether each game was home, away or "
             "neutral", "Last season's ratings, early in the year", "The official bracket and results once "
             "the tournament starts"],
    "epl": ["Every club's goals scored and conceded this season", "Each player's expected goals (xG) and "
            "expected assists (xA) per 90 minutes", "How often each player starts, and their injury status",
            "Saves, defensive actions and FPL's scoring rules", "Player prices and your budget (or none)",
            "This gameweek's fixtures, including doubles and blanks"],
    "f1": ["Official F1 Fantasy prices and every driver's fantasy points per race", "Grid, finish and "
           "retirements in each driver's last 6 races", "Kalshi's odds for the race winner, podium, top 5 and top 10",
           "F1 Fantasy's scoring: qualifying, race, overtakes, fastest lap, DNFs"],
    "bets": ["DraftKings moneylines, spreads and totals for 24 leagues", "Every open Kalshi sports market: "
             "winners, spreads, totals and player props", "Each price with the bookmaker's cut removed",
             "Your risk, payout, number of legs, sports and bet types"],
}
st.markdown('<div class="grid">' + "".join(
    f'<div class="tile" style="--c:{SPORTS[sport]["color"]}"><p class="eyebrow" style="color:{SPORTS[sport]["color"]}">'
    f'{SPORTS[sport]["label"]}</p><ul>' + "".join(f"<li>{i}</li>" for i in items) + "</ul></div>"
    for sport, items in inputs.items()) + "</div>", unsafe_allow_html=True)

# --------------------------------------------------------------- the code
st.write("")
eyebrow("Under the hood")
st.header("The idea, in a few lines of code")
st.write("Simplified versions of what each simulator does, written to be read by anyone. "
         "The real code is one click away under each one.")
t_nfl, t_ncaa, t_epl, t_f1, t_bets = st.tabs(["NFL lineups", "March Madness", "Premier League", "F1 Fantasy",
                                             "Parlay Lab"])

with t_nfl:
    st.code('''# Play this week 1,000,000 times
for week in range(1_000_000):
    for player in your_players:
        # Start from the projection, then roll the dice:
        # most weeks land near it, some are huge, some are duds.
        points[player] = player.projection * random_good_or_bad_day()

        # Teammates share luck: when a QB has a big day,
        # their receivers usually do too.
        points[player] *= team_luck[player.team]

        # Listed as questionable? Some weeks they don't play.
        if player.questionable and chance(20%):
            points[player] = 0

    # Which lineup would have scored the most this time?
    remember(best_lineup(points))

# Start the lineup that came out on top most often.''', language="python")
    real_code(simulate.simulate, simulate.luck_to_points)

with t_ncaa:
    st.code('''# Step 1: rate every team from this season's scores.
# "A beat B by 12" -> A is about 12 points better than B
# (after allowing for home court). Repeat for thousands of games.
ratings = rate_teams(every_score_this_season)

# Step 2: play the whole tournament 1,000,000 times.
for tournament in range(1_000_000):
    teams_left = the_64_teams
    while more_than_one(teams_left):
        for team_a, team_b in this_rounds_games(teams_left):
            # a team 11 points better wins about 84% of the time
            chance_a_wins = win_chance(ratings[team_a] - ratings[team_b])
            winner = team_a if random() < chance_a_wins else team_b
        teams_left = this_rounds_winners
    remember(champion = teams_left[0])

# Title odds = how often each team ended up as champion.''', language="python")
    real_code(madness.fit_ratings, madness.simulate_bracket)

with t_epl:
    st.code('''# Play this gameweek 1,000,000 times
for gameweek in range(1_000_000):
    for match in this_gameweeks_fixtures:
        # How many goals? Depends on one side's attack vs. the other's defence.
        home_goals = random_goals(expected = home_attack * away_defence)
        away_goals = random_goals(expected = away_attack * home_defence)

        # Who scored? Players with higher xG get more of the goals,
        # but only if they're on the pitch that day.
        for goal in home_goals:
            scorer = pick_a_player(more_likely_if = high_xG)
            points[scorer] += goal_points[scorer.position]   # 4, 5, 6 or 10

        # Defenders and keepers get a clean sheet if the other side scored 0.
        # Then: assists, saves, defensive actions, bonus for the top 3.

    remember(best_xi(points), top_scorer(points))

# Captain = the player who topped the XI most often.''', language="python")
    real_code(fpl.simulate, fpl.player_points)

with t_f1:
    st.code('''# Each driver's pace: recent results blended with the betting market's odds.
expected_finish = blend(last_6_races, kalshi_odds_for_this_race)

# Play the race weekend 1,000,000 times
for weekend in range(1_000_000):
    for driver in grid:
        # Everyone has good and bad weekends, plus extra luck on the day.
        quali_pace[driver] = -expected_finish[driver] + weekend_luck + quali_luck
        race_pace[driver]  = -expected_finish[driver] + weekend_luck + race_luck
        if chance(driver.retirement_rate):
            race_pace[driver] = DNF                     # -20 in F1 Fantasy

    grid_order, race_order = sort(quali_pace), sort(race_pace)
    # F1 Fantasy scoring: 10 for pole, 25 for a win, +1 per place gained,
    # overtakes, fastest lap, Driver of the Day; teams score both cars.
    remember(fantasy_points(grid_order, race_order))

# Then check every team of 5 drivers + 2 constructors that fits the budget,
# with the DRS Boost (2x) on its best driver, and keep the highest scorer.''', language="python")
    real_code(f1.simulate_batch)

with t_bets:
    st.code('''# Step 1: every leg's real chance, with the bookmaker's cut taken out.
# DraftKings -150 / +130 -> 58% / 42% after removing the cut.
# If Kalshi lists the same game too, average the two.
chances = fair_chance(every_draftkings_line + every_kalshi_market)

# Step 2: play every game 1,000,000 times.
for scenario in range(1_000):
    # Our chances are estimates, so nudge each one a little per scenario.
    nudged = wiggle(chances)
    for slate in range(1_000):
        won[leg] = random() < nudged[leg]        # for every leg at once

# Step 3: score every parlay that fits your risk, payout and legs.
for parlay in candidates(your_settings):
    hit_rate = share_of_slates_where(all legs in parlay won)
    value = hit_rate * parlay.payout - 1      # profit per $1, on average

# Show the parlays with the best value (or best odds, or biggest payout).''', language="python")
    real_code(parlay.simulate)

# ------------------------------------------------------------ track record
st.write("")
eyebrow("Track record")
st.header("How it has done")
st.write("Each tool can be rerun on past weeks and tournaments using only what was known beforehand.")
m1, m2, m3 = st.columns(3, gap="medium")
m1.metric("NFL 2026, week 9: optimizer's lineup", "186.7 pts", "+8.2 vs. its own projection")
m2.metric("Best lineup possible in hindsight", "260.9 pts")
m2.caption("The optimizer's lineup captured 72% of it.")
m3.metric("2026 March Madness bracket (ESPN scoring)", "≈1,000 / 1,920")
m3.caption("Champion Michigan was its #2 title pick before the tournament.")
st.caption("Single results, not long-run averages.")

st.divider()
st.caption("Data: ESPN Fantasy (NFL), ESPN public scoreboards and news, the official Fantasy Premier League API, the "
           "official F1 Fantasy game, Formula 1 images, the Jolpica F1 database and Kalshi's public market data. Not "
           "affiliated with ESPN, DraftKings, Kalshi, the NFL, the NCAA, the Premier League or Formula 1. For "
           f"entertainment; no outcome is guaranteed. Version {APP_VERSION}.")
