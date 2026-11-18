"""Best Bets page: teams our simulations rate higher than Kalshi does."""

from __future__ import annotations

import streamlit as st

from ffmc.live_view import CSS, render_best_bets
from ffmc.ui import banner

st.markdown(CSS, unsafe_allow_html=True)
banner("edge", "Best Bets",
       "Where our simulations rate a team higher than Kalshi does. Every upcoming game is played 1,000,000 times; "
       "these are the teams that win more often in our sims than their Kalshi price says, biggest gap first.",
       chips=["Upcoming games", "Biggest gap first", "Exact payout for your stake"])
render_best_bets()
st.divider()
st.caption("Prices from Kalshi's public market data and DraftKings via ESPN. Not affiliated with ESPN, DraftKings "
           "or Kalshi.")
