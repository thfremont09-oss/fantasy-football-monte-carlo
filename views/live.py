"""Live Odds page: scores plus DraftKings and Kalshi odds for the top leagues.

Click any game for its stats and a live odds chart (Kalshi, ESPN's win-probability
model and DraftKings' line). Everything refreshes every 15 seconds.
"""

from __future__ import annotations

import datetime as dt
import html
from urllib.parse import quote
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
REFRESH = 15        # seconds


@st.cache_data(ttl=12, show_spinner=False)
def board() -> tuple[list[live.Game], dt.datetime]:
    return live.load_board(), dt.datetime.now(dt.timezone.utc)


@st.cache_data(ttl=12, show_spinner=False)
def schedule(league: str, day: dt.date) -> list[live.Game]:
    return live.load_schedule(league, day)


@st.cache_data(ttl=120, show_spinner=False)
def week(league: str, first: dt.date) -> list[live.Game]:
    return live.load_week(league, first)


@st.cache_data(ttl=120, show_spinner=False)
def next_games(query: str) -> list[live.Game]:
    return live.next_games(query)


@st.cache_data(ttl=12, show_spinner=False)
def history(series: str, ticker: str, hours: float, interval: int):
    return live.kalshi_history(series, ticker, hours, interval)


@st.cache_data(ttl=12, show_spinner=False)
def details(path: str, event_id: str) -> live.Details:
    return live.game_details(path, event_id)


def american(o: int | None) -> str:
    return "—" if o is None else (f"+{o}" if o > 0 else str(o))


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def status_html(g: live.Game) -> str:
    if g.state == "in":
        return f'<span class="lv-live"><i></i>LIVE · {html.escape(g.detail)}</span>'
    if g.state == "post":
        return f'<span class="lv-final">{html.escape(g.detail or "Final")}</span>'
    t = g.start.astimezone(ET)
    return f'<span class="lv-pre">{t:%a %b} {t.day}, {t:%I:%M %p}'.replace(", 0", ", ") + ' ET</span>'


# One color per sport, so leagues are easy to tell apart at a glance.
SPORT_COLORS = {"Football": "#2e7d3a", "Basketball": "#c75a1c", "Hockey": "#0f6fa8", "Baseball": "#b3261e",
                "Soccer": "#0f7a86", "Tennis": "#7a8a12", "MMA": "#5b3cc4"}
FLAGS = {"Premier League": "England", "EFL Championship": "England", "La Liga": "Spain", "Bundesliga": "Germany",
         "Serie A": "Italy", "Ligue 1": "France", "Champions League": "Europe", "Europa League": "Europe",
         "MLS": "USA & Canada", "Liga MX": "Mexico", "Eredivisie": "Netherlands", "Primeira Liga": "Portugal",
         "Brasileirão": "Brazil", "Argentine Primera": "Argentina", "Saudi Pro League": "Saudi Arabia",
         "Scottish Premiership": "Scotland", "ATP": "Men's tour", "WTA": "Women's tour"}


def league_html(g: live.Game) -> str:
    """Colored league badge plus the sport (and country for soccer)."""
    color = SPORT_COLORS.get(g.sport, "#4a5a6c")
    where = FLAGS.get(g.league)
    sub = f"{g.sport} · {where}" if where else g.sport
    return (f'<span class="lv-league"><b class="lv-badge" style="background:{color}">{html.escape(g.league)}</b>'
            f'<span class="lv-sport">{html.escape(sub)}</span></span>')


def logo_html(s: live.Side, cls: str = "lv-logo") -> str:
    # A background image shows nothing (rather than a broken-image icon) if the logo can't load.
    return (f'<span class="{cls}" style="background-image:url(\'{html.escape(s.logo)}\')"></span>'
            if s.logo else f'<span class="{cls}"></span>')


def result_chip(result: str) -> str:
    """'W 31-20 vs CHI' -> a green chip; losses red, draws/ties grey."""
    kind = {"W": "w", "L": "l"}.get(result[:1].upper(), "d")
    return f'<span class="wl wl-{kind}">{html.escape(result)}</span>'


