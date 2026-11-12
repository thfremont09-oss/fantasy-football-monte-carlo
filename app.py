"""Web UI for the fantasy football Monte Carlo optimizer.

Run with:  streamlit run app.py
"""

from __future__ import annotations

from dataclasses import replace

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from ffmc import engine
from ffmc.data import Slate, load_live, with_rosters
from ffmc.demo import demo_slate
from ffmc.lineup import DEFAULT_SLOTS
from ffmc.report import OBJECTIVE_TEXT
from ffmc.sleeper import SleeperClient, SleeperError

YOU_COLOR = "#2a78d6"
OPP_COLOR = "#eb6834"
BENCH_COLOR = "#a3a29c"

SLOT_TYPES = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "K", "DEF"]
SLOT_LABELS = {"FLEX": "FLEX (RB/WR/TE)", "SUPER_FLEX": "SUPERFLEX (QB/RB/WR/TE)"}
OBJECTIVES = {
    "auto": "Auto (win chance if I have an opponent)",
    "mean": "Most expected points",
    "win": "Best chance to beat my opponent",
    "floor": "Safe floor (avoid a dud week)",
    "ceiling": "Big ceiling (swing for upside)",
}

st.set_page_config(page_title="Fantasy Lineup Simulator", page_icon="🏈", layout="wide")


# ------------------------------------------------------------------ data
@st.cache_resource
def client() -> SleeperClient:
    return SleeperClient(".ffmc_cache")


@st.cache_data(ttl=600, show_spinner=False)
def nfl_state() -> dict:
    return client().state()


@st.cache_data(ttl=3600, show_spinner="Downloading this week's NFL projections and stats...")
def load_pool(season: int, week: int, scoring: str, slots: tuple[str, ...], history_weeks: int) -> Slate:
    return load_live(client(), season=season, week=week, scoring=scoring, slots=list(slots),
                     history_weeks=history_weeks)


@st.cache_data(ttl=300, show_spinner="Loading your Sleeper league...")
def load_league(league_id: str, username: str, season: int, week: int, history_weeks: int) -> Slate:
    return load_live(client(), season=season, week=week, league_id=league_id, username=username,
                     history_weeks=history_weeks)


@st.cache_data(show_spinner=False)
def load_demo(scoring: str, with_roster: bool) -> Slate:
    return demo_slate(scoring=scoring, with_roster=with_roster)


def headshot(pid: str, live: bool) -> str | None:
    if not live:
        return None
    if not pid.isdigit():  # team defenses are keyed by team abbreviation
        return f"https://sleepercdn.com/images/team_logos/nfl/{pid.lower()}.png"
    return f"https://sleepercdn.com/content/nfl/players/thumb/{pid}.jpg"


# --------------------------------------------------------------- sidebar
st.sidebar.title("🏈 Lineup Simulator")
demo = st.sidebar.toggle("Use demo data (offline)", value=False,
                         help="Fake players, no internet needed. Turn off for real NFL data from Sleeper.")

mode = st.sidebar.radio("Whose lineup?", ["Best possible lineup (any NFL player)",
                                          "My Sleeper league", "Pick my players"])
dream = mode.startswith("Best")

season = week = None
if not demo:
    try:
        state = nfl_state()
        cur_season, cur_week = int(state.get("league_season") or state["season"]), int(state.get("week") or 1)
    except SleeperError as exc:
        st.error(f"Couldn't reach the Sleeper API: {exc}\n\nCheck your internet connection, "
                 "or turn on **Use demo data** in the sidebar.")
        st.stop()
    c1, c2 = st.sidebar.columns(2)
    season = c1.number_input("Season", 2018, 2100, cur_season)
    week = c2.number_input("Week", 1, 18, min(max(cur_week, 1), 18))

league_id = username = None
if mode == "My Sleeper league":
    league_id = st.sidebar.text_input("League ID", help="The number in sleeper.com/leagues/<LEAGUE_ID>/...")
    username = st.sidebar.text_input("Sleeper username")
    if demo:
        st.sidebar.info("Demo mode uses a fake league matchup.")

scoring = "ppr"
slots = list(DEFAULT_SLOTS)
if mode != "My Sleeper league":
    scoring = st.sidebar.selectbox("Scoring", ["ppr", "half", "std"],
                                   format_func={"ppr": "PPR", "half": "Half PPR", "std": "Standard"}.get)
    with st.sidebar.expander("Lineup slots"):
        defaults = {s: DEFAULT_SLOTS.count(s) for s in SLOT_TYPES}
        slots = []
        for s in SLOT_TYPES:
            n = st.number_input(SLOT_LABELS.get(s, s), 0, 4, defaults[s], key=f"slot_{s}")
            slots += [s] * int(n)

with st.sidebar.expander("Simulation settings"):
    objective = st.selectbox("Optimize for", list(OBJECTIVES), format_func=OBJECTIVES.get)
    n_sims = st.select_slider("Simulations", [1000, 2500, 5000, 10000, 25000], value=10000)
    history_weeks = st.slider("Weeks of recent stats", 0, 10, 6,
                              help="Used to judge how boom-or-bust each player is.")
    correlated = st.checkbox("Teammates & games are correlated", value=True,
                             help="A QB and his receivers rise and fall together; a defense "
                                  "struggles when the offense it faces has a big day.")
    seed = st.number_input("Random seed", 0, 10**6, 42)

