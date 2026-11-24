"""Best Bets page: teams our simulations rate higher than Kalshi does."""

from __future__ import annotations

import streamlit as st

from ffmc.live_view import CSS, render_best_bets
from ffmc.ui import banner

st.markdown(CSS, unsafe_allow_html=True)
banner("edge", "Best Bets",
       "Bets priced below their fair chance. DraftKings and Kalshi together are the best predictor of who wins, so "
       "their consensus sets each team's fair chance; a bet is real value when one of them sells it for less, by "
       "enough to beat the fees. We also show where our own 1,000,000-game simulation disagrees, and why.",
       chips=["DraftKings + Kalshi consensus", "Expected return after fees", "Exact payout for your stake"])
render_best_bets()
st.divider()
st.caption("Prices from Kalshi's public market data and DraftKings via ESPN. Not affiliated with ESPN, DraftKings "
           "or Kalshi.")