def card(g: live.Game, sched: bool = False) -> str:
    rows = []
    best = max(range(len(g.sides)), key=lambda i: g.sides[i].kalshi or 0) if g.kalshi_updated else None
    for i, s in enumerate(g.sides):
        win = " lv-win" if s.winner else ""
        bar = (f'<span class="lv-bar"><b style="width:{(s.kalshi or 0) * 100:.0f}%;background:{SIDE_COLORS[i % 2]}"></b></span>'
               if s.kalshi is not None else "")
        rec = f'<small>{html.escape(s.record)}</small>' if s.record else ""
        odds = ("" if g.state == "post" else f'<td class="lv-dk">{american(s.dk)}</td>'
                f'<td class="lv-k{" lv-fav" if i == best else ""}">{pct(s.kalshi)}{bar}</td>')
        rows.append(f'<tr class="{win.strip()}"><td class="lv-team">{logo_html(s)}<span>{html.escape(s.name)}{rec}</span></td>'
                    f'<td class="lv-score">{html.escape(s.score) if g.state != "pre" else ""}</td>{odds}</tr>')
    if g.state != "post" and (g.draw_dk is not None or g.draw_kalshi is not None):
        rows.append(f'<tr><td class="lv-team"><span class="lv-logo"></span><span>Draw</span></td><td></td>'
                    f'<td class="lv-dk">{american(g.draw_dk)}</td><td class="lv-k">{pct(g.draw_kalshi)}</td></tr>')
    foot = " · ".join(x for x in (f"Spread {g.spread}" if g.spread else "", g.total) if x)
    if g.state == "in" and any(s.dk for s in g.sides):
        foot = (foot + " · " if foot else "") + "DraftKings line is pre-game"
    # Games beyond the live board carry their date, so the game page knows where to find them.
    day = f"&d={g.start.astimezone(ET).date().isoformat()}" if sched else ""
    return (f'<a class="lv-cardlink" href="?game={quote(g.key)}{day}" target="_self">'
            f'<div class="lv-card{" is-live" if g.state == "in" else ""}"><div class="lv-top">'
            f'{league_html(g)}{status_html(g)}</div>'
            f'<table><thead><tr><th></th><th>{"Score" if g.state != "pre" else ""}</th>'
            + ("" if g.state == "post" else "<th>DraftKings</th><th>Kalshi</th>") + '</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>'
            + (f'<div class="lv-foot">{html.escape(foot)}</div>' if foot else "")
            + '<div class="lv-more">Stats &amp; odds chart →</div></div></a>')


