"""Sports Monte Carlo web app.  Run with:  streamlit run app.py"""

import streamlit as st

st.set_page_config(page_title="Sports Monte Carlo", page_icon="🎲", layout="wide")

page = st.navigation([
    st.Page("views/football.py", title="Football", icon="🏈", default=True),
    st.Page("views/march_madness.py", title="March Madness", icon="🏀"),
], position="top")
page.run()
