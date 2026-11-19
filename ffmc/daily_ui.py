"""Page for ESPN fantasy basketball and hockey (shared): today's lineup and this week's win chance."""

from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from . import espn_daily as ed
from .http import APIError
from .ui import SPORTS, banner

MODES = ["My ESPN league", "Best possible lineup (any player)", "Pick my players"]
OPP_COLOR = "#c75a1c"
N_SIMS = 1_000_000


@st.cache_data(ttl=900, show_spinner="Downloading ESPN players and schedules...")
def default_board(sport_key: str) -> ed.Board:
    return ed.load_default(ed.DailyFantasy(ed.SPORTS[sport_key]))


@st.cache_data(ttl=120, show_spinner="Loading your ESPN league...")
def league_board(sport_key: str, league_id: str, team_id: int | None, espn_s2: str, swid: str):
    return ed.load_league(ed.DailyFantasy(ed.SPORTS[sport_key], espn_s2=espn_s2, swid=swid), league_id, team_id)


@st.cache_data(ttl=600, show_spinner=False, max_entries=50)
def outlook(board: ed.Board) -> ed.WeekOutlook:
    return ed.simulate_week(board, N_SIMS)


def headshot(sport: ed.Sport, p: ed.DPlayer) -> str:
    return f"https://a.espncdn.com/i/headshots/{sport.headshot}/players/full/{p.id}.png"


def day_label(d: ed.Day, today: ed.Day) -> str:
    return "Today" if d.period == today.period else d.date.strftime("%a %b %-d")


def why(p: ed.DPlayer, day: ed.Day, starts: int | None) -> str:
    bits = []
    g = day.games.get(p.team_id)
    bits.append(f"{'vs' if g[1] else '@'} {g[0]}" if g else "no game")
    if p.recent_avg is not None:
        bits.append(f"{p.recent_avg:.1f} last 15 days")
    if p.season_avg is not None:
        bits.append(f"{p.season_avg:.1f} season")
    if p.proj_avg is not None:
        bits.append(f"ESPN projects {p.proj_avg:.1f}")
    if starts is not None:
        bits.append(f"{starts} game{'s' if starts != 1 else ''} in your lineup this week")
    return " · ".join(bits)


def lineup_frame(sport, rows: list[tuple[str, ed.DPlayer | None]], day: ed.Day, starts: dict | None) -> pd.DataFrame:
    data = []
    for slot, p in rows:
        if p is None:
            data.append({"": None, "Slot": slot, "Player": "(nobody playing)", "Pos": "", "Team": "", "Game": "",
                         "Avg / game": None, "Bad game": None, "Great game": None, "Status": "", "Why": ""})
            continue
        lo, hi = ed.game_range(p, sport)
        g = day.games.get(p.team_id)
        data.append({"": headshot(sport, p), "Slot": slot, "Player": p.name, "Pos": p.position, "Team": p.team,
                     "Game": (f"{'vs' if g[1] else '@'} {g[0]}" if g else "No game"),
                     "Avg / game": round(p.avg, 1), "Bad game": round(lo, 1), "Great game": round(hi, 1),
                     "Status": p.status, "Why": why(p, day, starts.get(p.id, 0) if starts is not None else None)})
    return pd.DataFrame(data)


COLCFG = {
    "": st.column_config.ImageColumn("", width="small"),
    "Avg / game": st.column_config.NumberColumn(format="%.1f", help="Expected fantasy points in one game: ESPN's "
                                                "projection blended with the last 15 days and the season"),
    "Bad game": st.column_config.NumberColumn(format="%.1f", help="1 game in 10 is worse than this"),
    "Great game": st.column_config.NumberColumn(format="%.1f", help="1 game in 10 is better than this"),
    "Why": st.column_config.TextColumn(width="large"),
}


