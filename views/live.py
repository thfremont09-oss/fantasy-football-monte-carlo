"""Live Odds page: scores plus DraftKings and Kalshi odds for the top leagues, with Kalshi charts."""

from __future__ import annotations

import datetime as dt
import html
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from ffmc import live
from ffmc.ui import SPORTS, banner

COLOR = SPORTS["live"]["color"]
ET = ZoneInfo("America/New_York")
SIDE_COLORS = ["#2a78d6", "#eb6834"]
DRAW_COLOR = "#8a8f98"


@st.cache_data(ttl=25, show_spinner=False)
def board() -> tuple[list[live.Game], dt.datetime]:
    return live.load_board(), dt.datetime.now(dt.timezone.utc)


@st.cache_data(ttl=30, show_spinner=False)
def history(series: str, ticker: str, hours: float, interval: int):
    return live.kalshi_history(series, ticker, hours, interval)


def american(o: int | None) -> str:
    return "—" if o is None else (f"+{o}" if o > 0 else str(o))


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def status_html(g: live.Game) -> str:
    if g.state == "in":
        return f'<span class="lv-live"><i></i>LIVE · {html.escape(g.detail)}</span>'
    if g.state == "post":
        return f'<span class="lv-final">{html.escape(g.detail or "Final")}</span>'
    return f'<span class="lv-pre">{g.start.astimezone(ET):%a %I:%M %p} ET</span>'


