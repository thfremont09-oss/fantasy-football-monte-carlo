"""Parlay Lab page: Monte Carlo parlay finder for DraftKings and Kalshi."""

from __future__ import annotations

import datetime as dt
import time
from zoneinfo import ZoneInfo

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from ffmc import parlay as pl
from ffmc.ui import SPORTS, banner

COLOR = SPORTS["bets"]["color"]
ET = ZoneInfo("America/New_York")
PAYOUTS = [1.5, 2, 3, 5, 10, 20, 50, 100, 250, 500, 1000]
RISK_NAMES = {1: "Very safe", 2: "Safe", 3: "Careful", 4: "Balanced", 5: "Balanced", 6: "Bold", 7: "Bold",
              8: "Long shot", 9: "Long shot", 10: "Lottery ticket"}
FUN_LINES = [
    "Checking every line from the NFL to Peruvian soccer...",
    "Asking 80,000 markets what they really think...",
    "Taking the bookmaker's cut out of every price...",
    "Fun fact: ten 50/50 legs hit about once in 1,024 tries.",
    "Lining up DraftKings and Kalshi side by side...",
    "Fun fact: every extra leg multiplies the house's edge.",
    "Rolling a million possible weekends...",
    "Counting how often the underdog shows up...",
]


# ------------------------------------------------------------------ loading
@st.cache_resource
def _store() -> dict:
    return {}


def loading_screen():
    """A fun scoreboard while the markets load. Returns an update(stage, fraction, stats) function."""
    lines = "".join(f'<span style="animation-delay:{3 * i}s">{t}</span>' for i, t in enumerate(FUN_LINES))
    total = 3 * len(FUN_LINES)
    st.markdown(f"""
<style>
.ld {{ background: radial-gradient(circle at 20% 0%, #2a1f6b 0%, #0c1a2b 60%); border-radius: 14px; padding: 1.6rem 1.6rem 1.3rem;
  color: #fff; overflow: hidden; position: relative; margin: .4rem 0 1rem; }}
.ld .lights {{ display: flex; gap: 10px; margin-bottom: 1rem; }}
.ld .lights i {{ width: 12px; height: 12px; border-radius: 50%; background: #f2b134; opacity: .25;
  animation: blink 1.2s infinite; }}
.ld .lights i:nth-child(2) {{ animation-delay: .2s; }} .ld .lights i:nth-child(3) {{ animation-delay: .4s; }}
.ld .lights i:nth-child(4) {{ animation-delay: .6s; }} .ld .lights i:nth-child(5) {{ animation-delay: .8s; }}
@keyframes blink {{ 0%, 100% {{ opacity: .2; transform: scale(.85); }} 50% {{ opacity: 1; transform: scale(1.1); }} }}
.ld h3 {{ color: #fff; margin: 0 0 .3rem; font-size: 1.6rem; text-transform: uppercase; }}
.ld .msgs {{ position: relative; height: 1.6rem; color: #c9d3df; font-size: 1.02rem; }}
.ld .msgs span {{ position: absolute; left: 0; top: 0; opacity: 0; animation: msg {total}s infinite; white-space: nowrap; }}
@keyframes msg {{ 0% {{ opacity: 0; transform: translateY(8px); }} 3% {{ opacity: 1; transform: none; }}
  {100 / len(FUN_LINES) - 3:.1f}% {{ opacity: 1; }} {100 / len(FUN_LINES):.1f}% {{ opacity: 0; transform: translateY(-8px); }} 100% {{ opacity: 0; }} }}
.ld .track {{ position: relative; height: 34px; margin-top: 1rem; border-bottom: 2px dashed rgba(255,255,255,.18); }}
.ld .ball {{ position: absolute; bottom: 4px; width: 18px; height: 18px; border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #ffd27a, #f2b134 60%, #b9801a); animation: roll 3.2s ease-in-out infinite alternate; }}
@keyframes roll {{ 0% {{ left: 0; transform: translateY(0) rotate(0); }} 25% {{ transform: translateY(-14px); }}
  50% {{ transform: translateY(0); }} 75% {{ transform: translateY(-8px); }} 100% {{ left: calc(100% - 18px); transform: translateY(0) rotate(720deg); }} }}
@media (max-width: 640px) {{ .ld .msgs {{ height: 3rem; }} .ld .msgs span {{ white-space: normal; }} }}
</style>
<div class="ld"><div class="lights"><i></i><i></i><i></i><i></i><i></i></div>
<h3>Scouting the board</h3><div class="msgs">{lines}</div><div class="track"><div class="ball"></div></div></div>
""", unsafe_allow_html=True)
    board = st.empty()

    def update(stage: str, frac: float, stats: dict):
        cells = [("Markets scanned", f"{stats.get('scanned', 0):,}"), ("Leagues", f"{stats.get('leagues', 0) or '...'}"),
                 ("DraftKings legs", f"{stats.get('dk_legs', 0):,}"), ("Kalshi legs", f"{stats.get('kalshi_legs', 0):,}")]
        tiles = "".join(f'<div style="flex:1;min-width:120px;background:#0c1a2b;border:1px solid #233a55;border-radius:8px;'
                        f'padding:.6rem .8rem"><div style="font-family:\'Barlow Condensed\',sans-serif;font-size:1.9rem;'
                        f'font-weight:700;color:#f2b134;line-height:1">{v}</div><div style="color:#9fb0c3;font-size:.7rem;'
                        f'letter-spacing:.1em;text-transform:uppercase;font-weight:600">{k}</div></div>' for k, v in cells)
        board.markdown(f"""
<div style="display:flex;gap:.6rem;flex-wrap:wrap;margin-bottom:.6rem">{tiles}</div>
<div style="height:10px;background:#e3e7ee;border-radius:5px;overflow:hidden">
  <div style="height:100%;width:{100 * frac:.0f}%;background:linear-gradient(90deg,{COLOR},#f2b134);transition:width .4s"></div></div>
<p style="margin:.4rem 0 0;color:#4a5a6c;font-size:.9rem">{stage}... {100 * frac:.0f}%</p>""", unsafe_allow_html=True)
    return update


