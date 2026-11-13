"""Fantasy Premier League page: Monte Carlo team picker."""

from __future__ import annotations

import datetime as dt
import math

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from ffmc import fpl
from ffmc.ui import SPORTS, banner

COLOR = SPORTS["epl"]["color"]


@st.cache_data(ttl=1800, show_spinner="Loading this gameweek from the official FPL site...")
def load() -> fpl.Gameweek:
    return fpl.load_gameweek(fpl.FPLClient(".ffmc_cache"))


@st.cache_data(ttl=600, show_spinner="Loading your FPL team...")
def load_team(gw: fpl.Gameweek, team_id: int):
    return fpl.load_squad(fpl.FPLClient(".ffmc_cache"), gw, team_id)


@st.cache_data(show_spinner="Simulating the gameweek...")
def simulate(gw: fpl.Gameweek, n_sims: int, seed: int, squad: tuple[int, ...] | None, budget: float | None):
    return fpl.run(gw, gw.players, n_sims, seed, list(squad) if squad else None, budget)


# ------------------------------------------------------------------- data
try:
    gw = load()
except fpl.FPLError as exc:
    st.error(f"Couldn't reach the FPL site: {exc}")
    st.stop()

deadline = dt.datetime.fromisoformat(gw.deadline.replace("Z", "+00:00"))
banner("epl", "Fantasy Premier League",
       "Every fixture of the gameweek is played out 25,000 times: goals, assists, clean sheets, "
       "saves, defensive contributions and bonus. The XI and captain that come out on top most often "
       "are your best picks.",
       chips=[gw.name, f"Deadline {deadline:%a %d %b, %H:%M} UTC", f"{len(gw.fixtures)} fixtures"])

# --------------------------------------------------------------- settings
with st.container(key="settings"):
    mode = st.pills("Whose team?", ["Best XI this gameweek", "My FPL team"], default="Best XI this gameweek",
                    required=True, key="fpl_mode")
    team_id = None
    budget = None
    if mode == "My FPL team":
        c1, _ = st.columns(2, gap="medium")
        raw = c1.text_input("FPL team ID", help="The number in your Points page address: "
                            "fantasy.premierleague.com/entry/1234567/event/10")
        team_id = int(raw) if raw.strip().isdigit() else None
    else:
        presets = {"No budget": None, "£100.0m (FPL start)": 100.0, "£102.0m": 102.0, "£103.5m": 103.5,
                   "£105.0m": 105.0, "Custom": "custom"}
        choice = st.pills("Budget", list(presets), default="£100.0m (FPL start)", required=True,
                          key="fpl_budget_choice",
                          help="Everyone starts FPL with £100.0m. As player prices rise your team value grows, so "
                               "most managers have £100-105m by mid-season (your Transfers page shows yours). "
                               "The budget covers the full 15-player squad: the XI plus the cheapest legal bench.")
        if presets[choice] == "custom":
            budget = st.number_input("Your budget (£m)", min_value=60.0, max_value=200.0, value=fpl.DEFAULT_BUDGET,
                                     step=0.1, format="%.1f")
        else:
            budget = presets[choice]
    with st.expander("Simulation settings"):
        s1, s2 = st.columns(2, gap="medium")
        n_sims = s1.select_slider("Simulated gameweeks", [10_000, 25_000, 50_000], value=25_000,
                                  format_func=lambda n: f"{n:,}",
                                  help="More simulations = steadier odds, but slower. Each one plays all 10 matches.")
        seed = s2.number_input("Random seed", 0, 10**6, 42, key="fpl_seed")

for note in gw.notes:
    st.caption(note)

squad = None
team_name = None
if mode == "My FPL team":
    if not team_id:
        st.info("Enter your **FPL team ID** above. It's the number in the address of your "
                "Points page, e.g. fantasy.premierleague.com/entry/**1234567**/event/10.")
        st.stop()
    try:
        squad, team_name, notes = load_team(gw, team_id)
    except fpl.FPLError as exc:
        st.error(f"Couldn't load team {team_id}: {exc}")
        st.stop()
    for note in notes:
        st.caption(note)

try:
    res = simulate(gw, n_sims, int(seed), tuple(squad) if squad else None, budget)
except fpl.FPLError as exc:
    st.error(str(exc))
    st.stop()

P = gw.players

