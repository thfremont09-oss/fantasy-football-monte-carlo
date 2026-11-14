"""Live Odds page: scores plus DraftKings and Kalshi odds for the top leagues.

Click any game for its stats and a live odds chart. Everything refreshes every 15 seconds.
The shared pieces (data, cards, the game page) live in ffmc/live_view.py.
"""

from __future__ import annotations

import datetime as dt
import html

import streamlit as st

from ffmc import live
from ffmc.live_view import (CSS, ET, REFRESH, board, card, game_view, next_games, schedule, week)
from ffmc.ui import banner

# --------------------------------------------------------------------- page
st.markdown(CSS, unsafe_allow_html=True)
game_key = st.query_params.get("game")

if game_key:
    c1, c2 = st.columns([1, 1])
    if c1.button("← All games", key="gd_back"):
        st.query_params.clear()
        st.rerun()
    c2.selectbox("Chart time span", ["Last 6 hours", "Last 24 hours", "Last 3 days"], key="gd_span",
                 index=None, placeholder="Chart time span (auto)", label_visibility="collapsed")
    st.fragment(game_view, run_every=REFRESH)(game_key, st.query_params.get("d"))
    st.stop()

banner("live", "Live Odds",
       "Scores and odds for the top leagues around the world, in one place: DraftKings lines next to Kalshi's live "
       "win chances, updating every 15 seconds. Click any game for its stats and live odds chart.",
       chips=["NFL · NBA · NHL · MLB · college", "Europe's top soccer + more", "Tennis · UFC"])

@st.cache_data(ttl=86400, show_spinner=False)
def search_options() -> tuple[list[str], list]:
    """Every team and league name, for the type-ahead search box."""
    index = live.team_index()
    names = sorted({n[0] for _, _, n in index} | {l[1] for l in live.LEAGUES}, key=str.lower)
    return names, index


league_names = [l[1] for l in live.LEAGUES]
today_tab, sched_tab = st.tabs(["Live & today", "Schedule · next 7 days"])

with today_tab, st.container(key="settings"):
    names, team_idx = search_options()
    picked = st.selectbox("Search teams, players or leagues", names, index=None, accept_new_options=True,
                          placeholder="Start typing: Bayern, Lakers, Arsenal, Sabalenka, UFC...", key="lv_q")
    query = (picked or "").strip()
    fixed = live.correct(query, team_idx) if query and query not in names else None
    if fixed:
        st.caption(f"No exact match for “{query}”. Showing results for **{fixed}**.")
        query = fixed
    f1, f2 = st.columns([2, 3], gap="large")
    status = f1.pills("Show", ["All", "Live now", "Upcoming", "Final"], default="All", required=True, key="lv_status")
    picked_leagues = f2.multiselect("Leagues", league_names, default=[], key="lv_leagues",
                                    placeholder="All leagues (or pick some)")
    leagues = picked_leagues or league_names     # nothing picked = every league
    auto = st.toggle(f"Auto-refresh every {REFRESH} seconds", value=True, key="lv_auto")


def grid(games: list[live.Game], sched: bool = False) -> str:
    return f'<div class="lv-grid">{"".join(card(g, sched) for g in games)}</div>'


@st.fragment(run_every=REFRESH if auto else None)
def live_board():
    if "lv_loaded" not in st.session_state:      # spinner only on the first load, not on every refresh
        with st.spinner("Loading scores and odds..."):
            games, fetched = board()
        st.session_state["lv_loaded"] = True
    else:
        games, fetched = board()
    shown = [g for g in games if g.league in set(leagues) and (not query or g.matches(query))]
    want = {"Live now": "in", "Upcoming": "pre", "Final": "post"}.get(status)
    if want:
        shown = [g for g in shown if g.state == want]
    n_live = sum(g.state == "in" for g in games)
    st.caption(f"Updated {fetched.astimezone(ET):%I:%M:%S %p} ET · {len(games)} games across {len(live.LEAGUES)} leagues · "
               f"{n_live} live now · DraftKings via ESPN, live chances from Kalshi · click a game for stats")
    if query:
        # A team's next game, however far away (one per competition it plays in).
        ahead = [g for g in next_games(query) if g.key not in {x.key for x in shown}]
        if ahead:
            st.markdown(f'<div class="lv-count">Next game{"s" if len(ahead) > 1 else ""} · {html.escape(query)}</div>'
                        + grid(ahead, sched=True), unsafe_allow_html=True)
    if not shown:
        if not query:
            st.info("No games match. Try more leagues, or **All**.")
        elif not ahead:
            st.info("No games found for that search. Try a team, player or league name.")
        return
    for label, state in (("Live now", "in"), ("Upcoming", "pre"), ("Final", "post")):
        part = [g for g in shown if g.state == state]
        if part:
            st.markdown(f'<div class="lv-count">{label} · {len(part)}</div>'
                        f'<div class="lv-grid">{"".join(card(g) for g in part[:120])}</div>', unsafe_allow_html=True)
            if len(part) > 120:
                st.caption(f"Showing 120 of {len(part)}. Search or pick leagues to narrow it down.")


with today_tab:
    live_board()

with sched_tab:
    st.markdown("Pick a league to see its games for the next week, with odds where they're posted. "
                "Choose a day to see just that day.")
    s1, s2 = st.columns(2, gap="large")
    sched_league = s1.selectbox("League", league_names, index=None, placeholder="Choose a league", key="sc_league")
    today = dt.datetime.now(ET).date()
    days = [today + dt.timedelta(i) for i in range(8)]
    label = lambda d: ("Today · " if d == today else "Tomorrow · " if d == today + dt.timedelta(1) else "") + \
        f"{d:%A, %b} {d.day}"
    sched_day = s2.selectbox("Day", days, index=None, format_func=label, placeholder="All 7 days", key="sc_day")
    if sched_league:
        with st.spinner(f"Loading the {sched_league} schedule..."):
            games = schedule(sched_league, sched_day) if sched_day else week(sched_league, today)
        if not games:
            st.info(f"No {sched_league} games {'on ' + label(sched_day) if sched_day else 'in the next 7 days'}. "
                    "It may be an off week or the off-season.")
        for d in sorted({g.start.astimezone(ET).date() for g in games}):
            part = [g for g in games if g.start.astimezone(ET).date() == d]
            st.markdown(f'<div class="lv-day">{label(d)} · {len(part)} game{"s" if len(part) != 1 else ""}</div>'
                        + grid(part, sched=True), unsafe_allow_html=True)

st.divider()
st.caption("Scores, stats and DraftKings odds via ESPN; live prices and charts from Kalshi's public market data. For "
           "information only, not betting advice. Must be 21+; if gambling stops being fun, call 1-800-GAMBLER. Not "
           "affiliated with ESPN, DraftKings or Kalshi.")
