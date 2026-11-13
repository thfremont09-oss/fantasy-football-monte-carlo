"""Parlay Lab page: Monte Carlo parlay finder for DraftKings and Kalshi."""

from __future__ import annotations

import streamlit as st

from ffmc import parlay as pl
from ffmc import parlay_ui as ui
from ffmc.ui import SPORTS, banner

COLOR = SPORTS["bets"]["color"]

banner("bets", "Parlay Lab",
       "Every DraftKings line ESPN carries and every open Kalshi sports market, from the NFL to college hockey, "
       "esports and cricket. Set your risk and payout; the lab simulates a million slates and shows the "
       "parlays that come out best.",
       chips=["DraftKings + Kalshi", "80,000+ markets scanned", "1,000,000 simulated slates"])

# Load the markets first, so the loading screen sits right under the banner.
all_legs, stats, loaded_at = ui.get_legs(COLOR)

with st.container(key="settings"):
    bet = ui.bet_controls(key="pl")
    with st.expander("More options"):
        a1, a2 = st.columns(2, gap="large")
        rank_by = a1.pills("Rank by", ["Best value", "Most likely to hit", "Biggest payout"], default="Best value",
                           required=True, key="pl_rank")
        days = a2.select_slider("Games starting within", [1, 2, 3, 5, 7], value=2, key="pl_days",
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

legs = pl.within(all_legs, days, max_spread=0.15)
sports = sorted({l.sport for l in legs})
with st.container(key="sport_filter"):
    picked = st.multiselect("Sports", sports, default=sports,
                            help="Everything DraftKings and Kalshi have open right now. Remove any you don't want.")

st.caption(f"Odds as of {loaded_at.astimezone(ui.ET):%a %b %d, %I:%M %p} ET: {stats.get('scanned', 0):,} Kalshi markets "
           f"in {stats.get('leagues', 0)} leagues and {stats.get('dk_legs', 0):,} DraftKings lines → "
           f"{len(legs):,} legs in the next {days} day{'s' if days > 1 else ''}. Prices move: check them before betting.")
for note in stats.get("notes", []):
    st.caption(note)

settings = pl.Settings(app=bet["app"], risk=bet["risk"], payout_range=bet["payout"], legs_range=bet["legs_range"],
                       leg_prob_range=leg_prob, markets=tuple(markets), sports=tuple(picked) if picked else None,
                       one_per_game=one_per_game,
                       rank_by={"Best value": "value", "Most likely to hit": "likely", "Biggest payout": "payout"}[rank_by],
                       stake=bet["stake"], n_show=n_show)
params = (settings, n_sims, days, int(loaded_at.timestamp()))
sim = ui.run_search(legs, settings, n_sims, params, key="pl", button=f"Find parlays · simulate {n_sims:,} slates")
ui.render_results(sim, legs, bet["stake"])

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
st.caption(ui.GAMBLING_NOTE)
