"""Monte Carlo Sports Lab web app.  Run with:  streamlit run app.py"""

import streamlit as st

from ffmc.ui import APP_VERSION, apply_site_css

st.set_page_config(page_title="Monte Carlo Sports Lab", page_icon=":material/query_stats:", layout="wide")

home = st.Page("views/home.py", title="Home", icon=":material/home:", default=True)
football = st.Page("views/football.py", title="NFL Fantasy Lineups", icon=":material/sports_football:",
                   url_path="football")
madness = st.Page("views/march_madness.py", title="March Madness", icon=":material/sports_basketball:",
                  url_path="march-madness")
fpl = st.Page("views/fpl.py", title="Fantasy Premier League", icon=":material/sports_soccer:", url_path="fpl")
parlays = st.Page("views/parlays.py", title="Parlay Lab", icon=":material/casino:", url_path="parlays")
niche = st.Page("views/niche.py", title="Niche Sports", icon=":material/explore:", url_path="niche")
live = st.Page("views/live.py", title="Live Odds", icon=":material/live_tv:", url_path="live")
PAGES = [home, live, football, madness, fpl, parlays, niche]
SHORT = {"live": "Live", "football": "NFL", "march-madness": "Bracket", "fpl": "FPL", "parlays": "Parlays",
         "niche": "Niche"}                            # short labels so all tabs fit across the header
page = st.navigation(PAGES, position="hidden")

apply_site_css()

with st.container(key="site_header"):
    brand, nav, menu = st.columns([3, 6, 1], vertical_alignment="center")
    with brand, st.container(key="brand"):
        st.page_link(home, label="Monte Carlo Sports Lab")
    # Desktop: plain links across the header. Phones: a menu button instead (CSS picks one).
    with nav, st.container(key="nav_col"), st.container(key="nav_inline", horizontal=True):
        for p in PAGES[1:]:
            with st.container(key=f"navlink_{'on' if p.url_path == page.url_path else 'off'}_{p.url_path}",
                              width="content"):
                st.page_link(p, label=SHORT.get(p.url_path, p.title))
    with menu, st.container(key="menu_col"):
        # A separate key per page, so the menu starts closed after you navigate.
        with st.popover("Menu", icon=":material/menu:", key=f"menu_{page.url_path or 'home'}"), \
                st.container(key="menu_items"):
            for p in PAGES:
                st.page_link(p, label=p.title, width="stretch")
            st.caption(f"Version {APP_VERSION}")

page.run()
