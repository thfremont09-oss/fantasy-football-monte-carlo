"""Football page: Monte Carlo fantasy lineup optimizer."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from ffmc import engine
from ffmc.data import Slate, with_rosters
from ffmc.demo import demo_slate
from ffmc.espn_ff import DEFAULT_RULES, ESPNError, ESPNFantasy, load_default, load_league
from ffmc.lineup import DEFAULT_SLOTS
from ffmc.report import OBJECTIVE_TEXT
from ffmc.ui import SPORTS, banner

YOU_COLOR = SPORTS["nfl"]["color"]
OPP_COLOR = "#c75a1c"
BENCH_COLOR = "#a3a29c"

SLOT_TYPES = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX", "K", "DEF"]
SLOT_LABELS = {"FLEX": "FLEX (RB/WR/TE)", "SUPER_FLEX": "OP / Superflex (QB/RB/WR/TE)", "DEF": "D/ST", "K": "K"}
OBJECTIVES = {
    "auto": "Auto (win chance if I have an opponent)",
    "mean": "Most expected points",
    "win": "Best chance to beat my opponent",
    "floor": "Safe floor (avoid a dud week)",
    "ceiling": "Big ceiling (swing for upside)",
}
MODES = ["My ESPN league", "Best possible lineup (any NFL player)", "Pick my players"]
DEMO_SCORING = {"ESPN PPR": "espn", "ESPN Half-PPR": "half", "ESPN Standard": "std"}


def nfl_season() -> int:
    today = dt.date.today()
    return today.year if today.month >= 8 else today.year - 1


# ------------------------------------------------------------------ data
@st.cache_data(ttl=1800, show_spinner=False)
def espn_week(season: int) -> int:
    return ESPNFantasy(season).current_week()


@st.cache_data(ttl=1800, show_spinner="Downloading ESPN projections and stats...")
def load_pool(season: int, week: int, rules: str, slots: tuple[str, ...], history_weeks: int) -> Slate:
    return load_default(ESPNFantasy(season), rules, list(slots), week, history_weeks)


@st.cache_data(ttl=300, show_spinner="Loading your ESPN league...")
def load_espn_league(season: int, week: int, league_id: str, team_id: int | None, espn_s2: str, swid: str,
                     history_weeks: int):
    return load_league(ESPNFantasy(season, espn_s2=espn_s2, swid=swid), league_id, team_id, week, history_weeks)


@st.cache_data(show_spinner=False)
def load_demo(scoring: str, with_roster: bool) -> Slate:
    return demo_slate(scoring=scoring, with_roster=with_roster)


def headshot(p, live: bool) -> str | None:
    if not live:
        return None
    if p.position == "DEF":
        return f"https://a.espncdn.com/i/teamlogos/nfl/500/{(p.team or '').lower()}.png"
    return f"https://a.espncdn.com/i/headshots/nfl/players/full/{p.player_id}.png"


# --------------------------------------------------------------- settings
banner("nfl", "Fantasy Football Lineups",
       "Built for ESPN leagues. Your week is simulated thousands of times from ESPN's projections, each "
       "player's recent games, injury status and matchup, and the lineup that comes out ahead most often "
       "is the one to start.")

with st.container(key="settings"):
    mode = st.pills("Whose lineup?", MODES, default=MODES[0], required=True, key="nfl_mode")
    dream = mode.startswith("Best")

    league_id, espn_s2, swid = "", "", ""
    rules = "ESPN PPR"
    if mode == "My ESPN league":
        c1, c2, c3 = st.columns([2, 1, 1], gap="medium")
        league_id = c1.text_input(
            "ESPN league ID", help="The number after leagueId= in your league's address, e.g. "
                                   "fantasy.espn.com/football/league?leagueId=12345678")
    else:
        c1, c2, c3 = st.columns([2, 1, 1], gap="medium")
        rules = c1.selectbox("Scoring", list(DEFAULT_RULES),
                             help="ESPN's standard rules: 4 per passing TD, -2 per interception, "
                                  "6 per rushing/receiving TD, and 1 (PPR), 0.5 or 0 per catch.")

    with st.expander("Advanced: season, week, demo data"):
        demo = st.toggle("Use demo data (offline)", value=False,
                         help="Fake players, no internet needed. Turn off for real NFL data from ESPN.")
    season = week = None
    if not demo:
        try:
            cur_season = nfl_season()
            cur_week = espn_week(cur_season)
        except ESPNError as exc:
            st.error(f"Couldn't reach ESPN: {exc}\n\nCheck your internet connection, "
                     "or turn on **Use demo data** under Advanced.")
            st.stop()
        season = c2.number_input("Season", 2018, 2100, cur_season)
        week = c3.number_input("Week", 1, 18, min(max(cur_week, 1), 18))

    if mode == "My ESPN league":
        with st.expander("Private league? Add your ESPN login"):
            st.caption("Most ESPN leagues are private. ESPN only shares them with a logged-in browser, "
                       "so paste these two values from yours. They're used only to read your league "
                       "and aren't saved.")
            k1, k2 = st.columns(2, gap="medium")
            espn_s2 = k1.text_input("espn_s2", type="password")
            swid = k2.text_input("SWID", type="password", placeholder="{XXXXXXXX-XXXX-...}")
            st.markdown("**How do I find these?** On a computer, log in at fantasy.espn.com in Chrome. "
                        "Open the menu (⋮) → *More tools* → *Developer tools* → *Application* tab → "
                        "*Cookies* → *https://fantasy.espn.com*. Copy the values of **espn_s2** and **SWID**. "
                        "(Safari: *Develop* → *Show Web Inspector* → *Storage* → *Cookies*.)")
        if demo:
            st.info("Demo mode uses a fake league matchup.")

    slots = list(DEFAULT_SLOTS)
    e1, e2 = st.columns(2, gap="medium")
    if mode != "My ESPN league":
        with e1.expander("Lineup slots"):
            st.caption("ESPN's default: QB, 2 RB, 2 WR, TE, FLEX, D/ST, K.")
            defaults = {s: DEFAULT_SLOTS.count(s) for s in SLOT_TYPES}
            slots = []
            g1, g2 = st.columns(2)
            for k, s in enumerate(SLOT_TYPES):
                n = (g1 if k % 2 == 0 else g2).number_input(SLOT_LABELS.get(s, s), 0, 4, defaults[s], key=f"slot_{s}")
                slots += [s] * int(n)
    with (e2 if mode != "My ESPN league" else e1).expander("Simulation settings"):
        objective = st.selectbox("Optimize for", list(OBJECTIVES), format_func=OBJECTIVES.get)
        n_sims = st.select_slider("Simulations", [1000, 2500, 5000, 10000, 25000], value=10000)
        history_weeks = st.slider("Weeks of recent stats", 0, 10, 6,
                                  help="Used to judge how boom-or-bust each player is.")
        correlated = st.checkbox("Teammates & games are correlated", value=True,
                                 help="A QB and their receivers rise and fall together; a defense "
                                      "struggles when the offense it faces has a big day.")
        seed = st.number_input("Random seed", 0, 10**6, 42)

# ------------------------------------------------------------ build slate
try:
    if demo:
        slate = load_demo(DEMO_SCORING[rules], with_roster=not dream)
        if mode != "My ESPN league":
            slate = replace(slate, slots=slots)
    elif mode == "My ESPN league":
        if not league_id.strip().isdigit():
            st.info("Enter your **ESPN league ID** above. It's the number after **leagueId=** in "
                    "your league's address on fantasy.espn.com. Private league? Also open "
                    "**Private league? Add your ESPN login** above.")
            st.stop()
        _, teams = load_espn_league(int(season), int(week), league_id.strip(), None, espn_s2, swid, history_weeks)
        if not teams:
            st.warning("That league has no teams yet.")
            st.stop()
        labels = {t.id: f"{t.name}" + (f"  ({t.owner})" if t.owner else "") for t in teams}
        team_id = st.selectbox("Which team is yours?", list(labels), format_func=labels.get, key="espn_team")
        slate, _ = load_espn_league(int(season), int(week), league_id.strip(), int(team_id), espn_s2, swid,
                                    history_weeks)
    else:
        slate = load_pool(int(season), int(week), rules, tuple(slots), history_weeks)
except ESPNError as exc:
    st.error(str(exc))
    st.stop()

if not slate.slots:
    st.warning("Add at least one lineup slot under **Lineup slots**.")
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
           f"Data: {'synthetic demo' if demo else 'live from ESPN (projections, recent points, injuries)'}")
for note in slate.notes:
    st.caption(note)

if objective == "win" and (dream or not slate.has_opponent):
    st.info("**Best chance to beat my opponent** needs an opponent, so this run maximizes expected "
            "points instead. To get a win chance, pick **My ESPN league** or add your opponent's "
            "players under **Pick my players**.")
    objective = "mean"

params = (demo, mode, slate.season, slate.week, tuple(slate.slots), tuple(sorted(slate.my_ids)),
          tuple(sorted(slate.opp_ids)), objective, n_sims, history_weeks, correlated, seed, rules)
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
        row = {"": headshot(p, live), "Slot": slot, "Player": p.name, "Pos": p.position,
               "Team": p.team or "FA", "Opp": p.opponent or "—", "Projection": p.projection,
               "Sim avg": r.sim_mean, "Bad week": r.p10, "Great week": r.p90,
               "Status": p.injury_status or ""}
        if show_start:
            row["Best lineup %"] = r.start_pct
        data.append(row)
    return pd.DataFrame(data)


COLCFG = {
    "": st.column_config.ImageColumn("", width="small"),
    "Projection": st.column_config.NumberColumn(format="%.1f", help="This week's ESPN projection"),
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