CSS = f"""
<style>
.lv-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: .8rem; margin: .4rem 0 1.2rem; }}
a.lv-cardlink, a.lv-cardlink:hover {{ text-decoration: none !important; color: inherit !important; display: block; }}
.lv-card {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 10px; padding: .7rem .85rem .55rem; cursor: pointer;
  transition: box-shadow .15s, transform .15s, border-color .15s; height: 100%; }}
@media (hover: hover) {{ a.lv-cardlink:hover .lv-card {{ box-shadow: 0 8px 22px rgba(12,26,43,.12); transform: translateY(-2px);
  border-color: {COLOR}; }} }}
.lv-card.is-live {{ border-color: #f0b3b3; box-shadow: 0 0 0 2px rgba(214,40,40,.08); }}
.lv-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: .35rem; gap: .5rem; }}
.lv-league {{ font-size: .7rem; font-weight: 600; color: #4a5a6c; display: inline-flex; align-items: center; gap: .45rem;
  flex-wrap: wrap; min-width: 0; }}
.lv-badge {{ color: #fff !important; font-size: .74rem; font-weight: 700; letter-spacing: .04em; padding: .16rem .5rem;
  border-radius: 4px; white-space: nowrap; }}
.lv-sport {{ text-transform: uppercase; letter-spacing: .08em; font-size: .66rem; }}
.lv-day {{ font-family: "Barlow Condensed", sans-serif; font-size: 1.15rem; font-weight: 700; text-transform: uppercase;
  margin: .9rem 0 0; border-bottom: 2px solid {COLOR}; display: inline-block; padding-right: .5rem; }}
.lv-live {{ color: #c62828; font-weight: 700; font-size: .8rem; display: inline-flex; align-items: center; gap: .35rem; }}
.lv-live i {{ width: 8px; height: 8px; border-radius: 50%; background: #e53935; animation: lvpulse 1.2s infinite; }}
@keyframes lvpulse {{ 0%, 100% {{ opacity: 1; transform: scale(1); }} 50% {{ opacity: .35; transform: scale(.7); }} }}
.lv-final {{ color: #4a5a6c; font-weight: 600; font-size: .8rem; }}
.lv-pre {{ color: #1d3a5c; font-weight: 600; font-size: .8rem; }}
.lv-card table {{ width: 100%; border-collapse: collapse; font-size: .9rem; border: none !important; margin: 0; }}
.lv-card thead, .lv-card tbody, .lv-card tr, .lv-card th, .lv-card td {{ border: none !important; background: none !important; }}
.lv-card th {{ font-size: .66rem; font-weight: 600; color: #8592a3; text-transform: uppercase; letter-spacing: .06em;
  text-align: right; padding: 0 0 .2rem .7rem !important; }}
.lv-card td {{ padding: .28rem 0 .28rem .7rem !important; border-top: 1px solid #f0f2f5 !important; text-align: right; white-space: nowrap; color: #1c2b3a; }}
.lv-card td.lv-team {{ padding-left: 0 !important; text-align: left; display: flex; align-items: center; gap: .45rem; white-space: normal; }}
.lv-logo {{ width: 22px; height: 22px; flex: 0 0 22px; background: center / contain no-repeat; display: inline-block; }}
.lv-team small {{ display: block; color: #8592a3; font-size: .7rem; }}
.lv-score {{ font-family: "Barlow Condensed", sans-serif; font-size: 1.25rem; font-weight: 700; width: 3.6rem; }}
tr.lv-win td.lv-team span, tr.lv-win .lv-score {{ font-weight: 700; color: #0c1a2b; }}
.lv-dk {{ width: 4.6rem; font-variant-numeric: tabular-nums; }}
.lv-k {{ width: 5.4rem; font-variant-numeric: tabular-nums; font-weight: 600; }}
.lv-bar {{ display: block; height: 4px; background: #eceff3; border-radius: 2px; margin-top: 3px; overflow: hidden; }}
.lv-bar b {{ display: block; height: 100%; }}
.lv-foot {{ font-size: .74rem; color: #6b7889; margin-top: .3rem; }}
.lv-more {{ font-size: .74rem; color: {COLOR}; font-weight: 600; margin-top: .35rem; text-align: right; }}
.lv-count {{ font-family: "Barlow Condensed", sans-serif; font-size: 1.35rem; font-weight: 700; text-transform: uppercase;
  margin: .6rem 0 .1rem; color: #14202e; }}
/* detail view */
.gd-head {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 12px; padding: 1rem 1.2rem; margin-bottom: 1rem; }}
.gd-head .lv-top {{ margin-bottom: .8rem; }}
.gd-teams {{ display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 1rem; }}
.gd-team {{ display: flex; flex-direction: column; align-items: center; text-align: center; gap: .3rem; }}
.gd-team .lv-logo {{ width: 56px; height: 56px; flex-basis: 56px; }}
.gd-team b {{ font-size: 1.05rem; }} .gd-team small {{ color: #8592a3; }}
.gd-score {{ font-family: "Barlow Condensed", sans-serif; font-size: 3rem; font-weight: 700; line-height: 1; white-space: nowrap; }}
.gd-odds {{ display: grid; grid-template-columns: 1fr 1fr; gap: .8rem; margin-top: .9rem; }}
.gd-box {{ background: #f5f6f8; border-radius: 8px; padding: .6rem .8rem; font-size: .9rem; }}
.gd-box p {{ margin: 0; }} .gd-box .eyebrow {{ margin-bottom: .3rem; }}
.gd-row {{ display: flex; justify-content: space-between; gap: .5rem; padding: .12rem 0; }}
.ffmc-wl-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; margin: 0 0 .6rem; }}
.ffmc-wl-row b {{ min-width: 3rem; }}
.wl {{ display: inline-block; padding: .18rem .5rem; border-radius: 5px; font-size: .82rem; font-weight: 600;
  font-variant-numeric: tabular-nums; color: #fff; }}
.wl-w {{ background: #1e8e3e; }} .wl-l {{ background: #d93025; }} .wl-d {{ background: #7b8794; }}
@media (max-width: 640px) {{ .gd-odds {{ grid-template-columns: 1fr; }} .gd-score {{ font-size: 2.3rem; }} }}
</style>
"""