# ------------------------------------------------------------ build slate
st.title("Fantasy Football Lineup Simulator")
try:
    if demo:
        slate = load_demo(scoring, with_roster=not dream)
        if mode != "My Sleeper league":
            slate = replace(slate, slots=slots)
    elif mode == "My Sleeper league":
        if not (league_id and username):
            st.info("Enter your **League ID** and **Sleeper username** in the sidebar.")
            st.stop()
        slate = load_league(league_id.strip(), username.strip(), int(season), int(week), history_weeks)
    else:
        slate = load_pool(int(season), int(week), scoring, tuple(slots), history_weeks)
except SleeperError as exc:
    st.error(f"Sleeper API error: {exc}")
    st.stop()

if not slate.slots:
    st.warning("Add at least one lineup slot in the sidebar.")
    st.stop()

if mode == "Pick my players":
    ranked = sorted(slate.players, key=lambda p: -p.mean * p.p_play)
    labels = {p.player_id: f"{p.name} · {p.position} · {p.team or 'FA'}" for p in ranked}
    c1, c2 = st.columns(2)
    mine = c1.multiselect("Your players", list(labels), format_func=labels.get, key="mine",
                          placeholder="Start typing a name... (defenses by team name)")
    theirs = c2.multiselect("Opponent's players (optional)", [p for p in labels if p not in mine],
                            format_func=labels.get, key="theirs",
                            placeholder="Add them to see your win probability")
    if not mine:
        st.info("Add your players above, then hit **Simulate**.")
        st.stop()
    slate = with_rosters(slate, set(mine), set(theirs))

st.caption(f"Season {slate.season} · Week {slate.week} · Scoring: {slate.scoring_name} · "
           f"Data: {'synthetic demo' if demo else 'live from Sleeper (projections, recent stats, injuries)'}")
for note in slate.notes:
    st.caption(f"ℹ️ {note}")

if objective == "win" and (dream or not slate.has_opponent):
    st.info("**Best chance to beat my opponent** needs an opponent, so this run maximizes expected "
            "points instead. To get a win chance, pick **My Sleeper league** or add your opponent's "
            "players under **Pick my players**.")
    objective = "mean"

params = (demo, mode, slate.season, slate.week, tuple(slate.slots), tuple(sorted(slate.my_ids)),
          tuple(sorted(slate.opp_ids)), objective, n_sims, history_weeks, correlated, seed, scoring)
if st.button("Simulate", type="primary") or st.session_state.get("params") == params:
    if st.session_state.get("params") != params:
        with st.spinner(f"Simulating the week {n_sims:,} times..."):
            try:
                st.session_state["result"] = engine.run(slate, n_sims=n_sims, objective=objective,
                                                        seed=int(seed), correlated=correlated, dream=dream)
            except ValueError as exc:
                st.error(str(exc))
                st.stop()
        st.session_state["params"] = params
else:
    st.stop()

res: engine.Result = st.session_state["result"]
live = not demo

# ---------------------------------------------------------------- headline
totals = res.totals
p10, p90 = np.percentile(totals, [10, 90])
cols = st.columns(4 if res.win_prob is not None else 3)
cols[0].metric("Expected points", f"{totals.mean():.1f}")
cols[1].metric("Bad week (10th pct)", f"{p10:.1f}")
cols[2].metric("Great week (90th pct)", f"{p90:.1f}")
if res.win_prob is not None:
    cols[3].metric(f"Win chance vs {slate.opp_name}", f"{100 * res.win_prob:.0f}%",
                   f"{(totals - res.opp_totals).mean():+.1f} pts expected margin")
st.caption(f"Goal: {OBJECTIVE_TEXT[res.objective]}."
           + (f" The max-expected-points lineup would average {res.mean_lineup_points:.1f}."
              if res.objective != "mean" and res.mean_lineup_points is not None else ""))


def show_table(df: pd.DataFrame) -> None:
    row_h = 44 if live else 35
    st.dataframe(df, column_config=COLCFG, hide_index=True, width="stretch",
                 row_height=row_h, height=(len(df) + 1) * row_h + 3)


def table(rows, slots, show_start=True) -> pd.DataFrame:
    data = []
    for slot, r in zip(slots, rows):
        if r is None:
            continue
        p = r.player
        row = {"": headshot(p.player_id, live), "Slot": slot, "Player": p.name, "Pos": p.position,
               "Team": p.team or "FA", "Opp": p.opponent or "—", "Projection": p.projection,
               "Sim avg": r.sim_mean, "Bad week": r.p10, "Great week": r.p90,
               "Status": p.injury_status or ""}
        if show_start:
            row["Best lineup %"] = r.start_pct
        data.append(row)
    return pd.DataFrame(data)