def get_legs(days: int):
    """Load every leg once per 10 minutes for everyone on the site; show the loading screen meanwhile."""
    key = (days, int(time.time() // 600))
    store = _store()
    if key not in store:
        holder = st.empty()
        with holder.container():
            update = loading_screen()
            legs, stats = pl.load_legs(days, progress=update)
        holder.empty()
        for old in [k for k in store if k[0] == days]:
            store.pop(old)
        store[key] = (legs, stats, dt.datetime.now(dt.timezone.utc))
    return store[key]


# ------------------------------------------------------------------- page
banner("bets", "Parlay Lab",
       "Every DraftKings line ESPN carries and every open Kalshi sports market, from the NFL to college hockey, "
       "esports and cricket. Set your risk and payout; the lab simulates a million slates and shows the "
       "parlays that come out best.",
       chips=["DraftKings + Kalshi", "80,000+ markets scanned", "1,000,000 simulated slates"])

# Load the markets first, so the loading screen sits right under the banner.
legs, stats, loaded_at = get_legs(st.session_state.get("pl_days", 2))

with st.container(key="settings"):
    app = st.pills("Where will you bet?", ["DraftKings", "Kalshi", "Either (best price)"], default="DraftKings",
                   required=True, key="pl_app")
    c1, c2 = st.columns(2, gap="large")
    risk = c1.slider("Risk", 1, 10, 5, help="How unlikely a parlay you're willing to bet on. 1 = only parlays "
                     "that hit almost half the time; 10 = lottery tickets.")
    c1.caption(f"**{RISK_NAMES[risk]}**: parlays that hit at least **{pl.min_hit_chance(risk):.1%}** of the time.")
    payout = c2.select_slider("Payout", PAYOUTS, value=(3, 50), format_func=lambda x: f"{x:g}x",
                              help="Total payout as a multiple of your stake. 10x = a $10 bet pays $100.")
    c3, c4 = st.columns(2, gap="large")
    legs_range = c3.slider("Number of legs", 2, 8, (2, 4))
    stake = c4.number_input("Stake per parlay ($)", 1.0, 10_000.0, 10.0, step=5.0)
    c2.caption(f"A ${stake:,.0f} bet pays between **${stake * payout[0]:,.0f}** and **${stake * payout[1]:,.0f}**.")
    with st.expander("More options"):
        a1, a2 = st.columns(2, gap="large")
        rank_by = a1.pills("Rank by", ["Best value", "Most likely to hit", "Biggest payout"], default="Best value",
                           required=True, key="pl_rank")
        days = a2.select_slider("Games starting within", [1, 2, 3], value=2, key="pl_days",
                                format_func=lambda d: f"{d} day{'s' if d > 1 else ''}")
        markets = a1.multiselect("Bet types", list(pl.MARKETS), default=list(pl.MARKETS))
        leg_prob = a2.slider("Each leg's chance to win", 0.05, 0.95, (0.15, 0.92), 0.01, format="%.2f",
                             help="Skip heavy favorites or long shots as single legs.")
        one_per_game = a1.toggle("One leg per game", value=True,
                                 help="Legs from the same game depend on each other, so parlays here use at most "
                                      "one leg per game.")
        n_show = a2.slider("Parlays to show", 3, 20, 10)
        n_sims = a2.select_slider("Simulated slates", [100_000, 250_000, 1_000_000], value=1_000_000,
                                  format_func=lambda n: f"{n:,}")

sports = sorted({l.sport for l in legs})
with st.container(key="sport_filter"):
    picked = st.multiselect("Sports", sports, default=sports,
                            help="Everything Kalshi and DraftKings have open right now. Remove any you don't want.")

st.caption(f"Odds as of {loaded_at.astimezone(ET):%a %b %d, %I:%M %p} ET: {stats.get('scanned', 0):,} Kalshi markets "
           f"in {stats.get('leagues', 0)} leagues and {stats.get('dk_legs', 0):,} DraftKings lines → "
           f"{stats.get('legs', 0):,} legs from {stats.get('games', 0):,} games. Prices move: check them before betting.")
for note in stats.get("notes", []):
    st.caption(note)

settings = pl.Settings(app={"Either (best price)": "Either"}.get(app, app), risk=risk, payout_range=payout,
                       legs_range=legs_range, leg_prob_range=leg_prob, markets=tuple(markets),
                       sports=tuple(picked) if picked else None, one_per_game=one_per_game,
                       rank_by={"Best value": "value", "Most likely to hit": "likely", "Biggest payout": "payout"}[rank_by],
                       stake=stake, n_show=n_show)
params = (settings, n_sims, int(loaded_at.timestamp()))
if st.button(f"Find parlays · simulate {n_sims:,} slates", type="primary") or st.session_state.get("pl_params") == params:
    if st.session_state.get("pl_params") != params:
        bar = st.progress(0.0, text="Searching leg combinations...")
        try:
            sim = pl.find_parlays(legs, settings, n_sims, seed=7,
                                  progress=lambda f: bar.progress(f, text=f"Simulating {n_sims:,} slates... {int(f * n_sims):,} done"))
        except pl.ParlayError as exc:
            bar.empty()
            st.warning(str(exc))
            st.stop()
        bar.empty()
        st.session_state["pl_result"], st.session_state["pl_params"] = sim, params
else:
    st.stop()

sim: pl.Simulation = st.session_state["pl_result"]

# ------------------------------------------------------------------ results
m1, m2, m3, m4 = st.columns(4)
m1.metric("Parlays checked", f"{sim.candidates:,}")
m2.metric("Simulated slates", f"{sim.n_sims:,}")
up = float((sim.portfolio_profit > 0).mean())
m3.metric(f"Bet all {len(sim.parlays)}: chance you profit", f"{up:.0%}")
avg = float(sim.portfolio_profit.mean())
m4.metric("Bet all: average result", f"{'+' if avg >= 0 else '−'}${abs(avg):,.2f}",
          help=f"${stake:,.0f} on each shown parlay. Averaged over every simulated slate.")


def fmt_start(t: dt.datetime) -> str:
    return t.astimezone(ET).strftime("%a %I:%M %p")


for n, par in enumerate(sim.parlays, 1):
    with st.container(border=True, key=f"parlay_{n}"):
        h1, h2 = st.columns([3, 2], vertical_alignment="center")
        h1.markdown(f"**Parlay {n}** · {len(par.legs)} legs · place on **{par.app}**")
        good = par.ev > 0
        h2.markdown(f"<div style='text-align:right'><span style='font-family:Barlow Condensed,sans-serif;font-size:1.6rem;"
                    f"font-weight:700'>{par.payout:,.2f}x</span> &nbsp;<span style='color:#4a5a6c'>${stake:,.0f} → "
                    f"${stake * par.payout:,.2f}</span></div>", unsafe_allow_html=True)
        k1, k2, k3 = st.columns(3)
        k1.metric("Chance to hit", f"{par.hit:.1%}", help="Share of the simulated slates in which every leg won.")
        k2.metric("Expected value", f"{par.ev:+.1%}", help="Average profit per $1 bet, across all simulated slates. "
                  "Negative is normal: it's the bookmaker's cut.", delta=None)
        k3.metric("Worth it", f"{par.worth_it:.0%}", help="How often the bet pays more than it's likely to cost, across "
                  "1,000 plausible versions of the true odds.")
        rows = []
        for i in par.legs:
            l = legs[i]
            rows.append({"Sport": l.sport, "League": l.league, "Game": l.matchup, "Pick": l.pick, "Starts (ET)": fmt_start(l.start),
                         "DraftKings": f"{l.dk_odds:+d}" if l.dk_odds is not None else "—",
                         "Kalshi": f"{l.kalshi_ask * 100:.0f}¢" if l.kalshi_ask is not None else "—",
                         "Chance": l.p})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"Chance": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1,
                                                                            help="Our estimate, with the margin removed")})
        extra = []
        if par.dk_payout:
            extra.append(f"DraftKings pays {par.dk_payout:,.2f}x ({pl.decimal_to_american(par.dk_payout)})")
        if par.kalshi_payout:
            extra.append(f"Kalshi ≈ {par.kalshi_payout:,.2f}x if you buy all legs as a combo (estimate, incl. fees)")
        st.caption(" · ".join(extra))

