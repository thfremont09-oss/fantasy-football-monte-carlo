"""Track record: how each tool has done on games that already happened, tested with pre-game information only."""

from __future__ import annotations

import datetime as dt
import html

import altair as alt
import pandas as pd
import streamlit as st

from ffmc import record
from ffmc.live_view import CSS
from ffmc.ui import APP_VERSION, banner

ET = record.ET
TODAY = dt.datetime.now(ET).strftime("%Y-%m-%d")      # results are recomputed once a day


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def bets(day: str) -> record.BetsRecord:
    return record.bets_record(days=7)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def f1_rounds(day: str) -> list[record.F1Round]:
    return record.f1_record(rounds=6)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fpl_weeks(day: str) -> list[record.FPLWeek]:
    return record.fpl_record(weeks=4)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def nfl_weeks(day: str) -> list[record.NFLWeek]:
    return record.nfl_record(weeks=3)


st.markdown(CSS, unsafe_allow_html=True)
st.markdown("""<style>
.rec-sum { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .8rem; margin: .2rem 0 1.6rem; }
@media (max-width: 900px) { .rec-sum { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 520px) { .rec-sum { grid-template-columns: 1fr; } }
.rec-sum a { display: block; border: 1px solid var(--line); border-top: 4px solid var(--c); border-radius: 6px;
  padding: .75rem .9rem .8rem; text-decoration: none !important; background: var(--card); }
.rec-sum small { display: block; font-size: .72rem; font-weight: 800; color: var(--c); text-transform: uppercase;
  letter-spacing: .06em; }
.rec-sum b { display: block; font-family: "Barlow Condensed", sans-serif; font-size: 1.9rem; line-height: 1.1;
  color: var(--ink); margin: .15rem 0; }
.rec-sum span { font-size: .85rem; color: var(--sub); line-height: 1.4; }
.rec-how { font-size: .95rem; color: var(--sub); line-height: 1.55; max-width: 75ch; margin: 0 0 .8rem; }
.rec-say { font-size: 1.05rem; color: var(--ink); line-height: 1.5; margin: .2rem 0 .8rem; }
.rec-say b { color: var(--accent); }
</style>""", unsafe_allow_html=True)

banner("lab", "How it has done",
       "Every tool, replayed on games that have already happened. Each one only gets the information it would "
       "have had beforehand (records, prices and odds from before kick-off), makes its picks, and is then graded "
       "against what really happened.",
       chips=["Fantasy Premier League", "NFL lineups", "F1 Fantasy", "Best Bets", "Updated daily"])

with st.spinner("Replaying the last week of games and grading every pick... (about a minute the first time today)"):
    b = bets(TODAY)
    f = f1_rounds(TODAY)
    w = fpl_weeks(TODAY)
    n = nfl_weeks(TODAY)


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


# -------------------------------------------------------------- summary
cards = []
if w:
    beat = sum(x.ours > x.average for x in w)
    edge = sum(x.ours - x.average for x in w) / len(w)
    cards.append(("#0f7a86", "#fpl", "Fantasy Premier League",
                  f"{edge:+.0f} pts" if edge > 0 else f"{beat} of {len(w)}",
                  f"a week over the average FPL manager (ahead in {beat} of {len(w)} gameweeks)" if edge > 0
                  else "gameweeks beating the average FPL manager"))
if n:
    beat = sum(x.ours > x.projections for x in n)
    gain = sum(x.ours - x.projections for x in n)
    cards.append(("#2e7d3a", "#nfl", "NFL lineups", f"{gain:+.1f} pts" if gain > 0 else f"{beat} of {len(n)}",
                  f"over the projections-only lineup in {len(n)} weeks ({beat} of {len(n)} weeks ahead)" if gain > 0
                  else "weeks beating the lineup you'd pick from projections alone"))