COLCFG = {
    "": st.column_config.ImageColumn("", width="small"),
    "Projection": st.column_config.NumberColumn(format="%.1f", help="This week's Sleeper projection"),
    "Sim avg": st.column_config.NumberColumn(format="%.1f",
                                             help="Simulated average: projection blended with recent form, "
                                                  "including injury risk"),
    "Bad week": st.column_config.NumberColumn(format="%.1f", help="10th percentile outcome"),
    "Great week": st.column_config.NumberColumn(format="%.1f", help="90th percentile outcome"),
    "Best lineup %": st.column_config.ProgressColumn(
        format="%.0f%%", min_value=0, max_value=100,
        help="How often this player was in the best possible lineup looking back at each simulated week"),
}


def range_chart(rows: list[engine.PlayerResult], groups: list[str]) -> alt.Chart:
    df = pd.DataFrame([{
        "Player": f"{r.player.name} ({r.player.position})", "Group": g, "Bad week": round(r.p10, 1),
        "Great week": round(r.p90, 1), "Sim avg": round(r.sim_mean, 1),
        "Best lineup %": round(r.start_pct),
    } for r, g in zip(rows, groups)])
    order = list(df["Player"])
    color = alt.Color("Group:N", scale=alt.Scale(domain=["Starter", "Bench"], range=[YOU_COLOR, BENCH_COLOR]),
                      legend=alt.Legend(title=None, orient="top"))
    tooltip = ["Player", "Group", "Sim avg", "Bad week", "Great week", "Best lineup %"]
    base = alt.Chart(df).encode(y=alt.Y("Player:N", sort=order, title=None, axis=alt.Axis(labelLimit=220)), tooltip=tooltip)
    bars = base.mark_rule(strokeWidth=8, strokeCap="round", opacity=0.55).encode(
        x=alt.X("Bad week:Q", title="Fantasy points (10th to 90th percentile, dot = average)"),
        x2="Great week:Q", color=color)
    dots = base.mark_circle(size=110, opacity=1, stroke="white", strokeWidth=2).encode(
        x="Sim avg:Q", color=color)
    return (bars + dots).properties(height=alt.Step(34))


def distribution_chart(res: engine.Result) -> alt.Chart:
    series = [(slate.my_name, res.totals)]
    if res.opp_totals is not None:
        series.append((slate.opp_name or "Opponent", res.opp_totals))
    lo = min(s.min() for _, s in series)
    hi = max(s.max() for _, s in series)
    edges = np.linspace(lo, hi, 41)
    rows = []
    for name, s in series:
        counts, _ = np.histogram(s, edges)
        for c, a, b in zip(counts, edges[:-1], edges[1:]):
            rows.append({"Team": name, "Points": round((a + b) / 2, 1),
                         "Range": f"{a:.0f}–{b:.0f}", "Share of weeks %": round(100 * c / len(s), 1)})
    df = pd.DataFrame(rows)
    names = [n for n, _ in series]
    color = alt.Color("Team:N", scale=alt.Scale(domain=names, range=[YOU_COLOR, OPP_COLOR][:len(names)]),
                      legend=alt.Legend(title=None, orient="top"))
    hover = alt.selection_point(fields=["Points"], nearest=True, on="pointerover", empty=False)
    area = alt.Chart(df).mark_area(interpolate="monotone", opacity=0.25, line={"strokeWidth": 2}).encode(
        x=alt.X("Points:Q", title="Total fantasy points"),
        y=alt.Y("Share of weeks %:Q", title="% of simulated weeks", stack=None), color=color)
    points = alt.Chart(df).mark_circle(size=70).encode(
        x="Points:Q", y="Share of weeks %:Q", color=color,
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=["Team", "Range", "Share of weeks %"]).add_params(hover)
    rule = alt.Chart(df).mark_rule(color="gray", strokeDash=[3, 3]).encode(x="Points:Q").transform_filter(hover)
    return (area + points + rule).properties(height=280)


# ------------------------------------------------------------------ tabs
tab_names = ["Lineup", "Score outlook"] + (["Opponent"] if res.opp_lineup is not None else [])
tabs = st.tabs(tab_names)

with tabs[0]:
    st.subheader("Start these players" if not dream else "Best possible lineup this week")
    show_table(table(res.lineup, res.slots))
    if res.bench:
        st.subheader("Bench")
        show_table(table(res.bench, ["BN"] * len(res.bench)))
    st.subheader("How wide is each player's range?")
    starters = [r for r in res.lineup if r]
    bench = [r for r in res.bench if r.player.mean > 0]
    st.altair_chart(range_chart(starters + bench, ["Starter"] * len(starters) + ["Bench"] * len(bench)),
                    width="stretch")

with tabs[1]:
    st.subheader("Simulated total points")
    st.altair_chart(distribution_chart(res), width="stretch")
    st.caption("Each simulated week draws a random outcome for every player, with teammates and "
               "opponents linked, and injury-risk players sometimes sitting out.")

if res.opp_lineup is not None:
    with tabs[2]:
        st.subheader(f"{slate.opp_name}'s lineup")
        show_table(table(res.opp_lineup, res.slots, show_start=False))