def week_chart(out: ed.WeekOutlook, me: str, opp: str | None, color: str) -> alt.Chart:
    series = [(me, out.my_total)] + ([(opp or "Opponent", out.opp_total)] if out.opp_total is not None else [])
    lo = min(float(np.percentile(s, 0.2)) for _, s in series)
    hi = max(float(np.percentile(s, 99.8)) for _, s in series)
    edges = np.linspace(lo, hi, 41)
    rows = []
    for name, s in series:
        counts, _ = np.histogram(s, edges)
        for c, a, b in zip(counts, edges[:-1], edges[1:]):
            rows.append({"Team": name, "Points": round((a + b) / 2, 1), "Range": f"{a:.0f}–{b:.0f}",
                         "Share of weeks %": round(100 * c / len(s), 2)})
    names = [n for n, _ in series]
    c = alt.Color("Team:N", scale=alt.Scale(domain=names, range=[color, OPP_COLOR][:len(names)]),
                  legend=alt.Legend(title=None, orient="top"))
    return alt.Chart(pd.DataFrame(rows)).mark_area(interpolate="monotone", opacity=0.25, line={"strokeWidth": 2}).encode(
        x=alt.X("Points:Q", title="Fantasy points this week"),
        y=alt.Y("Share of weeks %:Q", title="% of simulated weeks", stack=None), color=c,
        tooltip=["Team", "Range", "Share of weeks %"]).properties(height=260)


