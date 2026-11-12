"""Monte Carlo Sports Lab web app.  Run with:  streamlit run app.py"""

import streamlit as st

APP_VERSION = "2026-11-12d"  # bump on each release so you can tell which version is live

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
header[data-testid="stHeader"] { background: transparent; pointer-events: none; }
/* Streamlit's invisible top bar overlaps our header; let taps pass through it,
   except on its own buttons (e.g. the sidebar toggle). */
header[data-testid="stHeader"] * { pointer-events: none !important; }
header[data-testid="stHeader"] button, header[data-testid="stHeader"] button *,
header[data-testid="stHeader"] a, header[data-testid="stHeader"] a * { pointer-events: auto !important; }

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

/* Menu: big tap targets. The whole row is the link, not just its text. */
.st-key-site_header [data-testid="stPopover"] button { min-height: 44px; padding: 0 1rem; }
[data-testid="stPopoverBody"]:has(.st-key-menu_items) { min-width: min(320px, 90vw); padding: 0.4rem; }
.st-key-menu_items { gap: 2px; }
.st-key-menu_items > [data-testid="stElementContainer"] { margin: 0 !important; }
.st-key-menu_items [data-testid="stPageLink"],
.st-key-menu_items [data-testid="stPageLink"] > div { width: 100%; }
.st-key-menu_items a[data-testid="stPageLink-NavLink"] {
  display: flex; align-items: center; width: 100%; min-height: 48px; padding: 0 0.85rem;
  border-radius: 6px; -webkit-tap-highlight-color: rgba(29, 92, 74, 0.12); }
.st-key-menu_items a[data-testid="stPageLink-NavLink"]:hover,
.st-key-menu_items a[data-testid="stPageLink-NavLink"]:active { background: #ebe8df; }
.st-key-menu_items a[data-testid="stPageLink-NavLink"] p { font-size: 1rem; }
.st-key-menu_items [data-testid="stCaptionContainer"] { padding: 0.4rem 0.85rem 0.2rem; }

/* Homepage card links: full width, finger-sized */
[class*="st-key-card_link"] [data-testid="stPageLink"], [class*="st-key-card_link"] [data-testid="stPageLink"] > div { width: 100%; }
[class*="st-key-card_link"] a[data-testid="stPageLink-NavLink"] {
  display: flex; align-items: center; width: 100%; min-height: 46px; padding: 0 0.85rem;
  border: 1px solid #e2dfd6; border-radius: 6px; background: #f2f0ea; }
[class*="st-key-card_link"] a[data-testid="stPageLink-NavLink"]:hover { background: #ebe8df; border-color: #1d5c4a; }

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
        # A separate key per page, so the menu starts closed after you navigate.
        with st.popover("Menu", icon=":material/menu:", key=f"menu_{page.url_path or 'home'}"), \
                st.container(key="menu_items"):
            st.page_link(home, label="Home", width="stretch")
            st.page_link(football, label="Fantasy Football Lineup Optimizer", width="stretch")
            st.page_link(madness, label="March Madness Bracket Simulator", width="stretch")
            st.caption(f"Version {APP_VERSION}")

page.run()
