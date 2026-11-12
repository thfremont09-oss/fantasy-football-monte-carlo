"""Sports Monte Carlo web app.  Run with:  streamlit run app.py"""

import streamlit as st

st.set_page_config(page_title="Sports Monte Carlo", page_icon="🎲", layout="wide")

PAGES = {
    "🏈  Football": st.Page("views/football.py", title="Football", icon="🏈", default=True),
    "🏀  March Madness": st.Page("views/march_madness.py", title="March Madness", icon="🏀"),
}
page = st.navigation(list(PAGES.values()), position="hidden")
current = next(name for name, p in PAGES.items() if p.url_path == page.url_path)

# Big sport switcher at the top of every page. Each page gets its own widget key,
# so it always starts out showing the page you're on.
st.markdown("""
<style>
[class*="st-key-sport"] button { min-height: 3.2rem; }
[class*="st-key-sport"] button p { font-size: 1.2rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)
choice = st.segmented_control("Choose a sport", list(PAGES), default=current, required=True,
                              key=f"sport_{page.url_path or 'home'}", label_visibility="collapsed",
                              width="stretch")
if choice != current:
    st.switch_page(PAGES[choice])

page.run()