# --------------------------------------------------------------- headline
p10, p90 = np.percentile(res.totals, [10, 90])
cols = st.columns(4)
cols[0].metric("Expected points", f"{res.totals.mean():.1f}", help="Starting XI with the captain's points doubled")
cols[1].metric("Captain", P[res.captain].name)
cols[1].caption(f"Vice-captain: {P[res.vice].name}")
cols[2].metric("Bad week (10th pct)", f"{p10:.0f}")
cols[3].metric("Great week (90th pct)", f"{p90:.0f}")
if team_name:
    st.caption(f"{team_name}: best XI from your 15.")
elif res.squad_cost is not None:
    xi_cost = sum(P[i].price for i in res.xi)
    st.caption(f"Full 15-player squad costs **£{res.squad_cost:.1f}m** of your £{budget:.1f}m "
               f"(starting XI £{xi_cost:.1f}m + cheapest legal bench). Max 3 players per club.")
else:
    st.caption("Best XI from every player, prices ignored (max 3 per club).")


# ------------------------------------------------------------------ pitch
def pitch(xi: list[int]) -> str:
    rows = []
    for pos in ("FWD", "MID", "DEF", "GK"):
        chips = []
        for i in sorted((i for i in xi if P[i].position == pos), key=lambda i: -res.mean[i]):
            badge = '<span class="cap">C</span>' if i == res.captain else (
                '<span class="cap vice">V</span>' if i == res.vice else "")
            chips.append(f'<div class="pl">{badge}<div class="nm">{P[i].name}</div>'
                         f'<div class="fx">{" · ".join(P[i].fixtures)}</div>'
                         f'<div class="pt">{res.mean[i]:.1f}</div></div>')
        rows.append(f'<div class="row">{"".join(chips)}</div>')
    return f"""
<style>
.pitch {{ border-radius: 10px; padding: 22px 8px; max-width: 820px; margin: 0 auto 6px; display: flex; flex-direction: column; gap: 14px;
  background: repeating-linear-gradient(180deg, rgba(255,255,255,.06) 0 46px, transparent 46px 92px),
              linear-gradient(180deg, #13723a, #0f5f30); position: relative; }}
.pitch::before {{ content: ""; position: absolute; inset: 10px; border: 2px solid rgba(255,255,255,.35); border-radius: 4px; }}
.pitch::after {{ content: ""; position: absolute; left: 50%; top: 50%; width: 90px; height: 90px; margin: -45px 0 0 -45px;
  border: 2px solid rgba(255,255,255,.3); border-radius: 50%; }}
.pitch .row {{ display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; position: relative; z-index: 1; }}
.pitch .pl {{ background: #fff; border-radius: 8px; width: 112px; padding: 7px 6px 6px; text-align: center;
  box-shadow: 0 2px 6px rgba(0,0,0,.25); position: relative; }}
.pitch .nm {{ font-weight: 700; font-size: .85rem; color: #14202e; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.pitch .fx {{ font-size: .7rem; color: #5b6878; }}
.pitch .pt {{ margin: 5px -6px -6px; background: {COLOR}; color: #fff; font-weight: 700; font-size: .85rem;
  border-radius: 0 0 8px 8px; padding: 2px 0; font-family: "Barlow Condensed", sans-serif; }}
.pitch .cap {{ position: absolute; top: -8px; right: -8px; background: #f2b134; color: #14202e; font-weight: 800;
  font-size: .72rem; width: 22px; height: 22px; line-height: 22px; border-radius: 50%; }}
.pitch .cap.vice {{ background: #dfe3e8; }}
@media (max-width: 640px) {{ .pitch .pl {{ width: 84px; }} .pitch .nm {{ font-size: .75rem; }} }}
</style>
<div class="pitch">{''.join(rows)}</div>"""


def table(idx: list[int], show_captain: bool = True) -> pd.DataFrame:
    df = pd.DataFrame({
        "": [P[i].photo for i in idx],
        "Pos": [P[i].position for i in idx], "Player": [P[i].name for i in idx],
        "Club": [P[i].team_short for i in idx], "Fixture": [", ".join(P[i].fixtures) for i in idx],
        "Price": [P[i].price for i in idx], "FPL projection": [P[i].fpl_projection for i in idx],
        "Sim avg": [res.mean[i] for i in idx], "Bad week": [res.p10[i] for i in idx],
        "Great week": [res.p90[i] for i in idx], "Best XI %": [res.in_best_xi_pct[i] for i in idx],
        "News": [P[i].news for i in idx],
    })
    if show_captain:
        df.insert(10, "Top scorer %", [res.best_captain_pct[i] for i in idx])
    return df