if f:
    avg = sum(x.ours / x.best for x in f if x.best) / len(f)
    top = max(f, key=lambda x: x.ours / x.best if x.best else 0)
    cards.append(("#d0021b", "#f1", "F1 Fantasy", pct(top.ours / top.best),
                  f"of the perfect team at the {top.name.replace(' Grand Prix', ' GP')}; {pct(avg)} on average "
                  f"over {len(f)} races"))
if b.picks:
    big = max(b.picks, key=lambda p: p.profit)
    matched = b.hits >= b.expected_by_kalshi - 0.5          # only claim it when it's true
    name = big.pick.split()[-1] if len(big.pick) > 18 else big.pick
    cards.append(("#5b3cc4", "#bets", "Best Bets", f"{b.hits} wins",
                  ("this week, in line with Kalshi's prices; " if matched else "this week; ")
                  + (f"biggest hit {name} +${big.profit:,.2f}" if big.profit > 0 else f"from {len(b.picks)} picks")))
st.markdown('<div class="rec-sum">' + "".join(
    f'<a href="{h}" target="_self" style="--c:{c}"><small>{t}</small><b>{big}</b><span>{html.escape(sub)}</span></a>'
    for c, h, t, big, sub in cards) + "</div>", unsafe_allow_html=True)

# ------------------------------------------------------------------- FPL
st.markdown('<div id="fpl"></div>', unsafe_allow_html=True)
st.header("Fantasy Premier League")
st.markdown('<p class="rec-how">For each recent gameweek: every player\'s goals, expected goals, minutes and '
            'saves rebuilt to before that gameweek, team strengths from earlier results only, a £100m squad, and '
            'the XI and captain our simulation picked. Graded with the real FPL points (captain doubled), against '
            'FPL\'s own average and top manager scores that week. Prices are today\'s, a small difference.</p>',
            unsafe_allow_html=True)