# --------------------------------------------------------------- detail view
def odds_chart(g: live.Game, d: live.Details, span: str) -> None:
    hours, interval = {"Last 6 hours": (6, 1), "Last 24 hours": (24, 1), "Last 3 days": (72, 60)}[span]
    rows = []
    names = [s.name for s in g.sides]
    for i, s in enumerate(g.sides):
        if s.kalshi_ticker and g.kalshi_series:
            for t, v in history(g.kalshi_series, s.kalshi_ticker, hours, interval):
                rows.append({"Time": t, "Win chance %": round(v * 100, 1), "Side": s.name, "Source": "Kalshi"})
    if g.draw_ticker and g.kalshi_series:
        for t, v in history(g.kalshi_series, g.draw_ticker, hours, interval):
            rows.append({"Time": t, "Win chance %": round(v * 100, 1), "Side": "Draw", "Source": "Kalshi"})
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    for t, home in d.win_prob:
        if t >= cutoff and len(g.sides) == 2:
            rows.append({"Time": t, "Win chance %": round(home * 100, 1), "Side": g.sides[1].name, "Source": "ESPN model"})
            rows.append({"Time": t, "Win chance %": round((1 - home) * 100, 1), "Side": g.sides[0].name, "Source": "ESPN model"})
    if not rows:
        st.caption("No odds history yet for this game in that time span (Kalshi may not list it, or it hasn't traded).")
        return
    df = pd.DataFrame(rows)
    df["Time"] = df["Time"].map(lambda t: t.astimezone(ET).replace(tzinfo=None))
    sides = names + (["Draw"] if "Draw" in set(df["Side"]) else [])
    colors = SIDE_COLORS[:len(names)] + ([DRAW_COLOR] if "Draw" in sides else [])
    color = alt.Color("Side:N", scale=alt.Scale(domain=sides, range=colors), legend=alt.Legend(orient="top", title=None))
    dash = alt.StrokeDash("Source:N", scale=alt.Scale(domain=["Kalshi", "ESPN model"], range=[[1, 0], [2, 3]]),
                          legend=alt.Legend(orient="top", title=None))
    lines = alt.Chart(df).mark_line(strokeWidth=2, interpolate="step-after").encode(
        x=alt.X("Time:T", title="Eastern time"), y=alt.Y("Win chance %:Q", scale=alt.Scale(domain=[0, 100]),
                                                         title="Win chance (%)"), color=color, strokeDash=dash)
    hover = alt.selection_point(fields=["Time"], nearest=True, on="pointerover", empty=False)
    pts = alt.Chart(df).mark_circle(size=55).encode(
        x="Time:T", y="Win chance %:Q", color=alt.Color("Side:N", scale=alt.Scale(domain=sides, range=colors), legend=None),
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("Time:T", format="%a %I:%M %p"), "Side:N", "Source:N", "Win chance %:Q"]).add_params(hover)
    layers = [lines, pts]
    fair = g.dk_fair()
    if fair:
        ref = pd.DataFrame({"Side": sides[:len(fair)], "DraftKings %": [round(f * 100, 1) for f in fair[:len(sides)]]})
        layers.append(alt.Chart(ref).mark_rule(strokeDash=[6, 4], strokeWidth=1.2, opacity=.7).encode(
            y="DraftKings %:Q", color=alt.Color("Side:N", scale=alt.Scale(domain=sides, range=colors), legend=None),
            tooltip=["Side:N", alt.Tooltip("DraftKings %:Q", title="DraftKings pre-game (no-vig) %")]))
    st.altair_chart(alt.layer(*layers).properties(height=320), width="stretch")
    st.caption("Solid: Kalshi's live win chance. Dotted: ESPN's win-probability model (where ESPN has one). "
               "Faint dashed: DraftKings' pre-game line with the bookmaker's cut removed.")


