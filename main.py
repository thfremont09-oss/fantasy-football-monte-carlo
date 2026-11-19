"""Monte Sports Lab: the Streamlit site. Start it with  streamlit run app.py  (which adds the search routes)."""

from pathlib import Path

import streamlit as st

from ffmc.ui import APP_VERSION, apply_site_css, theme_button
from seo.content import NAME, PAGE_BY_PATH

ICON = str(Path(__file__).parent / "static" / "brand" / "icon-192.png")

st.set_page_config(page_title=NAME, page_icon=ICON, layout="wide")

home = st.Page("views/home.py", title="Home", icon=":material/home:", default=True)
football = st.Page("views/football.py", title="NFL Fantasy Lineups", icon=":material/sports_football:",
                   url_path="football")
madness = st.Page("views/march_madness.py", title="March Madness", icon=":material/sports_basketball:",
                  url_path="march-madness")
fpl = st.Page("views/fpl.py", title="Fantasy Premier League", icon=":material/sports_soccer:", url_path="fpl")
parlays = st.Page("views/parlays.py", title="Parlay Lab", icon=":material/casino:", url_path="parlays")
niche = st.Page("views/niche.py", title="Niche Sports", icon=":material/explore:", url_path="niche")
live = st.Page("views/live.py", title="Live Odds", icon=":material/live_tv:", url_path="live")
bets = st.Page("views/bets.py", title="Best Bets Now", icon=":material/trending_up:", url_path="bets")
f1 = st.Page("views/f1.py", title="F1 Fantasy", icon=":material/sports_motorsports:", url_path="f1")
method = st.Page("views/method.py", title="How it works", icon=":material/menu_book:", url_path="how-it-works")
players = st.Page("views/players.py", title="Player Stats", icon=":material/person_search:",
                    url_path="players")
record = st.Page("views/record.py", title="Track record", icon=":material/insights:", url_path="track-record")
PAGES = [home, live, bets, players, football, madness, fpl, f1, parlays, niche, record, method]
SHORT = {"live": "Live", "bets": "Bets", "players": "Players", "football": "NFL", "march-madness": "Bracket", "fpl": "FPL", "f1": "F1", "parlays": "Parlays", "track-record": "Record", "how-it-works": "How it works",
         "niche": "Niche"}                            # short labels so all tabs fit across the header
page = st.navigation(PAGES, position="hidden")

# What the browser tab (and Google) shows for each page: seo/content.py.
st.set_page_config(page_title=PAGE_BY_PATH[page.url_path].title if page.url_path in PAGE_BY_PATH else NAME)

apply_site_css()

with st.container(key="site_header"):
    brand, nav, theme, menu = st.columns([3, 6, 1, 1], vertical_alignment="center")
    with theme, st.container(key="theme_col"):
        theme_button([p.url_path for p in PAGES], page.url_path)
    with brand, st.container(key="brand"), st.container(key="brand_home" if page.url_path == "" else "brand_away"):
        st.page_link(home, label="Monte Sports Lab", help="Home")
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