def card(g: live.Game) -> str:
    rows = []
    best = max(range(len(g.sides)), key=lambda i: g.sides[i].kalshi or 0) if g.kalshi_updated else None
    for i, s in enumerate(g.sides):
        # A background image shows nothing (rather than a broken-image icon) if the logo can't load.
        logo = (f'<span class="lv-logo" style="background-image:url(\'{html.escape(s.logo)}\')"></span>'
                if s.logo else '<span class="lv-nologo"></span>')
        win = " lv-win" if s.winner else ""
        bar = (f'<span class="lv-bar"><b style="width:{(s.kalshi or 0) * 100:.0f}%;background:{SIDE_COLORS[i % 2]}"></b></span>'
               if s.kalshi is not None else "")
        rec = f'<small>{html.escape(s.record)}</small>' if s.record else ""
        odds = ("" if g.state == "post" else f'<td class="lv-dk">{american(s.dk)}</td>'
                f'<td class="lv-k{" lv-fav" if i == best else ""}">{pct(s.kalshi)}{bar}</td>')
        rows.append(f'<tr class="{win.strip()}"><td class="lv-team">{logo}<span>{html.escape(s.name)}{rec}</span></td>'
                    f'<td class="lv-score">{html.escape(s.score) if g.state != "pre" else ""}</td>{odds}</tr>')
    if g.state != "post" and (g.draw_dk is not None or g.draw_kalshi is not None):
        rows.append(f'<tr><td class="lv-team"><span class="lv-nologo"></span><span>Draw</span></td><td></td>'
                    f'<td class="lv-dk">{american(g.draw_dk)}</td><td class="lv-k">{pct(g.draw_kalshi)}</td></tr>')
    foot = " · ".join(x for x in (f"Spread {g.spread}" if g.spread else "", g.total) if x)
    if g.state == "in" and any(s.dk for s in g.sides):
        foot = (foot + " · " if foot else "") + "DraftKings line is pre-game"
    return (f'<div class="lv-card{" is-live" if g.state == "in" else ""}"><div class="lv-top">'
            f'<span class="lv-league">{html.escape(g.league)}</span>{status_html(g)}</div>'
            f'<table><thead><tr><th></th><th>{"Score" if g.state != "pre" else ""}</th>'
            + ("" if g.state == "post" else "<th>DraftKings</th><th>Kalshi</th>") + '</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            + (f'<div class="lv-foot">{html.escape(foot)}</div>' if foot else "") + '</div>')


CSS = f"""
<style>
.lv-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: .8rem; margin: .4rem 0 1.2rem; }}
.lv-card {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 10px; padding: .7rem .85rem .6rem; }}
.lv-card.is-live {{ border-color: #f0b3b3; box-shadow: 0 0 0 2px rgba(214,40,40,.08); }}
.lv-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: .35rem; gap: .5rem; }}
.lv-league {{ font-size: .7rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: #4a5a6c; }}
.lv-live {{ color: #c62828; font-weight: 700; font-size: .8rem; display: inline-flex; align-items: center; gap: .35rem; }}
.lv-live i {{ width: 8px; height: 8px; border-radius: 50%; background: #e53935; animation: lvpulse 1.2s infinite; }}
@keyframes lvpulse {{ 0%, 100% {{ opacity: 1; transform: scale(1); }} 50% {{ opacity: .35; transform: scale(.7); }} }}
.lv-final {{ color: #4a5a6c; font-weight: 600; font-size: .8rem; }}
.lv-pre {{ color: #1d3a5c; font-weight: 600; font-size: .8rem; }}
.lv-card table {{ width: 100%; border-collapse: collapse; font-size: .9rem; border: none !important; margin: 0; }}
.lv-card tr, .lv-card th, .lv-card td {{ border: none !important; background: none !important; }}
.lv-card th {{ font-size: .66rem; font-weight: 600; color: #8592a3; text-transform: uppercase; letter-spacing: .06em;
  text-align: right; padding: 0 0 .2rem .7rem !important; }}
.lv-card td {{ padding: .28rem 0 .28rem .7rem !important; border-top: 1px solid #f0f2f5 !important; text-align: right; white-space: nowrap; }}
.lv-card td.lv-team {{ padding-left: 0 !important; }}
.lv-card td.lv-team {{ text-align: left; display: flex; align-items: center; gap: .45rem; white-space: normal; }}
.lv-logo, .lv-nologo {{ width: 22px; height: 22px; flex: 0 0 22px; background: center / contain no-repeat; }}
.lv-team small {{ display: block; color: #8592a3; font-size: .7rem; }}
.lv-score {{ font-family: "Barlow Condensed", sans-serif; font-size: 1.25rem; font-weight: 700; width: 3.6rem; padding-right: .5rem !important; }}
tr.lv-win td.lv-team span, tr.lv-win .lv-score {{ font-weight: 700; color: #0c1a2b; }}
.lv-dk {{ width: 4.6rem; font-variant-numeric: tabular-nums; color: #1c2b3a; }}
.lv-k {{ width: 5.4rem; font-variant-numeric: tabular-nums; font-weight: 600; color: #1c2b3a; }}
.lv-k.lv-fav {{ color: #0c1a2b; }}
.lv-bar {{ display: block; height: 4px; background: #eceff3; border-radius: 2px; margin-top: 3px; overflow: hidden; }}
.lv-bar b {{ display: block; height: 100%; }}
.lv-foot {{ font-size: .74rem; color: #6b7889; margin-top: .3rem; }}
.lv-count {{ font-family: "Barlow Condensed", sans-serif; font-size: 1.35rem; font-weight: 700; text-transform: uppercase;
  margin: .6rem 0 .1rem; color: #14202e; }}
</style>
"""

banner("live", "Live Odds",
       "Scores and odds for the top leagues around the world, in one place: DraftKings lines next to Kalshi's live "
       "win chances, updating every 30 seconds. Search any game, then chart how its odds have moved.",
       chips=["NFL · NBA · NHL · MLB · college", "Europe's top soccer + more", "Tennis · UFC"])

with st.container(key="settings"):
    query = st.text_input("Search games", placeholder="Team, player or league, e.g. Lakers, Arsenal, Sabalenka, UFC",
                          key="lv_q")
    f1, f2 = st.columns([2, 3], gap="large")
    status = f1.pills("Show", ["All", "Live now", "Upcoming", "Final"], default="All", required=True, key="lv_status")
    league_names = [l[1] for l in live.LEAGUES]
    leagues = f2.multiselect("Leagues", league_names, default=league_names, key="lv_leagues")
    auto = st.toggle("Auto-refresh every 30 seconds", value=True, key="lv_auto")

st.markdown(CSS, unsafe_allow_html=True)


@st.fragment(run_every=30 if auto else None)
def live_board():
    with st.spinner("Loading scores and odds..."):
        games, fetched = board()
    shown = [g for g in games if g.league in set(leagues) and (not query or g.matches(query))]
    want = {"Live now": "in", "Upcoming": "pre", "Final": "post"}.get(status)
    if want:
        shown = [g for g in shown if g.state == want]
    n_live = sum(g.state == "in" for g in games)
    st.caption(f"Updated {fetched.astimezone(ET):%I:%M:%S %p} ET · {len(games)} games across {len(live.LEAGUES)} leagues · "
               f"{n_live} live now · DraftKings via ESPN, live chances from Kalshi")
    if not shown:
        st.info("No games match. Try another search, more leagues, or **All**.")
        return
    for label, state in (("Live now", "in"), ("Upcoming", "pre"), ("Final", "post")):
        part = [g for g in shown if g.state == state]
        if part:
            st.markdown(f'<div class="lv-count">{label} · {len(part)}</div>'
                        f'<div class="lv-grid">{"".join(card(g) for g in part[:120])}</div>', unsafe_allow_html=True)
            if len(part) > 120:
                st.caption(f"Showing 120 of {len(part)}. Search or pick leagues to narrow it down.")
    st.session_state["lv_games"] = shown


live_board()

# --------------------------------------------------------------- chart
st.subheader("Odds chart")
games = [g for g in st.session_state.get("lv_games", []) if g.kalshi_updated and g.kalshi_series]
if not games:
    st.caption("Kalshi charts appear for games that Kalshi lists (most top-league games before and during play).")
else:
    labels = {g.id: f"{g.league}: {g.label} · " + ("LIVE" if g.state == "in" else f"{g.start.astimezone(ET):%a %I:%M %p} ET")
              for g in games}
    gid = st.selectbox("Game", list(labels), format_func=labels.get, key="lv_chart_game",
                       help="Search above to find a game faster.")
    g = next(x for x in games if x.id == gid)
    c1, c2 = st.columns([3, 1])
    span = c2.selectbox("Time span", ["Last 6 hours", "Last 24 hours", "Last 3 days"],
                        index=0 if g.state == "in" else 2, key="lv_span")
    hours, interval = {"Last 6 hours": (6, 1), "Last 24 hours": (24, 1), "Last 3 days": (72, 60)}[span]
    rows = []
    parts = [(s.name, s.kalshi_ticker, SIDE_COLORS[i % 2]) for i, s in enumerate(g.sides) if s.kalshi_ticker]
    if g.draw_ticker:
        parts.append(("Draw", g.draw_ticker, DRAW_COLOR))
    for name, ticker, _ in parts:
        for t, v in history(g.kalshi_series, ticker, hours, interval):
            rows.append({"Time": t.astimezone(ET).replace(tzinfo=None), "Win chance %": round(v * 100, 1), "Side": name})
    if not rows:
        c1.caption("Kalshi hasn't recorded trades for this game in that time span yet.")
    else:
        df = pd.DataFrame(rows)
        names = [p[0] for p in parts]
        colors = [p[2] for p in parts]
        lines = alt.Chart(df).mark_line(strokeWidth=2, interpolate="step-after").encode(
            x=alt.X("Time:T", title="Eastern time"),
            y=alt.Y("Win chance %:Q", scale=alt.Scale(domain=[0, 100]), title="Kalshi win chance (%)"),
            color=alt.Color("Side:N", scale=alt.Scale(domain=names, range=colors), legend=alt.Legend(orient="top", title=None)))
        hover = alt.selection_point(fields=["Time"], nearest=True, on="pointerover", empty=False)
        pts = alt.Chart(df).mark_circle(size=60).encode(
            x="Time:T", y="Win chance %:Q", color=alt.Color("Side:N", scale=alt.Scale(domain=names, range=colors), legend=None),
            opacity=alt.condition(hover, alt.value(1), alt.value(0)),
            tooltip=[alt.Tooltip("Time:T", format="%a %I:%M %p"), "Side:N", "Win chance %:Q"]).add_params(hover)
        layers = [lines, pts]
        fair = g.dk_fair()
        if fair:
            ref = pd.DataFrame({"Side": names[:len(fair)], "DraftKings %": [round(f * 100, 1) for f in fair[:len(names)]]})
            layers.append(alt.Chart(ref).mark_rule(strokeDash=[5, 4], strokeWidth=1.5).encode(
                y="DraftKings %:Q", color=alt.Color("Side:N", scale=alt.Scale(domain=names, range=colors), legend=None),
                tooltip=["Side:N", alt.Tooltip("DraftKings %:Q", title="DraftKings (no-vig) %")]))
        st.altair_chart(alt.layer(*layers).properties(height=320), width="stretch")
        st.caption("Solid lines: Kalshi's win chance over time (mid of buy and sell prices). Dashed lines: DraftKings' "
                   "line converted to a win chance, with the bookmaker's cut removed.")

st.divider()
st.caption("Scores and DraftKings odds via ESPN; live prices and charts from Kalshi's public market data. For information "
           "only, not betting advice. Must be 21+; if gambling stops being fun, call 1-800-GAMBLER. Not affiliated with "
           "ESPN, DraftKings or Kalshi.")
