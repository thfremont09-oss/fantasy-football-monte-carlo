"""Monte Carlo Sports Lab web app.  Run with:  streamlit run app.py"""

import streamlit as st

APP_VERSION = "2026-11-12c"  # bump on each release so you can tell which version is live

st.set_page_config(page_title="Monte Carlo Sports Lab", page_icon=":material/query_stats:", layout="wide")

home = st.Page("views/home.py", title="Home", icon=":material/home:", default=True)
football = st.Page("views/football.py", title="Fantasy Football Lineup Optimizer",
                   icon=":material/sports_football:", url_path="football")
madness = st.Page("views/march_madness.py", title="March Madness Bracket Simulator",
                  icon=":material/sports_basketball:", url_path="march-madness")
page = st.navigation([home, football, madness], position="hidden")

st.markdown("""
<style>
/* Page frame */
.block-container { max-width: 1140px; padding-top: 1.25rem; }
[data-testid="stDecoration"] { display: none; }
header[data-testid="stHeader"] { background: transparent; }

/* Site header */
.st-key-site_header { border-bottom: 1px solid #e2dfd6; padding-bottom: 0.6rem; margin-bottom: 1.2rem; }
.st-key-site_header a[data-testid="stPageLink-NavLink"] p {
  font-family: "Source Serif 4", serif; font-size: 1.3rem; font-weight: 600; letter-spacing: -0.01em; }
.st-key-site_header a[data-testid="stPageLink-NavLink"] { padding-left: 0; background: none; }
.st-key-brand a[data-testid="stPageLink-NavLink"] > span:first-child { display: none; }
/* keep brand and menu on one line on phones */
.st-key-site_header [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; gap: 0.75rem; }
.st-key-site_header [data-testid="stColumn"] { min-width: 0 !important; }
.st-key-site_header [data-testid="stColumn"]:last-child { flex: 0 0 auto !important; width: auto !important; }

/* Type */
.eyebrow { text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.72rem; font-weight: 600;
           color: #1d5c4a; margin-bottom: 0.2rem; }
h1.hero { font-size: clamp(2rem, 5vw, 3.1rem); line-height: 1.1; letter-spacing: -0.02em;
          max-width: 18ch; padding: 0.2rem 0 0.8rem 0; }
p.lead { font-size: 1.12rem; line-height: 1.6; color: #3d424a; max-width: 62ch; margin-bottom: 1.6rem; }
h1, h2, h3, h1.hero { font-family: "Source Serif 4", Georgia, serif !important; letter-spacing: -0.01em; }
[data-testid="stMetricValue"] { font-family: "Source Serif 4", serif; }
</style>
""", unsafe_allow_html=True)

with st.container(key="site_header"):
    brand, menu = st.columns([5, 1], vertical_alignment="center")
    with brand, st.container(key="brand"):
        st.page_link(home, label="Monte Carlo Sports Lab")
    with menu:
        with st.popover("Menu", icon=":material/menu:"):
            st.page_link(home, label="Home")
            st.page_link(football, label="Fantasy Football Lineup Optimizer")
            st.page_link(madness, label="March Madness Bracket Simulator")
            st.caption(f"Version {APP_VERSION}")

page.run()