def render(sport_key: str) -> None:
    sport = ed.SPORTS[sport_key]
    color = SPORTS[sport_key]["color"]
    noun = "basketball" if sport_key == "nba" else "hockey"
    banner(sport_key, f"Fantasy {'Basketball' if sport_key == 'nba' else 'Hockey'} Lineups",
           f"Built for ESPN fantasy {noun}. Pick today's best lineup from whoever has a game, and see your chance "
           f"of winning this week: every remaining day is played out {N_SIMS:,} times for you and your opponent.",
           chips=["Today's lineup", "This week's win chance", "ESPN points & category leagues"])

    with st.container(key="settings"):
        mode = st.pills("Whose lineup?", MODES, default=MODES[0], required=True, key=f"{sport_key}_mode")
        league_id, espn_s2, swid = "", "", ""
        if mode == MODES[0]:
            league_id = st.text_input("ESPN league ID", key=f"{sport_key}_league",
                                      help=f"The number after leagueId= in your league's address, e.g. "
                                           f"fantasy.espn.com/{noun}/league?leagueId=12345678")
            with st.expander("Private league? Add your ESPN login"):
                st.caption("Most ESPN leagues are private. ESPN only shares them with a logged-in browser, so paste "
                           "these two values from yours. They're used only to read your league and aren't saved.")
                k1, k2 = st.columns(2, gap="medium")
                espn_s2 = k1.text_input("espn_s2", type="password", key=f"{sport_key}_s2")
                swid = k2.text_input("SWID", type="password", placeholder="{XXXXXXXX-XXXX-...}", key=f"{sport_key}_swid")
                st.markdown("**How do I find these?** On a computer, log in at fantasy.espn.com in Chrome. Open the "
                            "menu (⋮) → *More tools* → *Developer tools* → *Application* → *Cookies* → "
                            "*https://fantasy.espn.com*, and copy **espn_s2** and **SWID**.")

    try:
        if mode == MODES[0]:
            if not league_id.strip().isdigit():
                st.info(f"Enter your **ESPN league ID** above: the number after **leagueId=** in your league's "
                        f"address on fantasy.espn.com. Private league? Also open **Private league? Add your ESPN "
                        f"login**.")
                st.stop()
            _, teams = league_board(sport_key, league_id.strip(), None, espn_s2, swid)
            if not teams:
                st.warning("That league has no teams yet.")
                st.stop()
            labels = {t.id: t.name + (f"  ({t.owner})" if t.owner else "") for t in teams}
            team_id = st.selectbox("Which team is yours?", list(labels), format_func=labels.get,
                                   key=f"{sport_key}_team")
            board, _ = league_board(sport_key, league_id.strip(), int(team_id), espn_s2, swid)
        else:
            board = default_board(sport_key)
    except APIError as exc:
        st.error(str(exc))
        st.stop()

    if mode == MODES[2]:
        ranked = sorted(board.players, key=lambda p: -p.value)
        names = {p.id: f"{p.name} · {p.position} · {p.team}" for p in ranked}
        c1, c2 = st.columns(2)
        mine = c1.multiselect("Your players", list(names), format_func=names.get, key=f"{sport_key}_mine",
                              placeholder="Start typing a name...")
        theirs = c2.multiselect("Opponent's players (optional)", [p for p in names if p not in mine],
                                format_func=names.get, key=f"{sport_key}_theirs",
                                placeholder="Add them to see your win chance")
        if not mine:
            st.info("Add your players above to get today's lineup and this week's outlook.")
            st.stop()
        board = ed.with_rosters(board, set(mine), set(theirs))

    dream = mode == MODES[1]
    days = board.days
    pick = st.segmented_control("Lineup for", [d.period for d in days], default=days[0].period,
                                format_func=lambda per: day_label(next(d for d in days if d.period == per), days[0]),
                                key=f"{sport_key}_day") or days[0].period
    day = next(d for d in days if d.period == pick)
    pool = board.players if dream else [p for p in board.players if "mine" in p.tags]
    lineup = ed.day_lineup(pool, board.slots, day)
    started = {p.id for p in lineup if p}
    out = None if dream else outlook(board)

    st.caption(f"{sport.name} · {day.date.strftime('%A %B %-d')} · {len(day.games) // 2} games · Scoring: "
               f"{board.scoring} · Data live from ESPN")
    for n in board.notes:
        st.caption(n)

    # ---------------------------------------------------------------- headline
    today_pts = sum(p.value for p in lineup if p)
    cols = st.columns(4 if out and out.win_prob is not None and board.points_league else 2)
    cols[0].metric(f"Expected points ({day_label(day, days[0]).lower()})", f"{today_pts:.1f}")
    cols[1].metric("Players with a game", f"{len(started)} of {len(board.slots)} slots")
    if out and out.win_prob is not None and board.points_league:
        cols[2].metric(f"Win chance vs {board.opp_name}", f"{100 * out.win_prob:.0f}%",
                       f"{(out.my_total - out.opp_total).mean():+.0f} pts expected margin")
        cols[3].metric("Projected week", f"{out.my_total.mean():.0f} – {out.opp_total.mean():.0f}",
                       help="Points already scored this week plus the simulated rest of the week")

    tabs = st.tabs(["Lineup", "This week"] + (["Opponent"] if board.opp_ids else []))
    with tabs[0]:
        st.subheader("Best possible lineup" if dream else f"Start these players {day_label(day, days[0]).lower()}")
        st.dataframe(lineup_frame(sport, list(zip(board.slots, lineup)), day, out.my_starts if out else None),
                     column_config=COLCFG, hide_index=True, width="stretch", row_height=44)
        if not dream:
            bench = sorted((p for p in pool if p.id not in started), key=lambda p: -p.value)
            if bench:
                st.subheader("Bench")
                st.dataframe(lineup_frame(sport, [("BN", p) for p in bench], day, out.my_starts if out else None),
                             column_config=COLCFG, hide_index=True, width="stretch", row_height=44)
            st.caption("Players without a game that day can't score, so they sit. Lineups are filled exactly: "
                       "a player who fits several slots goes wherever they help the total most.")
    with tabs[1]:
        if dream:
            st.info("Pick **My ESPN league** or **Pick my players** to simulate a week against an opponent.")
        else:
            st.subheader("Games in your lineup this week")
            rows = []
            for d in days:
                lu = ed.day_lineup(pool, board.slots, d)
                row = {"Day": day_label(d, days[0]), "Your starters": sum(1 for p in lu if p)}
                if board.opp_ids:
                    their = [p for p in board.players if "opp" in p.tags]
                    row[f"{board.opp_name}'s starters"] = sum(1 for p in ed.day_lineup(their, board.slots, d) if p)
                rows.append(row)
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            if board.points_league:
                st.subheader("Simulated week totals")
                st.altair_chart(week_chart(out, board.my_name, board.opp_name, color), width="stretch")
                st.caption(f"{N_SIMS:,} simulated weeks. Each player's games count only on days they'd be in your "
                           "best lineup; injured players sometimes sit; points already scored this week are "
                           "included.")
    if board.opp_ids:
        with tabs[2]:
            their = [p for p in board.players if "opp" in p.tags]
            st.subheader(f"{board.opp_name}'s best lineup {day_label(day, days[0]).lower()}")
            st.dataframe(lineup_frame(sport, list(zip(board.slots, ed.day_lineup(their, board.slots, day))), day,
                                      out.opp_starts if out else None),
                         column_config=COLCFG, hide_index=True, width="stretch", row_height=44)
    st.divider()
    st.caption("Projections, points and injuries from ESPN. Not affiliated with ESPN, the NBA or the NHL.")