CFG = {
    "": st.column_config.ImageColumn("", width="small"),
    "Price": st.column_config.NumberColumn(format="£%.1fm"),
    "FPL projection": st.column_config.NumberColumn(format="%.1f", help="FPL's own expected points"),
    "Sim avg": st.column_config.NumberColumn(format="%.1f", help="Average across all simulated gameweeks"),
    "Bad week": st.column_config.NumberColumn(format="%.0f", help="10th percentile"),
    "Great week": st.column_config.NumberColumn(format="%.0f", help="90th percentile"),
    "Top scorer %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100,
                                                    help="How often this player outscored the rest of the XI: "
                                                         "the chance they were the right captain"),
    "Best XI %": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100,
                                                 help="How often this player was in the best possible XI "
                                                      "looking back at each simulated gameweek"),
}

order = sorted(res.xi, key=lambda i: ("GK", "DEF", "MID", "FWD").index(P[i].position))
tab_xi, tab_cap, tab_fx = st.tabs(["Starting XI", "Captain", "Match predictions"])

with tab_xi:
    st.markdown(pitch(res.xi), unsafe_allow_html=True)
    st.caption("C = captain, V = vice-captain. Numbers are simulated average points.")
    st.dataframe(table(order), column_config=CFG, hide_index=True, width="stretch",
                 height=(len(order) + 1) * 38 + 3, row_height=38)
    if res.bench:
        st.subheader("Bench")
        st.caption("In auto-sub order: goalkeeper first, then outfield players by expected points.")
        st.dataframe(table(res.bench, show_captain=False), column_config=CFG, hide_index=True, width="stretch",
                     height=(len(res.bench) + 1) * 38 + 3, row_height=38)

with tab_cap:
    top = sorted(res.xi, key=lambda i: -res.best_captain_pct[i])[:8]
    df = pd.DataFrame({"Player": [P[i].name for i in top], "Chance of being the right captain %":
                       [round(res.best_captain_pct[i], 1) for i in top],
                       "Sim avg": [round(res.mean[i], 1) for i in top]})
    chart = alt.Chart(df).mark_bar(color=COLOR, cornerRadiusEnd=4, height=20).encode(
        x=alt.X("Chance of being the right captain %:Q"),
        y=alt.Y("Player:N", sort=list(df["Player"]), title=None),
        tooltip=list(df.columns)).properties(height=alt.Step(32))
    st.altair_chart(chart, width="stretch")
    st.caption("Share of simulated gameweeks in which each player scored the most in your XI. Spread "
               "out across several players means there's no obvious captain this week.")


def outcome_probs(lam_h: float, lam_a: float) -> tuple[float, float, float]:
    ph = [math.exp(-lam_h) * lam_h ** k / math.factorial(k) for k in range(11)]
    pa = [math.exp(-lam_a) * lam_a ** k / math.factorial(k) for k in range(11)]
    home = sum(ph[i] * pa[j] for i in range(11) for j in range(11) if i > j)
    draw = sum(ph[i] * pa[i] for i in range(11))
    return home, draw, 1 - home - draw


with tab_fx:
    rows = []
    for f in sorted(gw.fixtures, key=lambda f: -(f["home_xg"] + f["away_xg"])):
        h, d, a = outcome_probs(f["home_xg"], f["away_xg"])
        rows.append({"Home": gw.teams[f["home"]], "Away": gw.teams[f["away"]],
                     "Expected goals": f"{f['home_xg']:.1f} – {f['away_xg']:.1f}",
                     "Home win": 100 * h, "Draw": 100 * d, "Away win": 100 * a,
                     "Home clean sheet": 100 * math.exp(-f["away_xg"]),
                     "Away clean sheet": 100 * math.exp(-f["home_xg"])})
    pct = st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                 column_config={c: pct for c in ("Home win", "Draw", "Away win", "Home clean sheet", "Away clean sheet")})
    st.caption("Team strength comes from goals scored and conceded in this season's matches, compared "
               "with the league average and home/away scoring rates.")