def game_view(key: str, day: str | None = None) -> None:
    games, fetched = board()
    g = next((x for x in games if x.key == key), None)
    if g is None and day:      # a game from the schedule or a team search: look it up on its day
        league = live.league_for_path(key.split("~")[0])
        try:
            when = dt.date.fromisoformat(day)
        except ValueError:
            when = None
        if league and when:
            g = next((x for x in schedule(league, when) if x.key == key), None)
    if g is None:
        st.info("That game isn't on the board any more (it may have finished more than 18 hours ago).")
        return
    d = details(g.path, g.event_id)
    away, home = g.sides[0], g.sides[1]
    a_sets, h_sets = (away.score or "").split(), (home.score or "").split()
    if g.state == "pre":
        t = g.start.astimezone(ET)
        score = f'<span style="font-size:1.6rem">{t:%a %b} {t.day}<br>{t:%I:%M %p}</span>'
    elif len(a_sets) > 1 or len(h_sets) > 1:     # tennis: show set by set, e.g. 6-3, 5-3
        score = html.escape(", ".join(f"{a}-{h}" for a, h in zip(a_sets, h_sets)))
    else:
        score = f'{html.escape(away.score or "0")} – {html.escape(home.score or "0")}'
    def row(label: str, value: str) -> str:
        return f'<div class="gd-row"><span>{html.escape(label)}</span><b>{html.escape(value)}</b></div>'

    where = " · ".join(html.escape(x) for x in (d.venue, d.broadcast) if x)
    dk = [row(away.name, american(away.dk)), row(home.name, american(home.dk))]
    if g.draw_dk is not None:
        dk.append(row("Draw", american(g.draw_dk)))
    if g.spread:
        dk.append(row("Spread", g.spread))
    if g.total:
        dk.append(row("Total", g.total))
    ks = [row(away.name, pct(away.kalshi)), row(home.name, pct(home.kalshi))]
    if g.draw_kalshi is not None:
        ks.append(row("Draw", pct(g.draw_kalshi)))
    if d.predictor:
        ks.append(row("ESPN matchup predictor", f"{pct(d.predictor[0])} / {pct(d.predictor[1])}"))
    team = lambda s: (f'<div class="gd-team">{logo_html(s)}<b>{html.escape(s.name)}</b>'
                      f'<small>{html.escape(s.record)}</small></div>')
    # One line with no indentation, so Markdown can't mistake any of it for a code block.
    st.markdown(
        f'<div class="gd-head"><div class="lv-top">{league_html(g)}<span class="lv-league">{where}</span>'
        f'{status_html(g)}</div>'
        f'<div class="gd-teams">{team(away)}<div class="gd-score">{score}</div>{team(home)}</div>'
        f'<div class="gd-odds"><div class="gd-box"><p class="eyebrow">DraftKings'
        f'{" (pre-game)" if g.state == "in" else ""}</p>{"".join(dk)}</div>'
        f'<div class="gd-box"><p class="eyebrow">Kalshi live win chance</p>{"".join(ks)}</div></div></div>',
        unsafe_allow_html=True)
    st.caption(f"Updated {fetched.astimezone(ET):%I:%M:%S %p} ET · refreshes every {REFRESH} seconds")

    st.subheader("Live odds")
    span = st.session_state.get("gd_span") or ("Last 6 hours" if g.state == "in" else "Last 3 days")
    odds_chart(g, d, span)

    left, right = st.columns(2, gap="large")
    with left:
        if d.team_stats:
            st.subheader(d.stats_kind or "Team stats")
            st.dataframe(pd.DataFrame([{"Stat": k, away.short or away.name: a, home.short or home.name: h}
                                       for k, a, h in d.team_stats]), hide_index=True, width="stretch",
                         height=min(460, (len(d.team_stats) + 1) * 35 + 3))
        if d.last_five:
            st.subheader("Last five games")
            for team, results in d.last_five:
                st.markdown(f'<div class="ffmc-wl-row"><b>{html.escape(team)}</b>'
                            + "".join(result_chip(r) for r in results) + "</div>", unsafe_allow_html=True)
    with right:
        if d.leaders:
            st.subheader("Leaders")
            st.dataframe(pd.DataFrame([{"Category": cat, "Team": t, "Player": n, "Value": v}
                                       for cat, entries in d.leaders for t, n, v in entries]),
                         hide_index=True, width="stretch", height=min(460, (sum(len(e) for _, e in d.leaders) + 1) * 35 + 3))
        if d.plays:
            st.subheader("Recent plays")
            for when, text in d.plays[:8]:
                st.markdown(f"<small style='color:#6b7889'>{html.escape(when)}</small> &nbsp; {html.escape(text)}",
                            unsafe_allow_html=True)
    if not (d.team_stats or d.leaders or d.plays):
        st.caption("ESPN doesn't publish detailed stats for this event, so only the score and odds are shown.")


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
    leagues = f2.multiselect("Leagues", league_names, default=league_names, key="lv_leagues")
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
