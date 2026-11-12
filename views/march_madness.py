"""March Madness page: Monte Carlo bracket simulator."""

from __future__ import annotations

import datetime as dt

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from ffmc import madness as mm
from ffmc.espn import ESPNClient
from ffmc.http import APIError
from ffmc.ui import SPORTS, banner

BAR_COLOR = SPORTS["ncaa"]["color"]


@st.cache_data(ttl=1800, show_spinner="Downloading this season's college basketball scores...")
def load(season: int, day: dt.date) -> mm.Bracket:   # `day` refreshes the cache daily
    return mm.load_bracket(ESPNClient(".ffmc_cache"), season)


@st.cache_data(show_spinner=False)
def simulate(bracket: mm.Bracket, n_sims: int, seed: int, game_sd: float):
    return mm.run(bracket, n_sims=n_sims, seed=seed, game_sd=game_sd)


def label(t: mm.Team) -> str:
    return f"({t.seed}) {t.name}"


# ---------------------------------------------------------------- sidebar
current = mm.current_season()
seasons = [s for s in range(current, 2018, -1) if s != 2020]   # no tournament in 2020
st.sidebar.header("Bracket settings")
season = st.sidebar.selectbox("Tournament", seasons,
                              format_func=lambda s: f"{s} (this season)" if s == current else str(s))
with st.sidebar.expander("Simulation settings"):
    n_sims = st.select_slider("Simulated tournaments", [1000, 5000, 10000, 25000, 50000], value=10000)
    game_sd = st.slider("Upset level", 8.0, 14.0, mm.GAME_SD, 0.5,
                        help="How many points a single game swings by chance. Higher = more upsets.")
    seed = st.number_input("Random seed", 0, 10**6, 42, key="mm_seed")

# ------------------------------------------------------------------ data
banner("ncaa", "March Madness",
       "The whole 64-team bracket, played out thousands of times. Team ratings come from every Division I "
       "score this season; each game is a weighted coin flip based on the gap between two teams.")
try:
    bracket = load(season, dt.date.today())
except APIError as exc:
    st.error(f"Couldn't reach ESPN: {exc}")
    st.stop()

if not bracket.official:
    st.info(f"**Projected bracket.** The real {season} bracket is announced on Selection Sunday in "
            "mid-March. Until then this shows the 64 best teams by our ratings, and it switches to the "
            "official bracket automatically once it's out.")
elif bracket.complete:
    st.success(f"**{season} tournament is over.** The odds below use only games played *before* the "
               "tournament, so you can see how the model would have done.")
elif any(w >= 0 for r in bracket.results for w in r):
    st.info("**Tournament in progress.** Games already played are locked in; the rest are simulated.")
else:
    st.info(f"**Official {season} bracket.**")
for note in bracket.notes:
    if not note.startswith("Projected field"):
        st.caption(note)

odds, picks = simulate(bracket, n_sims, int(seed), float(game_sd))
teams = bracket.teams

# --------------------------------------------------------------- headline
fav = int(np.argmax(odds[:, 5]))
champ = picks[5][0]
cols = st.columns(3)
cols[0].metric("Title favorite", teams[fav].name)
cols[0].caption(f"{100 * odds[fav, 5]:.0f}% to win it all")
cols[1].metric("Bracket's champion pick", label(teams[champ]))
if bracket.results:
    earned, possible = mm.bracket_score(picks, bracket.results)
    if possible:
        cols[2].metric("Bracket score (ESPN points)", f"{earned} / {possible}")
        cols[2].caption(f"{100 * earned / possible:.0f}% of available points")
    if bracket.complete:
        st.caption(f"Actual champion: **{label(teams[bracket.results[5][0]])}**")

tab_odds, tab_bracket, tab_teams, tab_h2h = st.tabs(["Title odds", "Best bracket", "All teams", "Head to head"])

