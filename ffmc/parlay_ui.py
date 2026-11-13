"""Streamlit pieces shared by Parlay Lab and Niche Sports: loading screen, shared scan, results."""

from __future__ import annotations

import datetime as dt
import time
from zoneinfo import ZoneInfo

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from . import parlay as pl
from .ui import SPORTS

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
    "Looking for Russian table tennis and Bosnian basketball...",
    "Fun fact: every extra leg multiplies the house's edge.",
    "Rolling a million possible weekends...",
]


@st.cache_resource
def _store() -> dict:
    return {}


def loading_screen(color: str):
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
  <div style="height:100%;width:{100 * frac:.0f}%;background:linear-gradient(90deg,{color},#f2b134);transition:width .4s"></div></div>
<p style="margin:.4rem 0 0;color:#4a5a6c;font-size:.9rem">{stage}... {100 * frac:.0f}%</p>""", unsafe_allow_html=True)
    return update


def get_legs(color: str):
    """One shared scan of the next 7 days for everyone on the site, refreshed every 10 minutes."""
    key = int(time.time() // 600)
    store = _store()
    if key not in store:
        holder = st.empty()
        with holder.container():
            update = loading_screen(color)
            legs, stats = pl.load_legs(pl.SCAN_DAYS, progress=update)
        holder.empty()
        store.clear()
        store[key] = (legs, stats, dt.datetime.now(dt.timezone.utc))
    return store[key]


def fmt_start(t: dt.datetime) -> str:
    return t.astimezone(ET).strftime("%a %b %d, %I:%M %p")


def bet_controls(app_default: str = "DraftKings", risk_default: int = 5, payout_default=(3, 50),
                 legs_default=(2, 4), min_legs: int = 2, key: str = "pl"):
    """Where / risk / payout / legs / stake controls. Returns a dict."""
    app = st.pills("Where will you bet?", ["DraftKings", "Kalshi", "Either (best price)"], default=app_default,
                   required=True, key=f"{key}_app")
    c1, c2 = st.columns(2, gap="large")
    risk = c1.slider("Risk", 1, 10, risk_default, key=f"{key}_risk",
                     help="How unlikely a bet you're willing to make. 1 = only bets that hit almost half the time; "
                          "10 = lottery tickets.")
    c1.caption(f"**{RISK_NAMES[risk]}**: bets that hit at least **{pl.min_hit_chance(risk):.1%}** of the time.")
    payout = c2.select_slider("Payout", PAYOUTS, value=payout_default, format_func=lambda x: f"{x:g}x", key=f"{key}_pay",
                              help="Total payout as a multiple of your stake. 10x = a $10 bet pays $100.")
    c3, c4 = st.columns(2, gap="large")
    legs_range = c3.slider("Number of legs", min_legs, 8, legs_default, key=f"{key}_legs")
    stake = c4.number_input("Stake per bet ($)", 1.0, 10_000.0, 10.0, step=5.0, key=f"{key}_stake")
    c2.caption(f"A ${stake:,.0f} bet pays between **${stake * payout[0]:,.0f}** and **${stake * payout[1]:,.0f}**.")
    return dict(app={"Either (best price)": "Either"}.get(app, app), risk=risk, payout=payout, legs_range=legs_range,
                stake=stake)


def run_search(legs: list[pl.Leg], settings: pl.Settings, n_sims: int, params, key: str, button: str):
    """Button + progress bar; returns the Simulation (kept across reruns) or stops the page."""
    if st.button(button, type="primary") or st.session_state.get(f"{key}_params") == params:
        if st.session_state.get(f"{key}_params") != params:
            bar = st.progress(0.0, text="Searching leg combinations...")
            try:
                sim = pl.find_parlays(legs, settings, n_sims, seed=7,
                                      progress=lambda f: bar.progress(f, text=f"Simulating {n_sims:,} slates... "
                                                                              f"{int(f * n_sims):,} done"))
            except pl.ParlayError as exc:
                bar.empty()
                st.warning(str(exc))
                st.stop()
            bar.empty()
            st.session_state[f"{key}_result"], st.session_state[f"{key}_params"] = sim, params
        return st.session_state[f"{key}_result"]
    st.stop()


def render_results(sim: pl.Simulation, legs: list[pl.Leg], stake: float, show_niche: bool = False) -> None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Combinations checked", f"{sim.candidates:,}")
    m2.metric("Simulated slates", f"{sim.n_sims:,}")
    up = float((sim.portfolio_profit > 0).mean())
    m3.metric(f"Bet all {len(sim.parlays)}: chance you profit", f"{up:.0%}")
    avg = float(sim.portfolio_profit.mean())
    m4.metric("Bet all: average result", f"{'+' if avg >= 0 else '−'}${abs(avg):,.2f}",
              help=f"${stake:,.0f} on each shown bet. Averaged over every simulated slate.")

    for n, par in enumerate(sim.parlays, 1):
        with st.container(border=True, key=f"parlay_{n}"):
            h1, h2 = st.columns([3, 2], vertical_alignment="center")
            kind = f"Bet {n} · single" if len(par.legs) == 1 else f"Parlay {n} · {len(par.legs)} legs"
            h1.markdown(f"**{kind}** · place on **{par.app}**")
            h2.markdown(f"<div style='text-align:right'><span style='font-family:Barlow Condensed,sans-serif;font-size:1.6rem;"
                        f"font-weight:700'>{par.payout:,.2f}x</span> &nbsp;<span style='color:#4a5a6c'>${stake:,.0f} → "
                        f"${stake * par.payout:,.2f}</span></div>", unsafe_allow_html=True)
            k1, k2, k3 = st.columns(3)
            k1.metric("Chance to hit", f"{par.hit:.1%}", help="Share of the simulated slates in which every leg won.")
            k2.metric("Expected value", f"{par.ev:+.1%}", help="Average profit per $1 bet, across all simulated slates. "
                      "Negative is normal: it's the bookmaker's cut.")
            k3.metric("Worth it", f"{par.worth_it:.0%}", help="How often the bet pays more than it's likely to cost, "
                      "across 1,000 plausible versions of the true odds.")
            rows = []
            for i in par.legs:
                l = legs[i]
                row = {"Sport": l.sport, "League": l.league, "Game": l.matchup, "Pick": l.pick,
                       "When (ET)": fmt_start(l.start),
                       "DraftKings": f"{l.dk_odds:+d}" if l.dk_odds is not None else "—",
                       "Kalshi": f"{l.kalshi_ask * 100:.0f}¢" if l.kalshi_ask is not None else "—", "Chance": l.p}
                if show_niche:
                    row["Niche"] = "●" * min(l.niche, 7)
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         column_config={"Chance": st.column_config.ProgressColumn(
                             format="percent", min_value=0, max_value=1, help="Our estimate, with the margin removed")})
            extra = []
            if par.dk_payout:
                extra.append(f"DraftKings pays {par.dk_payout:,.2f}x ({pl.decimal_to_american(par.dk_payout)})")
            if par.kalshi_payout:
                extra.append(f"Kalshi ≈ {par.kalshi_payout:,.2f}x" + (" if you buy all legs as a combo (estimate, incl. fees)"
                                                                      if len(par.legs) > 1 else " (incl. fees)"))
            st.caption(" · ".join(extra))

    st.subheader(f"If you bet all {len(sim.parlays)}")
    profit = sim.portfolio_profit
    total_stake = stake * len(sim.parlays)
    lost_all = float((profit <= -total_stake + 1e-6).mean())
    r1, r2, r3 = st.columns(3)
    r1.metric("Lose every bet", f"{lost_all:.0%}")
    r2.metric("Come out ahead", f"{up:.0%}")
    r3.metric("Best 1 in 100 slates", f"+${max(0.0, float(np.percentile(profit, 99))):,.0f} or more")
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
    st.caption(f"You'd stake ${total_stake:,.0f} in total. Bets that share legs win and lose together, "
               "which the simulation accounts for.")


GAMBLING_NOTE = ("For entertainment and education only, not betting advice. Odds change constantly; always check the "
                 "price before you bet. Must be 21+ and in a state where DraftKings or Kalshi is legal. If gambling stops "
                 "being fun, call 1-800-GAMBLER. Not affiliated with DraftKings, Kalshi or ESPN.")
