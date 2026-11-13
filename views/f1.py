"""F1 Fantasy page: Monte Carlo team picker for the official F1 Fantasy game."""

from __future__ import annotations

import datetime as dt

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from ffmc import f1
from ffmc.http import APIError
from ffmc.ui import SPORTS, banner

COLOR = SPORTS["f1"]["color"]
OBJECTIVES = {"mean": "Most expected points", "floor": "Safe floor (avoid a bad weekend)",
              "ceiling": "Big ceiling (swing for a huge score)"}


@st.cache_data(ttl=1800, show_spinner="Loading prices from F1 Fantasy, results and race odds...")
def load() -> tuple[f1.Weekend, list[f1.Asset]]:
    return f1.load_weekend()


@st.cache_resource
def saved_results() -> dict:
    """Finished simulations, shared by everyone on the site, keyed by their settings."""
    return {}


def simulate(weekend, assets, settings: tuple, progress=None) -> f1.Result:
    key = (weekend.gameday, dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H"), settings)
    store = saved_results()
    if key not in store:
        if len(store) >= 30:
            store.pop(next(iter(store)))
        n_sims, budget, objective, mult, must, banned, seed = settings
        store[key] = f1.run(weekend, assets, n_sims, budget, objective, mult, seed, set(must), set(banned),
                            progress=progress)
    return store[key]


# ------------------------------------------------------------------- data
try:
    weekend, assets = load()
except (APIError, KeyError) as exc:
    st.error(f"Couldn't reach F1 Fantasy right now: {exc}")
    st.stop()

chips = [weekend.name or f"Round {weekend.round}"]
try:
    deadline = dt.datetime.strptime(weekend.deadline, "%m/%d/%Y %H:%M:%S")
    chips.append(f"Team deadline {deadline:%a %d %b, %H:%M} UTC")
except ValueError:
    pass
if weekend.sprint:
    chips.append("Sprint weekend")
banner("f1", "F1 Fantasy",
       "For the official F1 Fantasy game in the F1 app: 5 drivers and 2 constructors under your budget, with a "
       "DRS Boost on one driver. The race weekend is simulated 1,000,000 times (qualifying, the race, "
       "retirements, fastest lap and pit stops), scored with F1 Fantasy's rules.", chips=chips)

drivers = [a for a in assets if a.kind == "driver"]
cons = [a for a in assets if a.kind == "constructor"]
label = {a.id: (f"{a.name} · {a.team} · ${a.price:.1f}M" if a.kind == "driver" else f"{a.name} · ${a.price:.1f}M")
         for a in sorted(assets, key=lambda a: (a.kind != "driver", -a.price))}

# --------------------------------------------------------------- settings
with st.container(key="settings"):
    presets = {"No budget (Limitless chip)": None, "$100M (F1 Fantasy start)": 100.0, "$102M": 102.0,
               "$105M": 105.0, "$110M": 110.0, "Custom": "custom"}
    choice = st.pills("Budget", list(presets), default="$100M (F1 Fantasy start)", required=True,
                      key="f1_budget_choice",
                      help="Every team starts with $100M. Prices move after each race, so your team value grows "
                           "or shrinks; the F1 app shows yours. The Limitless chip removes the budget for one race.")
    budget = presets[choice]
    if budget == "custom":
        budget = st.number_input("Your budget ($M)", min_value=60.0, max_value=250.0, value=f1.DEFAULT_BUDGET,
                                 step=0.1, format="%.1f")
    c1, c2 = st.columns(2, gap="large")
    objective = c1.selectbox("Optimize for", list(OBJECTIVES), format_func=OBJECTIVES.get, key="f1_obj")
    extra = c2.toggle("Extra DRS Boost chip (3x instead of 2x)", value=False, key="f1_extra",
                      help="F1 Fantasy's Extra DRS Boost chip triples one driver's points for a race.")
    with st.expander("Must-haves and drivers to avoid"):
        m1, m2 = st.columns(2, gap="medium")
        must = m1.multiselect("Always include", list(label), format_func=label.get, key="f1_must",
                              placeholder="e.g. a driver you already own")
        banned = m2.multiselect("Leave out", [k for k in label if k not in must], format_func=label.get,
                                key="f1_banned", placeholder="e.g. a driver you don't trust")
    with st.expander("Simulation settings"):
        s1, s2 = st.columns(2, gap="medium")
        n_sims = s1.select_slider("Simulated race weekends", [50_000, 250_000, 1_000_000], value=1_000_000,
                                  format_func=lambda n: f"{n:,}")
        seed = s2.number_input("Random seed", 0, 10**6, 7, key="f1_seed")

notes = [f"Prices and past points: official F1 Fantasy · Form: last {weekend.races_used} races"]
notes.append("Race odds: Kalshi markets blended in" if weekend.market else
             "Race odds: Kalshi hasn't listed this race yet, so form alone sets the pace")
st.caption(" · ".join(notes))

settings = (n_sims, budget, objective, 3 if extra else 2, tuple(sorted(must)), tuple(sorted(banned)), int(seed))
if st.button(f"Simulate {n_sims:,} race weekends", type="primary") or st.session_state.get("f1_params") == settings:
    if st.session_state.get("f1_params") != settings:
        bar = st.progress(0.0, text=f"Racing {n_sims:,} times...")
        try:
            st.session_state["f1_result"] = simulate(
                weekend, assets, settings,
                progress=lambda f: bar.progress(min(f, 1.0), text=f"Racing {n_sims:,} times... "
                                                                  f"{int(min(f, 1) * n_sims):,} done"))
        except ValueError as exc:
            bar.empty()
            st.error(str(exc))
            st.stop()
        st.session_state["f1_params"] = settings
        bar.empty()
else:
    st.caption(f"Press the button to run the weekend {n_sims:,} times (about 10 seconds for a million).")
    st.stop()

res: f1.Result = st.session_state["f1_result"]
A = res.assets
mean = res.tally.mean + res.shift
p10 = res.tally.percentile(10) + res.shift
p90 = res.tally.percentile(90) + res.shift
team = res.team

# --------------------------------------------------------------- headline
cols = st.columns(4)
cols[0].metric("Expected points", f"{res.team_tally.mean[0]:.1f}", help="With the DRS Boost driver's points multiplied")
cols[1].metric(f"DRS Boost ({res.boost_mult}x)", A[team.boost].name)
cols[2].metric("Bad weekend (10th pct)", f"{res.team_tally.percentile(10)[0]:.0f}")
cols[3].metric("Great weekend (90th pct)", f"{res.team_tally.percentile(90)[0]:.0f}")
spent = f"Cost ${team.cost:.1f}M" + (f" of ${res.budget:.1f}M (${res.budget - team.cost:.1f}M left)"
                                     if res.budget is not None else " (no budget)")
st.caption(f"{spent} · Goal: {OBJECTIVES[objective].lower()} · {res.n_sims:,} simulated weekends")


def recent(a: f1.Asset) -> float | None:
    return round(float(np.mean(a.recent)), 1) if a.recent else None


def rows(idx: list[int], boost: int | None = None) -> pd.DataFrame:
    out = []
    for i in idx:
        a = A[i]
        mult = res.boost_mult if i == boost else 1
        out.append({"Pick": f"{a.name}" + (f"  · DRS {mult}x" if mult > 1 else ""),
                    "Team": a.team if a.kind == "driver" else "Constructor",
                    "Price $M": a.price, "Expected": mean[i] * mult, "Bad weekend": p10[i] * mult,
                    "Great weekend": p90[i] * mult, "Recent avg": recent(a),
                    "Expected finish": round(a.exp_finish, 1) if a.kind == "driver" else None,
                    "Owned %": a.selected})
    return pd.DataFrame(out)


CFG = {
    "Price $M": st.column_config.NumberColumn(format="$%.1f"),
    "Expected": st.column_config.NumberColumn(format="%.1f", help="Average F1 Fantasy points across the simulations"),
    "Bad weekend": st.column_config.NumberColumn(format="%.0f", help="10th percentile"),
    "Great weekend": st.column_config.NumberColumn(format="%.0f", help="90th percentile"),
    "Recent avg": st.column_config.NumberColumn(format="%.1f", help="Real F1 Fantasy points per race, last 5 rounds"),
    "Expected finish": st.column_config.NumberColumn(format="%.1f", help="Blend of recent results and Kalshi odds"),
    "Owned %": st.column_config.NumberColumn(format="%.0f%%", help="Share of F1 Fantasy teams that own them"),
    "Points per $M": st.column_config.NumberColumn(format="%.2f"),
}

tabs = st.tabs(["Your team", "Every driver & constructor", "Other strong teams"])
with tabs[0]:
    st.subheader("Drivers")
    picks = sorted(team.drivers, key=lambda i: -mean[i])
    st.dataframe(rows(picks, team.boost), hide_index=True, width="stretch", column_config=CFG)
    st.subheader("Constructors")
    st.dataframe(rows(sorted(team.constructors, key=lambda i: -mean[i])).drop(columns=["Expected finish", "Team"]),
                 hide_index=True, width="stretch", column_config=CFG)
    st.caption(f"Put the DRS Boost on {A[team.boost].name}: the highest expected scorer in the team, so "
               f"multiplying them adds the most.")
    # distribution of the team's total
    t = res.team_tally
    nz = np.nonzero(t.hist[0])[0]
    if len(nz):
        lo, hi = nz[0], nz[-1] + 1
        x = t.lo + np.arange(lo, hi) * t.step
        y = t.hist[0][lo:hi] / t.count * 100
        df = pd.DataFrame({"Points": x, "Share": y})
        df["Bin"] = (df["Points"] // 5) * 5
        df = df.groupby("Bin", as_index=False)["Share"].sum()
        st.subheader("How the team's score could go")
        st.altair_chart(alt.Chart(df).mark_bar(color=COLOR, opacity=.85).encode(
            x=alt.X("Bin:Q", title="Team total (F1 Fantasy points)", bin=alt.Bin(step=5, binned=True)),
            x2="Bin2:Q", y=alt.Y("Share:Q", title="% of simulated weekends"),
            tooltip=[alt.Tooltip("Bin:Q", title="From"), alt.Tooltip("Share:Q", format=".1f", title="% of weekends")])
            .transform_calculate(Bin2="datum.Bin + 5").properties(height=260), width="stretch")

with tabs[1]:
    allrows = rows(sorted(range(len(A)), key=lambda i: -mean[i]))
    allrows["Points per $M"] = (allrows["Expected"] / allrows["Price $M"]).round(2)
    st.dataframe(allrows, hide_index=True, width="stretch", column_config=CFG,
                 height=min(900, (len(allrows) + 1) * 35 + 3))
    st.subheader("Value: expected points vs price")
    sc = pd.DataFrame({"Name": [a.name for a in A], "Type": ["Driver" if a.kind == "driver" else "Constructor" for a in A],
                       "Price $M": [a.price for a in A], "Expected": np.round(mean, 1),
                       "In your team": ["Yes" if i in team.drivers + team.constructors else "No" for i in range(len(A))]})
    st.altair_chart(alt.Chart(sc).mark_circle(size=140).encode(
        x=alt.X("Price $M:Q"), y=alt.Y("Expected:Q", title="Expected F1 Fantasy points"),
        color=alt.Color("In your team:N", scale=alt.Scale(domain=["Yes", "No"], range=[COLOR, "#9aa5b1"]),
                        legend=alt.Legend(orient="top")),
        shape=alt.Shape("Type:N", legend=alt.Legend(orient="top")),
        tooltip=["Name", "Type", "Price $M", "Expected"]).properties(height=360), width="stretch")

with tabs[2]:
    if res.alternatives:
        alt_rows = []
        for t in res.alternatives:
            alt_rows.append({"Drivers": ", ".join(A[i].name + (" (DRS)" if i == t.boost else "") for i in t.drivers),
                             "Constructors": ", ".join(A[i].name for i in t.constructors),
                             "Cost $M": round(t.cost, 1), "Expected": round(t.mean, 1)})
        st.dataframe(pd.DataFrame(alt_rows), hide_index=True, width="stretch",
                     column_config={"Cost $M": st.column_config.NumberColumn(format="$%.1f")})
        st.caption("The next-best teams by expected points, in case you want to keep a driver you already own.")

with st.expander("How the simulation works"):
    st.markdown(f"""
- **Pace:** each driver's expected finish blends their last {weekend.races_used} races (from the official results)
  with Kalshi's odds for this race when it's listed (chance to win, finish on the podium, top 5 and top 10).
- **One simulated weekend:** every driver gets a random good or bad weekend, plus separate luck in qualifying
  and the race. Cars can retire, at each driver's recent retirement rate.
- **F1 Fantasy scoring:** qualifying 10 to 1 for the top 10; race 25, 18, 15... for the top 10; +1 per place
  gained and -1 per place lost; overtakes; +10 fastest lap; +10 Driver of the Day; -20 for a DNF.
  {"Sprint: 8 to 1 for the top 8, plus places gained and overtakes. " if weekend.sprint else ""}Constructors score
  both cars (without Driver of the Day), +10 if both reach Q3 (+5 for one, +3 if both reach Q2, +1 for one,
  -1 for neither) and pit-stop points.
- **Reality check:** each average is pulled part of the way toward the real F1 Fantasy points that driver or
  team has scored lately, which captures things the model can't see, like overtaking at a given track.
- **Picking the team:** every legal team of 5 drivers and 2 constructors under your budget is checked, with
  the DRS Boost on its best driver. That's over a million combinations, searched exactly.
""")
st.caption("Not affiliated with Formula 1 or F1 Fantasy. Prices and points from the official F1 Fantasy game; "
           "results from the Jolpica F1 database; odds from Kalshi.")