# --------------------------------------------------------------- title odds
with tab_odds:
    top = np.argsort(-odds[:, 5])[:16]
    df = pd.DataFrame({"Team": [label(teams[i]) for i in top], "Title chance %": (100 * odds[top, 5]).round(1),
                       "Final Four %": (100 * odds[top, 3]).round(1), "Region": [teams[i].region for i in top]})
    chart = alt.Chart(df).mark_bar(color=BAR_COLOR, cornerRadiusEnd=4, height=18).encode(
        x=alt.X("Title chance %:Q", title=f"Chance to win the title (share of {n_sims:,} simulated tournaments)"),
        y=alt.Y("Team:N", sort=list(df["Team"]), title=None, axis=alt.Axis(labelLimit=220)),
        tooltip=["Team", "Region", "Title chance %", "Final Four %"],
    ).properties(height=alt.Step(28))
    text = chart.mark_text(align="left", dx=4, color="gray").encode(text=alt.Text("Title chance %:Q", format=".1f"))
    st.altair_chart(chart + text, width="stretch")

# -------------------------------------------------------------- best bracket
def mark(r: int, slot: int, pick: int) -> str:
    if r < len(bracket.results) and bracket.results[r][slot] >= 0:
        return "  ✓" if bracket.results[r][slot] == pick else "  ✗"
    return ""


with tab_bracket:
    st.caption("In every game, the bracket advances whichever team won that round more often in the "
               "simulations." + (" ✓ = correct pick, ✗ = wrong pick." if bracket.results else ""))
    region_cols = st.columns(2)
    for ri, region in enumerate(bracket.regions):
        rows = {}
        for r, name in enumerate(mm.ROUND_LABELS[:4]):
            n = 8 >> r                                   # games per region in this round
            rows[name] = [label(teams[p]) + mark(r, ri * n + j, p)
                          for j, p in enumerate(picks[r][ri * n:(ri + 1) * n])]
        width = max(len(v) for v in rows.values())
        df = pd.DataFrame({k: v + [""] * (width - len(v)) for k, v in rows.items()})
        with region_cols[ri % 2]:
            st.markdown(f"**{region}**")
            st.dataframe(df, hide_index=True, width="stretch", height=(width + 1) * 35 + 3)
    st.markdown("**Final Four**")
    f4 = picks[3]
    for g in range(2):
        a, b, w = f4[2 * g], f4[2 * g + 1], picks[4][g]
        st.write(f"{label(teams[a])} vs {label(teams[b])} → **{teams[w].name}**{mark(4, g, w)}")
    st.write(f"Champion: **{label(teams[champ])}**{mark(5, 0, champ)}")

# ------------------------------------------------------------------ table
with tab_teams:
    df = pd.DataFrame({
        "": [t.logo for t in teams], "Seed": [t.seed for t in teams], "Team": [t.name for t in teams],
        "Region": [t.region for t in teams], "Rating": [round(t.rating, 1) for t in teams],
        **{name: 100 * odds[:, r] for r, name in enumerate(mm.ROUND_LABELS)},
    }).sort_values("Champion", ascending=False)
    pct = {name: st.column_config.ProgressColumn(name, format="%.1f%%", min_value=0, max_value=100)
           for name in mm.ROUND_LABELS}
    st.dataframe(df, hide_index=True, width="stretch", height=600,
                 column_config={"": st.column_config.ImageColumn("", width="small"),
                                "Rating": st.column_config.NumberColumn(
                                    help="Points better than an average Division I team on a neutral court"),
                                **pct})
    st.caption("Columns show the chance of *reaching* each stage, e.g. Sweet 16 = wins its first two games.")

# --------------------------------------------------------------- head to head
with tab_h2h:
    names = sorted(range(64), key=lambda i: teams[i].name)
    c1, c2 = st.columns(2)
    a = c1.selectbox("Team A", names, index=names.index(fav), format_func=lambda i: label(teams[i]))
    b = c2.selectbox("Team B", names, index=names.index(champ if champ != fav else names[0]),
                     format_func=lambda i: label(teams[i]))
    p = mm.win_probability(teams[a].rating, teams[b].rating, game_sd)
    margin = teams[a].rating - teams[b].rating
    st.metric(f"{teams[a].name} beats {teams[b].name}", f"{100 * p:.0f}%",
              f"expected margin {margin:+.1f} points (neutral court)", delta_color="off")