# portfolio chart
st.subheader(f"If you bet all {len(sim.parlays)}")
profit = sim.portfolio_profit
total_stake = stake * len(sim.parlays)
lost_all = float((profit <= -total_stake + 1e-6).mean())
r1, r2, r3 = st.columns(3)
r1.metric("Lose every parlay", f"{lost_all:.0%}")
r2.metric("Come out ahead", f"{up:.0%}")
r3.metric("Best 1 in 100 slates", f"+${max(0.0, float(np.percentile(profit, 99))):,.0f} or more")
# Group the results into readable ranges.
edges = np.unique(np.concatenate([[-total_stake - 0.01, -0.01, 0.01],
                                  np.quantile(profit[profit > 0.01], np.linspace(0, 1, 7)) if (profit > 0.01).any() else []]))
labels, shares, kinds = [], [], []
for lo, hi in zip(edges[:-1], edges[1:]):
    share = float(((profit > lo) & (profit <= hi + 1e-6)).mean())
    if share < 0.0005:
        continue
    if hi <= -0.01:
        labels.append(f"Lose ${-lo:,.0f}" if abs(lo + total_stake + 0.01) < 0.02 else f"Lose ${-hi:,.0f}–${-lo:,.0f}")
        kinds.append("Loss")
    elif hi <= 0.01:
        labels.append("Break even")
        kinds.append("Break even")
    else:
        labels.append(f"Win ${max(lo, 0):,.0f}–${hi:,.0f}")
        kinds.append("Profit")
    shares.append(100 * share)
