"""Best Bets page: the best moneyline bets to make right now, on Kalshi or DraftKings."""

from __future__ import annotations

import streamlit as st

from ffmc.live_view import CSS, render_best_bets
from ffmc.ui import banner

st.markdown(CSS, unsafe_allow_html=True)
banner("bets", "Best Bets Now",
       "The best win/lose bets on upcoming games, on Kalshi or DraftKings: each app's price is checked against "
       "the other's, and every pick is played out 1,000,000 times.",
       chips=["Kalshi or DraftKings", "Upcoming games, every top league", "Refreshes every minute"])
render_best_bets()
st.divider()
st.caption("Prices from Kalshi's public market data and DraftKings via ESPN. Not affiliated with ESPN, DraftKings "
           "or Kalshi.")