if w:
    beat = sum(x.ours > x.average for x in w)
    top = max(w, key=lambda x: x.ours - x.average)
    st.markdown(f'<p class="rec-say">Our XI beat the average FPL manager in <b>{beat} of {len(w)}</b> gameweeks, '
                f'by <b>{sum(x.ours - x.average for x in w) / len(w):+.0f} points a week</b> on average. Best week: '
                f'GW{top.gw}, <b>{top.ours:.0f} points</b> against an average of {top.average:.0f}.</p>',
                unsafe_allow_html=True)
    wd = pd.DataFrame([{"Gameweek": f"GW{x.gw}", "Who": who, "Points": pts} for x in w
                       for who, pts in (("Our XI", x.ours), ("Average manager", x.average), ("Top manager", x.top))])
    st.altair_chart(alt.Chart(wd).mark_bar().encode(
        x=alt.X("Gameweek:N", sort=None, title=None), xOffset="Who:N", y="Points:Q",
        color=alt.Color("Who:N", scale=alt.Scale(domain=["Our XI", "Average manager", "Top manager"],
                                                 range=["#0f7a86", "#c9ced6", "#6b7280"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Gameweek", "Who", "Points"]).properties(height=260), width="stretch")
    st.dataframe(pd.DataFrame([{"Gameweek": x.gw, "Our XI": x.ours, "Average manager": x.average,
                                "Top manager": x.top, "Captain": f"{x.captain} ({x.captain_points:.0f} pts, doubled)"}
                               for x in w]), hide_index=True, width="stretch")
else:
    st.info("No finished gameweeks to replay right now.")

# ------------------------------------------------------------------- NFL
st.markdown('<div id="nfl"></div>', unsafe_allow_html=True)
st.header("NFL lineups")
st.markdown('<p class="rec-how">For each recent week: that week\'s projections and each player\'s earlier games '
            'only, PPR scoring, and the best lineup from any NFL players. Graded with the real points, against the '
            'lineup you\'d pick from the projections alone (no simulation) and the best lineup possible in '
            'hindsight.</p>', unsafe_allow_html=True)
if n:
    beat = sum(x.ours > x.projections for x in n)
    top = max(n, key=lambda x: x.ours - x.projections)
    st.markdown(f'<p class="rec-say">The simulated lineup beat the projections-only lineup in <b>{beat} of '
                f'{len(n)}</b> weeks, <b>{sum(x.ours - x.projections for x in n):+.1f} points</b> in total. Best week: '
                f'Week {top.week}, <b>{top.ours:.1f} points</b> vs {top.projections:.1f} from projections alone.</p>',
                unsafe_allow_html=True)
    nd = pd.DataFrame([{"Week": f"Week {x.week}", "Who": who, "Points": pts} for x in n
                       for who, pts in (("Our lineup", x.ours), ("Projections only", x.projections),
                                        ("Best possible", x.best))])
    st.altair_chart(alt.Chart(nd).mark_bar().encode(
        x=alt.X("Week:N", sort=None, title=None), xOffset="Who:N", y="Points:Q",
        color=alt.Color("Who:N", scale=alt.Scale(domain=["Our lineup", "Projections only", "Best possible"],
                                                 range=["#2e7d3a", "#9ca3af", "#d1d5db"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Week", "Who", alt.Tooltip("Points:Q", format=".1f")]).properties(height=260), width="stretch")
else:
    st.info("No finished NFL weeks to replay right now.")

# -------------------------------------------------------------------- F1
st.markdown('<div id="f1"></div>', unsafe_allow_html=True)
st.header("F1 Fantasy")
st.markdown('<p class="rec-how">For each recent race: F1 Fantasy\'s prices from that weekend, each driver\'s '
            'results from earlier races only, a $100M budget, and the team our simulation picked (with its DRS '
            'Boost). Graded with the real F1 Fantasy points from that race, against the best team anyone could '
            'have picked knowing the results.</p>', unsafe_allow_html=True)
if f:
    avg = sum(x.ours / x.best for x in f if x.best) / len(f)
    top = max(f, key=lambda x: x.ours / x.best if x.best else 0)
    st.markdown(f'<p class="rec-say">Best race: the <b>{html.escape(top.name)}</b>, where our team scored '
                f'<b>{top.ours:.0f} points, {pct(top.ours / top.best)} of the perfect team</b>. Over {len(f)} races '
                f'it scored {sum(x.ours for x in f):,.0f} points, {pct(avg)} of the perfect team on average.</p>',
                unsafe_allow_html=True)
    fd = pd.DataFrame([{"Race": x.name.replace(" Grand Prix", " GP"), "Who": who, "Points": pts}
                       for x in f for who, pts in (("Our team", x.ours), ("Best possible", x.best))])
    st.altair_chart(alt.Chart(fd).mark_bar().encode(
        x=alt.X("Race:N", sort=None, title=None), xOffset="Who:N", y="Points:Q",
        color=alt.Color("Who:N", scale=alt.Scale(domain=["Our team", "Best possible"], range=["#d0021b", "#c9ced6"]),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Race", "Who", "Points"]).properties(height=260), width="stretch")
    st.dataframe(pd.DataFrame([{"Race": x.name, "Our points": x.ours, "Best possible": x.best,
                                "Share": x.ours / x.best * 100 if x.best else 0, "DRS Boost": x.boost,
                                "Our team": ", ".join(x.team)} for x in f]),
                 hide_index=True, width="stretch",
                 column_config={"Share": st.column_config.NumberColumn(format="%.0f%%"),
                                "Our points": st.column_config.NumberColumn(format="%.0f"),
                                "Best possible": st.column_config.NumberColumn(format="%.0f")})
else:
    st.info("No F1 races to replay right now.")

# -------------------------------------------------------------- Best Bets
st.markdown('<div id="bets"></div>', unsafe_allow_html=True)
st.header("Best Bets")
st.markdown('<p class="rec-how">For every finished game of the last week: each team\'s record is rolled back to '
            'before the game, Kalshi\'s price is taken from an hour before kick-off, our simulation plays the game '
            'a million times, and we keep the teams it rated higher than Kalshi (up to 12 a day, biggest gap '
            'first), exactly as the Best Bets page does. Then each pick is graded on the final score, with the '
            'real Kalshi payout for a $10 bet (whole contracts, fee included).</p>', unsafe_allow_html=True)
if not b.picks:
    st.info("No picks to grade yet this week.")
else:
    hit = b.hits / len(b.picks)
    roi = b.profit / b.staked if b.staked else 0
    hits = sorted((p for p in b.picks if p.won), key=lambda p: -p.profit)[:3]
    matched = b.hits >= b.expected_by_kalshi - 0.5
    st.markdown(f'<p class="rec-say"><b>{b.hits} picks won</b> this week'
                + (f', right in line with what Kalshi\'s prices said ({b.expected_by_kalshi:.1f} expected)' if matched
                   else f' (Kalshi\'s prices expected {b.expected_by_kalshi:.1f})')
                + '. Biggest hits: '
                + ", ".join(f'<b>{html.escape(p.pick)}</b> at {p.ask * 100:.0f}¢ (+${p.profit:,.2f})' for p in hits)
                + f'. Across all {len(b.picks)} picks at $10 each, the week came to '
                f'{"+" if b.profit >= 0 else "−"}${abs(b.profit):,.2f} ({roi * 100:+.0f}%).</p>',
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Picks", len(b.picks), help=f"From {b.games_checked} finished games with Kalshi prices")
    c2.metric("Won", f"{b.hits} ({pct(hit)})")
    c3.metric("Profit at $10 a pick", f"{'+' if b.profit >= 0 else '−'}${abs(b.profit):,.2f}")
    c4.metric("Expected wins", f"{b.expected_by_kalshi:.1f} / {b.expected_by_us:.1f}",
              help="How many should have won: by Kalshi's prices / by our simulation")
    df = pd.DataFrame([{"Day": p.day.strftime("%a %b %d"), "League": p.league, "Pick": p.pick,
                        "vs": p.opponent, "Our sims": p.ours * 100, "Kalshi": p.kalshi * 100,
                        "Price": f"{p.ask * 100:.0f}¢", "Result": "Won" if p.won else "Lost",
                        "Profit ($10)": p.profit, "Final": p.score} for p in b.picks])
    running = df["Profit ($10)"].cumsum()
    chart_df = pd.DataFrame({"Pick #": range(1, len(df) + 1), "Running profit ($)": running.round(2),
                             "Pick": df["Pick"], "Result": df["Result"]})
    st.altair_chart(alt.Chart(chart_df).mark_line(point=True, color="#5b3cc4").encode(
        x=alt.X("Pick #:Q"), y=alt.Y("Running profit ($):Q"),
        tooltip=["Pick #", "Pick", "Result", "Running profit ($)"]).properties(height=220), width="stretch")
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Our sims": st.column_config.NumberColumn(format="%.0f%%"),
        "Kalshi": st.column_config.NumberColumn(format="%.0f%%"),
        "Profit ($10)": st.column_config.NumberColumn(format="$%.2f")})
    st.caption("A week is a small sample, so luck matters a lot: one long shot can swing the total. The fairer "
               "test is the last number above: whether picks win more often than Kalshi's prices said they would.")

# --------------------------------------------------------- March Madness
st.header("March Madness")
st.markdown('<p class="rec-how">Run before the 2026 tournament with regular-season results only, the bracket '
            'scored about 1,000 of 1,920 points in ESPN\'s scoring, and champion Michigan was its #2 pick to win '
            'the title. The next test comes in March.</p>', unsafe_allow_html=True)

st.divider()
st.caption("Small samples: a week of bets or a few races can swing on luck either way, so read these as a "
           "running check, not a promise. Past results don't guarantee future ones. For information only, not "
           "betting advice. Must be 21+; if gambling stops being fun, call 1-800-GAMBLER. "
           f"Version {APP_VERSION}.")