df = pd.DataFrame({"Result": labels, "Share of slates %": shares, "Kind": kinds})
chart = alt.Chart(df).mark_bar(cornerRadiusEnd=4, height=22).encode(
    y=alt.Y("Result:N", sort=labels, title=None, axis=alt.Axis(labelLimit=220)),
    x=alt.X("Share of slates %:Q", title="% of simulated slates"),
    color=alt.Color("Kind:N", scale=alt.Scale(domain=["Loss", "Break even", "Profit"],
                                              range=["#c75a1c", "#a3a29c", "#2e7d3a"]), legend=None),
    tooltip=["Result", alt.Tooltip("Share of slates %:Q", format=".2f")]).properties(height=alt.Step(32))
text = chart.mark_text(align="left", dx=4).encode(text=alt.Text("Share of slates %:Q", format=".1f"),
                                                   color=alt.value("#4a5a6c"))
st.altair_chart(chart + text, width="stretch")
st.caption(f"You'd stake ${stake * len(sim.parlays):,.0f} in total. Parlays that share legs win and lose together, "
           "which the simulation accounts for.")

with st.expander("How Parlay Lab works"):
    st.markdown("""
1. **Collect every line.** DraftKings moneylines, spreads and totals (via ESPN) and every open Kalshi sports
   market: winners, spreads, totals, player props and more, both Yes and No.
2. **Find the real chances.** Each price includes the bookmaker's cut. Removing it gives a fair chance for each
   leg; when DraftKings and Kalshi both list a game, the two are averaged.
3. **Simulate a million slates.** Those chances are estimates, so each of 1,000 scenarios nudges them a little,
   and each scenario plays every game 1,000 times.
4. **Score every parlay** that fits your risk, payout and legs on the same million slates: how often it hits,
   what it pays, and its expected value. The best ones are shown.

**Good to know:** most parlays lose money over time, because every leg carries the bookmaker's cut.
Positive expected value only shows up where DraftKings and Kalshi disagree. Kalshi parlay payouts are
estimates (Kalshi prices combos live). Legs from the same game are kept apart because they move together.
""")

st.divider()
st.caption("For entertainment and education only, not betting advice. Odds change constantly; always check the price "
           "before you bet. Must be 21+ and in a state where DraftKings or Kalshi is legal. If gambling stops being "
           "fun, call 1-800-GAMBLER. Not affiliated with DraftKings, Kalshi or ESPN.")
