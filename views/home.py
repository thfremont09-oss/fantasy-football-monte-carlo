"""Home page: what the simulators do, what data they use, and the core code."""

from __future__ import annotations

import inspect

import pandas as pd
import streamlit as st

from ffmc import madness, model, simulate

FOOTBALL = "views/football.py"
MADNESS = "views/march_madness.py"


def section_label(text: str) -> None:
    st.markdown(f'<p class="eyebrow">{text}</p>', unsafe_allow_html=True)


def source(fn) -> str:
    return inspect.getsource(fn).rstrip()


# --------------------------------------------------------------------- hero
section_label("Simulation-based sports tools")
st.markdown('<h1 class="hero">Every game, played ten thousand times.</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="lead">Two tools for the decisions that come with a sports season: who to start in '
    "your fantasy lineup this week, and how to fill out your March Madness bracket. Neither one "
    "takes a projection at face value. Each builds its own model from real data, simulates the "
    "outcome thousands of times, and reports how often each choice actually comes out ahead.</p>",
    unsafe_allow_html=True)

c1, c2 = st.columns(2, gap="medium")
with c1, st.container(border=True):
    section_label("NFL · Weekly")
    st.subheader("Fantasy Football Lineup Optimizer")
    st.write("Pick the lineup with the best expected score or the best chance of beating this "
             "week's opponent. Connect a Sleeper league, or enter a roster from any site.")
    with st.container(key="card_link_football"):
        st.page_link(FOOTBALL, label="Open the lineup optimizer", icon=":material/arrow_forward:", width="stretch")
with c2, st.container(border=True):
    section_label("NCAA Men's Tournament · March")
    st.subheader("March Madness Bracket Simulator")
    st.write("Title odds for every team, round-by-round chances and a complete bracket. It shows a "
             "projected field until Selection Sunday, then switches to the official bracket.")
    with st.container(key="card_link_madness"):
        st.page_link(MADNESS, label="Open the bracket simulator", icon=":material/arrow_forward:", width="stretch")

# ------------------------------------------------------------- how it works
st.divider()
section_label("Method")
st.header("How a simulation works")
steps = [
    ("1  Estimate", "Turn raw data into a model: an expected score and a range for each player, or a "
                    "strength rating for each team."),
    ("2  Simulate", "Draw thousands of random outcomes from that model, including the things that "
                    "move together: a quarterback and his receivers, a defense and the offense it faces."),
    ("3  Decide", "Count the results. Choose the lineup or bracket that wins most often, and report "
                  "the odds instead of a single guess."),
]
for col, (title, text) in zip(st.columns(3, gap="medium"), steps):
    col.markdown(f"**{title}**")
    col.write(text)

# ----------------------------------------------------------------- football
st.divider()
section_label("Fantasy football")
st.header("The lineup model")
st.write("Data refreshes hourly from Sleeper's public API. The current NFL week is detected "
         "automatically.")

st.subheader("What goes in")
st.dataframe(pd.DataFrame([
    ["Weekly stat projections", "Sleeper", f"Expected points ({model.PROJECTION_WEIGHT:.0%} of the estimate)"],
    ["Points in each of the last 6 games", "Sleeper", f"Recent form ({1 - model.PROJECTION_WEIGHT:.0%}) "
                                                      "and how much the player's scores swing"],
    ["Injury report", "Sleeper", "Chance the player is active (Questionable "
                                 f"{model.PLAY_PROBABILITY['Questionable']:.0%}, Doubtful "
                                 f"{model.PLAY_PROBABILITY['Doubtful']:.0%}, Out 0%)"],
    ["Team and opponent", "Sleeper", "Which players' outcomes move together"],
    ["League scoring and lineup slots", "Your Sleeper league, or PPR / Half / Standard / ESPN",
     "Points per stat and which positions can fill each slot"],
], columns=["Input", "Source", "How it's used"]), hide_index=True, width="stretch")

st.subheader("Assumptions by position")
rows = []
for pos, (w_team, w_game, w_opp) in simulate.SHARED_LUCK.items():
    rows.append([pos, f"{model.POSITION_CV[pos]:.0%}", f"{w_team ** 2:.0%}", f"{w_game ** 2:.0%}",
                 f"{w_opp ** 2:.0%}" + (" (inverse)" if w_opp < 0 else ""), f"{model.POSITION_FLOOR[pos]:+.0f}"])
st.dataframe(pd.DataFrame(rows, columns=[
    "Position", "Typical weekly swing", "Shared with own offense", "Shared with game",
    "Shared with opposing offense", "Score floor"]), hide_index=True, width="stretch")
st.caption("Typical weekly swing is the starting estimate of a player's standard deviation as a share of "
           "the player's expected points, blended with the player's own recent games. The shared columns are the "
           "share of a player's week-to-week variation that comes from each common factor.")

st.subheader("The simulation")
st.code(source(simulate.simulate), language="python")
with st.expander("How random draws become fantasy points"):
    st.code(source(simulate.luck_to_points), language="python")

# -------------------------------------------------------------- march madness
st.divider()
section_label("March Madness")
st.header("The bracket model")
st.write("Every Division I game of the season, from ESPN's public scoreboard, refreshed during the day.")

st.subheader("What goes in")
st.dataframe(pd.DataFrame([
    ["Final score of every Division I game", "ESPN", "Team power ratings (least squares on scoring margin)"],
    ["Home, away or neutral site", "ESPN", "Separates home-court advantage from team strength"],
    ["Last season's ratings", "ESPN", "Starting point early in the season, phased out as games are played"],
    ["Official bracket, seeds and results", "ESPN", "Field and matchups; games already played are locked in"],
], columns=["Input", "Source", "How it's used"]), hide_index=True, width="stretch")

st.subheader("From ratings to win chances")
st.write(f"A single game's margin varies by about {madness.GAME_SD:.0f} points around the rating difference.")
gaps = [0, 3, 6, 11, 15, 20]
st.dataframe(pd.DataFrame({
    "Rating difference": [f"{g} pts" for g in gaps],
    "Better team wins": [f"{madness.win_probability(g, 0):.0%}" for g in gaps],
}).set_index("Rating difference").T, width="stretch")

st.subheader("The code")
st.code(source(madness.fit_ratings), language="python")
st.code(source(madness.simulate_bracket), language="python")

# ---------------------------------------------------------------- track record
st.divider()
section_label("Track record")
st.header("How it has done")
st.write("Both tools can be run on past weeks and past tournaments, using only the data that "
         "existed before the games.")
m1, m2, m3 = st.columns(3, gap="medium")
m1.metric("NFL 2026, week 9: optimizer's lineup", "186.7 pts", "+8.2 vs. its own projection")
m2.metric("Best lineup possible in hindsight", "260.9 pts")
m2.caption("The optimizer's lineup captured 72% of it.")
m3.metric("2026 tournament bracket (ESPN scoring)", "≈1,000 / 1,920")
m3.caption("Champion Michigan was its #2 title pick before the tournament.")
st.caption("Single results, not long-run averages. Run the football backtest for any completed week with "
           "python -m ffmc --backtest --week N.")

# --------------------------------------------------------------------- footer
st.divider()
st.caption("Data: Sleeper public API (NFL) and ESPN public scoreboard (college basketball). "
           "Not affiliated with Sleeper, ESPN, the NFL or the NCAA. For entertainment; no outcome is "
           "guaranteed.")
