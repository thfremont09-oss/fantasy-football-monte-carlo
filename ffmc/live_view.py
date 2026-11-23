"""Shared pieces of the Live Odds and Best Bets pages: data caches, game cards, the game
page and the best-bets cards.

Live Odds: scores plus DraftKings and Kalshi odds for the top leagues.

Click any game for its stats and a live odds chart (Kalshi, ESPN's win-probability
model and DraftKings' line). Everything refreshes every 15 seconds.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from urllib.parse import quote
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from ffmc import bestbets, live, winprob
from ffmc.ui import SPORTS

COLOR = SPORTS["live"]["color"]
ET = ZoneInfo("America/New_York")
SIDE_COLORS = ["#2a78d6", "#eb6834"]
DRAW_COLOR = "#8a8f98"
REFRESH = 15        # seconds


@st.cache_data(ttl=12, max_entries=60, show_spinner=False)
def board() -> tuple[list[live.Game], dt.datetime]:
    return live.load_board(), dt.datetime.now(dt.timezone.utc)


@st.cache_data(ttl=12, max_entries=60, show_spinner=False)
def schedule(league: str, day: dt.date) -> list[live.Game]:
    return live.load_schedule(league, day)


@st.cache_data(ttl=120, max_entries=60, show_spinner=False)
def week(league: str, first: dt.date) -> list[live.Game]:
    return live.load_week(league, first)


@st.cache_data(ttl=120, max_entries=60, show_spinner=False)
def next_games(query: str) -> list[live.Game]:
    return live.next_games(query)


@st.cache_data(ttl=30, max_entries=60, show_spinner=False)
def team_games(query: str) -> tuple[list[live.Game], list[live.Game]]:
    """(latest result, next game) for a searched team; refreshed every 30 seconds so scores stay current."""
    return live.team_games(query)


@st.cache_data(ttl=12, max_entries=60, show_spinner=False)
def history(series: str, ticker: str, hours: float, interval: int):
    return live.kalshi_history(series, ticker, hours, interval)


@st.cache_data(ttl=600, show_spinner=False, max_entries=500)
def own_odds(key: str, state: str, away_score: str, home_score: str, period: int, clock: float, detail: str,
             away_record: str, home_record: str, _g: live.Game) -> winprob.OwnOdds | None:
    """Our Monte Carlo for this game; reruns only when the score, clock or records change."""
    return winprob.own_odds(_g)


CARD_SIMS = 1_000_000   # per game on the board, same as the game page


@st.cache_data(ttl=600, show_spinner=False, max_entries=2000)
def card_odds(key: str, state: str, away_score: str, home_score: str, period: int, clock: float, detail: str,
              away_record: str, home_record: str, _g: live.Game) -> winprob.OwnOdds | None:
    """Our Monte Carlo for a board card; reruns only when the score, clock or records change."""
    return winprob.own_odds(_g, CARD_SIMS)


def ours_for(g: live.Game) -> winprob.OwnOdds | None:
    a, h = g.sides[0], g.sides[1] if len(g.sides) > 1 else g.sides[0]
    return card_odds(g.key, g.state, a.score, h.score, g.period, g.clock, g.detail, a.record, h.record, _g=g)


@st.cache_data(ttl=12, max_entries=60, show_spinner=False)
def details(path: str, event_id: str) -> live.Details:
    return live.game_details(path, event_id)


def american(o: int | None) -> str:
    return "—" if o is None else (f"+{o}" if o > 0 else str(o))


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def to_moneyline(p: float | None) -> int | None:
    """A win chance as an American moneyline: 60% -> -150 (favourite), 40% -> +150 (underdog)."""
    if p is None or not 0.005 < p < 0.995:
        return None
    return -round(100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def ml_meaning(name: str, line: int, stake: float = 10.0) -> str:
    """'+287: bet $10 to win $28.70' / '-360: bet $36 to win $10' in plain words."""
    if line > 0:
        return f"{name} {american(line)}: bet ${stake:,.0f} to win ${stake * line / 100:,.2f}"
    risk = stake * -line / 100
    return f"{name} {american(line)}: bet ${risk:,.2f}".replace(".00", "") + f" to win ${stake:,.0f}"


def money_tip(line: int | None, who: str, source: str = "DraftKings", stake: float = 10.0) -> str:
    """Hover text: what a moneyline means in money, for a $10 bet."""
    if line is None:
        return ""
    if line > 0:
        win = stake * line / 100
        text = (f"{who} {american(line)} ({source}): the underdog. Bet ${stake:,.0f} and if {who} wins you win "
                f"${win:,.2f}, so you get back ${stake + win:,.2f}. If they lose, you lose your ${stake:,.0f}.")
    else:
        risk = stake * -line / 100
        text = (f"{who} {american(line)} ({source}): the favourite. Bet ${risk:,.2f} to win ${stake:,.0f}; "
                f"if {who} wins you get back ${risk + stake:,.2f}. If they lose, you lose your ${risk:,.2f}.")
    if source != "DraftKings":
        text += " (Converted from a win chance; " + ("Kalshi pays $1 per contract." if source == "Kalshi"
                                                     else "this is the fair line our simulations imply.") + ")"
    return text


def spread_tip(spread: str) -> str:
    """'TENN +2.5 (-110)' -> what that bet means, in plain words."""
    m = re.match(r"\s*(.+?)\s+([+-]?\d+(?:\.\d+)?)\s*(?:\(([+-]?\d+)\))?", spread or "")
    if not m:
        return ""
    team, line, odds = m.group(1), float(m.group(2)), m.group(3)
    pts = abs(line)
    if line > 0:
        text = (f"Spread {team} +{pts:g}: bet on {team} and you win if they win the game, or lose by less than "
                f"{pts:g} points.")
    else:
        text = f"Spread {team} -{pts:g}: bet on {team} and you only win if they win by more than {pts:g} points."
    if odds:
        o = int(odds)
        text += (f" At {american(o)}, bet ${10 * -o / 100:,.2f} to win $10." if o < 0
                 else f" At {american(o)}, a $10 bet wins ${10 * o / 100:,.2f}.")
    return text


def total_tip(total: str) -> str:
    """'O/U 149.5 (o -110 / u -110)' -> what over and under mean."""
    m = re.search(r"(\d+(?:\.\d+)?)", total or "")
    if not m:
        return ""
    t = float(m.group(1))
    return (f"Over/under {t:g}: a bet on the combined score. 'Over' wins if both teams together score more than "
            f"{t:g}; 'under' wins if they score less. A line of -110 means bet $11 to win $10.")


def tip_attr(text: str) -> str:
    return f' data-tip="{html.escape(text, quote=True)}"' if text else ""


def ml_cell(p: float | None) -> str:
    """Moneyline on top, the win chance small underneath."""
    line = to_moneyline(p)
    return "—" if line is None else f'{american(line)}<small class="lv-p">{p * 100:.0f}%</small>'


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


def sim_bars(ours: float, kalshi: float) -> str:
    """Two bars: our simulated win chance and Kalshi's, so the gap is easy to see."""
    return (f'<div class="ed-bars"><div><span>Our sims</span><i style="width:{ours * 100:.0f}%"></i>'
            f'<b>{ours * 100:.0f}%</b></div><div class="k"><span>Kalshi</span><i style="width:{kalshi * 100:.0f}%"></i>'
            f'<b>{kalshi * 100:.0f}%</b></div></div>')


def sim_vs_kalshi(g: live.Game, mine: winprob.OwnOdds | None) -> str:
    """One plain sentence: how our simulation tracks with Kalshi for this game (empty if we can't compare)."""
    if not mine or len(g.sides) != 2:
        return ""
    pairs = [(s, p) for s, p in ((g.sides[0], mine.away), (g.sides[1], mine.home)) if s.kalshi is not None]
    if not pairs:
        return ""
    s, p = max(pairs, key=lambda x: x[1] - x[0].kalshi)          # the side we're most positive on
    gap = (p - s.kalshi) * 100
    name = html.escape(s.short or s.name)
    if g.state == "pre" and bestbets.too_far(g, 0 if s is g.sides[0] else 1, p, s.kalshi):
        return (f'<div class="lv-vs"><b>Our model can\'t judge this one:</b> it has {name} at {p * 100:.0f}%, '
                f'the market at {s.kalshi * 100:.0f}%. A gap that big usually means the market knows something our '
                f'model doesn\'t (injuries, a backup starter, a team stepping up a level), so it\'s left off '
                f'Best Bets.</div>')
    if abs(gap) < 3:
        fav, fp = max(pairs, key=lambda x: x[1])
        return (f'<div class="lv-vs"><b>Our sims agree with Kalshi:</b> {html.escape(fav.short or fav.name)} '
                f'{fp * 100:.0f}% in our sims, {fav.kalshi * 100:.0f}% on Kalshi.</div>')
    word = "a bit higher" if gap < 8 else "higher" if gap < 15 else "much higher"
    return (f'<div class="lv-vs"><b>We\'re {word} on {name}:</b> {p * 100:.0f}% in our sims vs '
            f'{s.kalshi * 100:.0f}% on Kalshi.</div>')


def ml_explain(g: live.Game) -> str:
    """What the moneylines mean for this game, for a $10 bet (DraftKings' line, or Kalshi's as a moneyline)."""
    if g.state == "post" or len(g.sides) != 2:
        return ""
    parts = []
    for s in g.sides:
        line = s.dk if s.dk is not None else to_moneyline(s.kalshi)
        if line is not None:
            parts.append(ml_meaning(html.escape(s.short or s.name), line))
    return f'<div class="lv-ml">{" · ".join(parts)}</div>' if parts else ""


def card(g: live.Game, sched: bool = False) -> str:
    rows = []
    best = max(range(len(g.sides)), key=lambda i: g.sides[i].kalshi or 0) if g.kalshi_updated else None
    mine = ours_for(g) if g.state != "post" else None          # our own Monte Carlo odds
    ours = [mine.away, mine.home] if mine else [None, None]
    for i, s in enumerate(g.sides):
        win = " lv-win" if s.winner else ""
        bar = (f'<span class="lv-bar"><b style="width:{(s.kalshi or 0) * 100:.0f}%;background:{SIDE_COLORS[i % 2]}"></b></span>'
               if s.kalshi is not None else "")
        rec = f'<small>{html.escape(s.record)}</small>' if s.record else ""
        who = s.short or s.name
        odds = ("" if g.state == "post" else
                f'<td class="lv-dk has-tip"{tip_attr(money_tip(s.dk, who))}>{american(s.dk)}</td>'
                f'<td class="lv-k has-tip{" lv-fav" if i == best else ""}"'
                f'{tip_attr(money_tip(to_moneyline(s.kalshi), who, "Kalshi"))}>{ml_cell(s.kalshi)}{bar}</td>'
                f'<td class="lv-ours has-tip"{tip_attr(money_tip(to_moneyline(ours[i] if i < 2 else None), who, "our sims"))}>'
                f'{ml_cell(ours[i] if i < 2 else None)}</td>')
        rows.append(f'<tr class="{win.strip()}"><td class="lv-team">{logo_html(s)}<span>{html.escape(s.name)}{rec}</span></td>'
                    f'<td class="lv-score">{html.escape(s.score) if g.state != "pre" else ""}</td>{odds}</tr>')
    if g.state != "post" and (g.draw_dk is not None or g.draw_kalshi is not None):
        rows.append(f'<tr><td class="lv-team"><span class="lv-logo"></span><span>Draw</span></td><td></td>'
                    f'<td class="lv-dk has-tip"{tip_attr(money_tip(g.draw_dk, "A draw"))}>{american(g.draw_dk)}</td>'
                    f'<td class="lv-k has-tip"{tip_attr(money_tip(to_moneyline(g.draw_kalshi), "A draw", "Kalshi"))}>'
                    f'{ml_cell(g.draw_kalshi)}</td>'
                    f'<td class="lv-ours has-tip"{tip_attr(money_tip(to_moneyline(mine.draw if mine else None), "A draw", "our sims"))}>'
                    f'{ml_cell(mine.draw if mine else None)}</td></tr>')
    bits = []
    if g.spread:
        bits.append(f'<span class="has-tip"{tip_attr(spread_tip(g.spread))}>Spread {html.escape(g.spread)}</span>')
    if g.total:
        bits.append(f'<span class="has-tip"{tip_attr(total_tip(g.total))}>{html.escape(g.total)}</span>')
    if g.state == "in" and any(s.dk for s in g.sides):
        bits.append("DraftKings line is pre-game")
    foot = " · ".join(bits)
    # Games beyond the live board carry their date, so the game page knows where to find them.
    day = f"&d={g.start.astimezone(ET).date().isoformat()}" if sched else ""
    return (f'<a class="lv-cardlink" href="?game={quote(g.key)}{day}" target="_self">'
            f'<div class="lv-card{" is-live" if g.state == "in" else ""}"><div class="lv-top">'
            f'{league_html(g)}{status_html(g)}</div>'
            f'<table><thead><tr><th></th><th>{"Score" if g.state != "pre" else ""}</th>'
            + ("" if g.state == "post" else '<th>DraftKings</th><th>Kalshi</th><th class="lv-ours-h">Ours</th>')
            + '</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>' + ml_explain(g) + sim_vs_kalshi(g, mine)
            + (f'<div class="lv-foot">{foot}</div>' if foot else "")
            + '<div class="lv-more">Stats &amp; odds chart →</div></div></a>')


CSS = f"""
<style>
.lv-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: .8rem; margin: .4rem 0 1.2rem; }}
a.lv-cardlink, a.lv-cardlink:hover {{ text-decoration: none !important; color: inherit !important; display: block; }}
.lv-card {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 6px; padding: .7rem .85rem .55rem; cursor: pointer;
  transition: box-shadow .15s, transform .15s, border-color .15s; height: 100%; }}
@media (hover: hover) {{ a.lv-cardlink:hover .lv-card {{ box-shadow: 0 8px 22px rgba(12,26,43,.12); transform: translateY(-2px);
  border-color: {COLOR}; }} }}
.lv-card.is-live {{ box-shadow: inset 3px 0 0 #d93025; }}
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
.lv-score {{ font-family: "Barlow Condensed", sans-serif; font-size: 1.25rem; font-weight: 700; width: 3rem; }}
tr.lv-win td.lv-team span, tr.lv-win .lv-score {{ font-weight: 700; color: #0c1a2b; }}
.lv-dk {{ width: 4.2rem; font-variant-numeric: tabular-nums; }}
.lv-k {{ width: 4.8rem; font-variant-numeric: tabular-nums; font-weight: 600; }}
/* our own Monte Carlo column: tinted so it reads as ours, next to the two apps */
.lv-card td.lv-ours {{ width: 4rem; font-variant-numeric: tabular-nums; font-weight: 700; color: {COLOR} !important; }}
.lv-card th.lv-ours-h {{ color: {COLOR} !important; }}
.lv-bar {{ display: block; height: 4px; background: #eceff3; border-radius: 2px; margin-top: 3px; overflow: hidden; }}
.lv-bar b {{ display: block; height: 100%; }}
.lv-foot {{ font-size: .74rem; color: #6b7889; margin-top: .3rem; }}
.ed-bars {{ display: grid; gap: .3rem; margin: .45rem 0 .1rem; }}
.ed-bars div {{ display: grid; grid-template-columns: 4.2rem 1fr 2.4rem; align-items: center; gap: .5rem;
  font-size: .75rem; color: var(--muted); }}
.ed-bars i {{ display: block; height: 7px; border-radius: 4px; background: var(--accent); min-width: 2px; }}
.ed-bars div.k i {{ background: #8a94a3; }}
.ed-bars b {{ text-align: right; color: var(--ink); font-variant-numeric: tabular-nums; font-weight: 700; }}
.bb-card .ed-bars {{ margin-bottom: .55rem; }}
.ed-lines {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .4rem; margin: 0 0 .5rem; }}
.ed-line {{ border: 1px solid var(--line); border-radius: 6px; padding: .3rem .5rem .35rem; font-weight: 700;
  font-variant-numeric: tabular-nums; color: var(--ink); background: var(--card); }}
.ed-line small {{ display: block; font-size: .66rem; font-weight: 600; color: var(--muted); }}
.ed-lines .ed-line:first-child::after {{ left: 0; right: auto; }}
.ed-extra {{ margin: -.1rem 0 .45rem; }}
.lv-card small.lv-p {{ display: block; font-size: .68rem; font-weight: 500; color: var(--muted); line-height: 1.1; }}
/* hover popups that say what a line means in money */
.has-tip {{ position: relative; cursor: help; }}
.has-tip::after {{ content: attr(data-tip); position: absolute; right: 0; bottom: calc(100% + 8px); width: 250px;
  white-space: normal; text-align: left; background: #111827 !important; color: #f9fafb !important; font: 500 .78rem/1.45
  "IBM Plex Sans", sans-serif; letter-spacing: 0; text-transform: none; padding: .55rem .7rem; border-radius: 6px;
  box-shadow: 0 6px 20px rgba(0,0,0,.25); opacity: 0; visibility: hidden; transform: translateY(4px);
  transition: opacity .12s ease, transform .12s ease; z-index: 60; pointer-events: none; }}
.lv-foot .has-tip::after {{ left: 0; right: auto; }}
.has-tip:not([data-tip])::after, .has-tip[data-tip=""]::after {{ display: none; }}
@media (hover: hover) {{ .has-tip:hover::after {{ opacity: 1; visibility: visible; transform: translateY(0); }}
  .has-tip:hover {{ text-decoration: underline dotted; text-underline-offset: 3px; }} }}
.lv-card {{ overflow: visible !important; }}
.lv-howto {{ font-size: .88rem; line-height: 1.5; color: var(--sub); background: var(--soft); border: 1px solid var(--line);
  border-radius: 6px; padding: .6rem .85rem; margin: .2rem 0 .6rem; }}
.lv-howto b {{ color: var(--ink); }}
.lv-ml {{ font-size: .76rem; color: var(--muted); margin: .4rem 0 0; line-height: 1.45; }}
.lv-vs {{ font-size: .82rem; line-height: 1.4; color: var(--sub); background: var(--soft); border-radius: 4px;
  padding: .4rem .55rem; margin: .45rem 0 0; }}
.lv-vs b {{ color: var(--ink); font-weight: 700; }}
.lv-vs.gd-vs {{ font-size: .98rem; padding: .6rem .8rem; margin: -.4rem 0 .6rem; border-left: 3px solid var(--accent); }}
.lv-more {{ font-size: .74rem; color: {COLOR}; font-weight: 600; margin-top: .35rem; text-align: right; }}
.lv-count {{ font-family: "Archivo", sans-serif; font-size: 1.25rem; font-weight: 800; letter-spacing: -.01em;
  margin: .6rem 0 .1rem; color: #14202e; }}
/* detail view */
.gd-head {{ background: #fff; border: 1px solid #dfe3e8; border-radius: 6px; padding: 1rem 1.2rem; margin-bottom: 1rem; }}
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
.bb-card .bb-pick {{ display: flex; justify-content: space-between; align-items: baseline; gap: .6rem;
  font-size: 1.05rem; margin: .1rem 0 .1rem; }}
.bb-price {{ font-family: "Barlow Condensed", sans-serif; font-size: 1.5rem; font-weight: 700; }}
.bb-game {{ font-size: .8rem; color: #6b7889; margin-bottom: .45rem; }}
.bb-pay {{ display: grid; grid-template-columns: auto 1fr auto; gap: .6rem; background: #f3f8f4;
  border-radius: 8px; padding: .5rem .7rem; margin: .1rem 0 .4rem; }}
.bb-pay small {{ display: block; font-size: .68rem; color: #6b7889; text-transform: uppercase; letter-spacing: .05em; }}
.bb-pay b {{ font-family: "Barlow Condensed", sans-serif; font-size: 1.45rem; line-height: 1.1; }}
.bb-how {{ font-size: .78rem; color: #4a5a6c; margin-bottom: .45rem; line-height: 1.4; }}
.bb-stats {{ display: grid; grid-template-columns: 1fr 1fr; gap: .2rem .8rem; font-size: .84rem; }}
.bb-pos {{ color: #1e8e3e; }} .bb-neg {{ color: #d93025; }}
.bb-tag {{ display: inline-block; padding: .08rem .45rem; border-radius: 4px; font-weight: 700; font-size: .7rem;
  margin-right: .35rem; color: #fff; }}
.bb-value {{ background: #1e8e3e; }} .bb-fair {{ background: #7b8794; }} .bb-over {{ background: #b26a00; }}
.ffmc-wl-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; margin: 0 0 .6rem; }}
.ffmc-wl-row b {{ min-width: 3rem; }}
.wl {{ display: inline-block; padding: .18rem .5rem; border-radius: 5px; font-size: .82rem; font-weight: 600;
  font-variant-numeric: tabular-nums; color: #fff; }}
.wl-w {{ background: #1e8e3e; }} .wl-l {{ background: #d93025; }} .wl-d {{ background: #7b8794; }}
.gd-odds.gd-three {{ grid-template-columns: 1fr 1fr 1fr; }}
.gd-ours {{ border-left: 3px solid {COLOR}; }}
.gd-gap {{ font-weight: 500; color: #6b7889; font-size: .75rem; margin-left: .3rem; }}
@media (max-width: 900px) {{ .gd-odds.gd-three {{ grid-template-columns: 1fr 1fr; }} }}
@media (max-width: 640px) {{ .gd-odds, .gd-odds.gd-three {{ grid-template-columns: 1fr; }} .gd-score {{ font-size: 2.3rem; }} }}
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
    def row(label: str, value: str, tip: str = "") -> str:
        cls = ' class="has-tip"' if tip else ""
        return (f'<div class="gd-row"><span>{html.escape(label)}</span><b{cls}{tip_attr(tip)}>{html.escape(value)}</b>'
                f'</div>')

    where = " · ".join(html.escape(x) for x in (d.venue, d.broadcast) if x)
    dk = [row(away.name, american(away.dk), money_tip(away.dk, away.name)),
          row(home.name, american(home.dk), money_tip(home.dk, home.name))]
    if g.draw_dk is not None:
        dk.append(row("Draw", american(g.draw_dk), money_tip(g.draw_dk, "A draw")))
    if g.spread:
        dk.append(row("Spread", g.spread))
    if g.total:
        dk.append(row("Total", g.total))
    ks = [row(away.name, pct(away.kalshi), money_tip(to_moneyline(away.kalshi), away.name, "Kalshi")),
          row(home.name, pct(home.kalshi), money_tip(to_moneyline(home.kalshi), home.name, "Kalshi"))]
    if g.draw_kalshi is not None:
        ks.append(row("Draw", pct(g.draw_kalshi)))
    if d.predictor:
        ks.append(row("ESPN matchup predictor", f"{pct(d.predictor[0])} / {pct(d.predictor[1])}"))
    # Our own Monte Carlo, as a little comparison with the market.
    mine = own_odds(g.key, g.state, away.score, home.score, g.period, g.clock, g.detail, away.record, home.record, _g=g)
    ours = ""
    if mine:
        sides = [(away, mine.away), (home, mine.home)]
        ours_rows = []
        for s, p in sides:
            gap = (f' <small class="gd-gap">{(p - s.kalshi) * 100:+.0f} vs Kalshi</small>'
                   if s.kalshi is not None else "")
            ours_rows.append(f'<div class="gd-row"><span>{html.escape(s.name)}</span><b>{pct(p)}{gap}</b></div>')
        if mine.draw is not None:
            ours_rows.append(row("Draw", pct(mine.draw)))
        sims = f"{mine.n_sims // 1_000_000}M" if mine.n_sims >= 1_000_000 else f"{mine.n_sims:,}"
        ours = (f'<div class="gd-box gd-ours"><p class="eyebrow">Our Monte Carlo · {sims} sims</p>'
                f'{"".join(ours_rows)}</div>')
    team = lambda s: (f'<div class="gd-team">{logo_html(s)}<b>{html.escape(s.name)}</b>'
                      f'<small>{html.escape(s.record)}</small></div>')
    # One line with no indentation, so Markdown can't mistake any of it for a code block.
    st.markdown(
        f'<div class="gd-head"><div class="lv-top">{league_html(g)}<span class="lv-league">{where}</span>'
        f'{status_html(g)}</div>'
        f'<div class="gd-teams">{team(away)}<div class="gd-score">{score}</div>{team(home)}</div>'
        f'<div class="gd-odds{" gd-three" if ours else ""}"><div class="gd-box"><p class="eyebrow">DraftKings'
        f'{" (pre-game)" if g.state == "in" else ""}</p>{"".join(dk)}</div>'
        f'<div class="gd-box"><p class="eyebrow">Kalshi live win chance</p>{"".join(ks)}</div>{ours}</div></div>',
        unsafe_allow_html=True)
    if mine and sim_vs_kalshi(g, mine):
        st.markdown(sim_vs_kalshi(g, mine).replace('class="lv-vs"', 'class="lv-vs gd-vs"'), unsafe_allow_html=True)
    if mine:
        st.caption(f"Our Monte Carlo plays the rest of this game out {mine.n_sims:,} times using only {mine.basis}. "
                   "It doesn't know injuries, lineups or form the way the market does, so big gaps usually mean "
                   "the market knows something a record can't show.")
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


# --------------------------------------------------------------- best bets
@st.cache_data(ttl=60, max_entries=60, show_spinner=False)
def best(book: str, sort: str, min_win: float) -> tuple[list[bestbets.Bet], int, dt.datetime]:
    games, fetched = board()
    bets, checked = bestbets.best_bets(games, book, sort, min_win=min_win)
    return bets, checked, fetched


def money(x: float) -> str:
    return f"${x:,.2f}"


def bet_card(b: bestbets.Bet, stake: float) -> str:
    g = b.game
    t = b.ticket(stake)
    avg = b.win * t.returned - t.spent           # average result over the simulations
    r = bestbets.rating(b)
    tag = {"value": '<span class="bb-tag bb-value">Value</span>',
           "fair": '<span class="bb-tag bb-fair">Fair price</span>',
           "overpriced": f'<span class="bb-tag bb-over">Overpriced {abs(b.ev) * 100:.0f}%</span>'}[r]
    vs = " vs ".join(html.escape(s.name) for s in g.sides)
    if b.book == "Kalshi":
        if t.contracts == 0:
            how = f"{money(stake)} isn't enough for one contract at {html.escape(b.price)}."
        else:
            how = (f"Buys <b>{t.contracts} contract{'s' if t.contracts != 1 else ''}</b> at {html.escape(b.price)} "
                   f"= {money(t.contracts * b.ask)} + {money(t.fee)} Kalshi fee = <b>{money(t.spent)}</b>. "
                   f"Each pays $1 if it wins.")
    else:
        how = f"At {html.escape(b.price)}, DraftKings pays {money(t.profit)} profit on {money(t.spent)}."
    return (f'<a class="lv-cardlink" href="live?game={quote(g.key)}" target="_self"><div class="lv-card bb-card">'
            f'<div class="lv-top">{league_html(g)}{status_html(g)}</div>'
            f'<div class="bb-pick"><span><b>{html.escape(b.pick)}</b>{" to win" if b.pick != "Draw" else ""}</span>'
            f'<span class="bb-price">{html.escape(b.price)}</span></div>'
            f'<div class="bb-game">{vs}</div>'
            f'<div class="bb-pay"><div><small>You bet</small><b>{money(t.spent)}</b></div>'
            f'<div><small>If it wins, you get back</small><b class="bb-pos">{money(t.returned)}</b></div>'
            f'<div><small>Profit</small><b class="bb-pos">+{money(t.profit)}</b></div></div>'
            f'<div class="bb-how">{how} If it loses, you lose {money(t.spent)}.</div>'
            f'<div class="bb-stats"><span>Win chance <b>{b.win * 100:.0f}%</b></span>'
            f'<span>Break-even <b>{b.implied * 100:.0f}%</b></span>'
            f'<span>Average result <b class="{"bb-pos" if avg >= 0 else "bb-neg"}">'
            f'{"+" if avg >= 0 else "−"}{money(abs(avg))}</b></span>'
            f'<span>Confidence <b>{b.confidence * 100:.0f}%</b></span></div>'
            f'<div class="lv-foot">{tag} Fair chance from {html.escape(b.sources)}</div></div></a>')


def edge_lines(e: bestbets.Edge) -> str:
    """The pick's moneyline on DraftKings, on Kalshi and from our sims, plus the game's spread and total,
    each with a hover popup saying what it means in money."""
    g, s = e.game, e.side
    who = s.short or s.name
    chips = []
    for label, line, src in (("DraftKings", s.dk, "DraftKings"), ("Kalshi", to_moneyline(e.kalshi), "Kalshi"),
                             ("Our sims", to_moneyline(e.ours), "our sims")):
        if line is not None:
            chips.append(f'<span class="ed-line has-tip"{tip_attr(money_tip(line, who, src))}><small>{label}</small>'
                         f'{american(line)}</span>')
    extra = []
    if g.spread:
        extra.append(f'<span class="has-tip"{tip_attr(spread_tip(g.spread))}>Spread {html.escape(g.spread)}</span>')
    if g.total:
        extra.append(f'<span class="has-tip"{tip_attr(total_tip(g.total))}>{html.escape(g.total)}</span>')
    out = f'<div class="ed-lines">{"".join(chips)}</div>' if chips else ""
    if extra:
        out += f'<div class="lv-foot ed-extra">{" · ".join(extra)}</div>'
    return out


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _unit(league: str) -> str:
    return "points" if league in winprob.MARGIN else "runs" if league in winprob.BASEBALL else "goals"


def why_html(e: bestbets.Edge) -> str:
    """Plain reasons our simulation rates this team above Kalshi's price, from the same numbers it uses."""
    from ffmc import ratings
    g, s = e.game, e.side
    i = 0 if s is g.sides[0] else 1
    o = g.sides[1 - i]
    me, them = html.escape(s.short or s.name), html.escape(o.short or o.name)
    unit = _unit(g.league)
    lines = []
    r = ratings.get(g.league) if winprob.USE_RATINGS else None
    a, b = (r.notes or {}).get(s.name) if r else None, (r.notes or {}).get(o.name) if r else None
    if r and a and b:
        sign = lambda x: f"{x:+.1f}"
        soccer = g.sport == "Soccer"

        def rec(w: int, d: int, l_: int) -> str:            # soccer shows draws: wins-draws-losses
            return f"{w}-{d}-{l_}" if soccer else f"{w}-{l_}"
        lines.append(f"<b>Strength:</b> on this season's results {me} rate <b>#{a.rank}</b> of {a.of} in "
                     f"{html.escape(g.league)} ({sign(r.rating[s.name])} {unit} a game vs an average team); "
                     f"{them} rate #{b.rank} ({sign(r.rating[o.name])}).")
        tougher = a.sos_rank < b.sos_rank
        three = "soccer" if soccer else ""
        share = lambda side: (winprob._share(side.record, three) or (0.5, 0))[0]
        line = (f"<b>Schedule:</b> {me} ({html.escape(s.record)}) have played the {_ordinal(a.sos_rank)}-toughest "
                f"schedule; {them} ({html.escape(o.record)}) the {_ordinal(b.sos_rank)}.")
        if tougher and share(o) > share(s):
            line += f" {them}'s better record came against weaker teams, so it counts for less."
        lines.append(line)
        if a.last and b.last:
            avg = lambda xs: sum(xs) / len(xs)
            form = lambda xs: rec(sum(m > 0 for m in xs), sum(m == 0 for m in xs), sum(m < 0 for m in xs))
            lines.append(f"<b>Form:</b> last {len(a.last)} games {me} {form(a.last)} ({sign(avg(a.last))} {unit} a "
                         f"game); {them} {form(b.last)} ({sign(avg(b.last))}).")
        home = i == 1
        m_home = r.margin(g.sides[1].name, g.sides[0].name)
        if m_home is not None:
            mine = m_home if home else -m_home
            where = f"at home (worth about {r.home_edge:g} {unit})" if home else "on the road"
            say = f"win by {mine:.1f}" if mine >= 0 else f"lose by {-mine:.1f}"
            line = f"<b>Our number:</b> {me} are {where}; we expect them to {say} {unit}"
            if g.league in winprob.MARGIN and 0.02 < e.kalshi < 0.98:
                sd = winprob.MARGIN[g.league][0]
                implied = sd * winprob.NormalDist().inv_cdf(e.kalshi)
                isay = f"win by {implied:.1f}" if implied >= 0 else f"lose by {-implied:.1f}"
                line += f", while Kalshi's {e.kalshi * 100:.0f}% says they {isay}"
            lines.append(line + ".")
    else:
        lines.append(f"<b>Records:</b> {me} {html.escape(s.record)} vs {them} {html.escape(o.record)}, plus "
                     f"{'home' if i == 1 else 'road'} advantage. Too few games to rate these teams on who they've "
                     f"played yet, so this pick leans on records alone: treat it with extra caution.")
    lines.append("<b>What we can't see:</b> injuries, rest and lineup news. If the gap comes from one of those, "
                 "the market is probably right.")
    return ('<div class="ed-why"><p>Why our sims are higher</p><ul>' + "".join(f"<li>{x}</li>" for x in lines)
            + "</ul></div>")


def edge_card(e: bestbets.Edge, stake: float) -> str:
    """One pick, said plainly: how our simulations track with Kalshi, and what your stake gets back."""
    g, s = e.game, e.side
    t = e.ticket(stake)
    other = next(x for x in g.sides if x is not s)
    pay = (f'Bet {money(t.spent)} on Kalshi ({t.contracts} contracts at {e.ask * 100:.0f}¢, fee included) and you get '
           f'back <b>{money(t.returned)}</b> if they win, <b class="bb-pos">+{money(t.profit)}</b>.'
           if t.contracts else f"{money(stake)} won't buy a contract at {e.ask * 100:.0f}¢.")
    return (f'<a class="lv-cardlink" href="live?game={quote(g.key)}" target="_self"><div class="lv-card bb-card">'
            f'<div class="lv-top">{league_html(g)}{status_html(g)}</div>'
            + (f'<div class="ed-dog">Underdog · even in our sims they lose {(1 - e.ours) * 100:.0f}% of the time'
               f'</div>' if e.ours < 0.5 else "")
            + f'<p class="ed-say">We like <b>{html.escape(s.name)}</b> more than the market does. Our sims give them '
            f'<span class="ed-big">{e.ours * 100:.0f}%</span>; Kalshi has {e.kalshi * 100:.0f}%.</p>'
            f'{sim_bars(e.ours, e.kalshi)}{why_html(e)}{edge_lines(e)}'
            f'<div class="bb-how">{pay}</div>'
            f'<div class="lv-foot">vs {html.escape(other.name)} · {html.escape(s.record)} vs {html.escape(other.record)}'
            f' · tap for the game page</div></div></a>')


EDGE_CSS = """<style>
.ed-say { font-size: .98rem; line-height: 1.5; margin: .35rem 0 .55rem; color: var(--sub); }
.ed-say b { color: var(--ink); }
.ed-big { font-family: "Barlow Condensed", sans-serif; font-weight: 700; font-size: 1.45rem; color: var(--accent); }
.st-key-bb_stake_row { max-width: 240px; margin-bottom: .4rem; }
.ed-dog { display: inline-block; font-size: .72rem; font-weight: 700; color: #b26a00; background: rgba(178,106,0,.1);
  border-radius: 4px; padding: .12rem .45rem; margin-top: .3rem; }
.ed-note { font-size: .92rem; line-height: 1.55; color: var(--sub); background: var(--soft); border: 1px solid var(--line);
  border-left: 3px solid #b26a00; border-radius: 6px; padding: .6rem .85rem; margin: .1rem 0 .9rem; max-width: 80ch; }
.ed-note b { color: var(--ink); }
.ed-why { margin: .2rem 0 .7rem; padding: .55rem .75rem; background: var(--soft); border: 1px solid var(--line);
  border-radius: 6px; }
.ed-why p { margin: 0 0 .25rem; font-size: .72rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: var(--muted); }
.ed-why ul { margin: 0; padding-left: 1.05rem; }
.ed-why li { font-size: .86rem; line-height: 1.45; color: var(--sub); margin: .18rem 0; }
.ed-why li b { color: var(--ink); }
</style>"""


def render_best_bets() -> None:
    """Teams our simulations like more than Kalshi does, biggest gap first, each said in plain English."""
    st.markdown(EDGE_CSS, unsafe_allow_html=True)
    games, fetched = board()
    with st.container(key="bb_stake_row"):
        stake = st.number_input("Your stake ($)", 1.0, 10_000.0, 10.0, step=5.0, key="bb_stake",
                                help="Each card shows exactly what this buys on Kalshi and what you'd get back.")
    edges = bestbets.model_edges(games, ours_for)
    dogs = sum(e.ours < 0.5 for e in edges)
    st.markdown('<div class="ed-note"><b>Good value isn\'t the same as likely to win.</b> These picks are teams our '
                'sims rate higher than Kalshi\'s price, but many are still underdogs: a team Kalshi has at 30% that '
                'we think is really 40% is a bargain, yet it still loses about 6 times in 10. The value comes from '
                'the bigger payout on the times it wins, so expect plenty of these to lose, even when the gap is big.'
                + (f' Right now <b>{dogs} of {len(edges)}</b> picks are underdogs.' if edges else "") + '</div>',
                unsafe_allow_html=True)
    if not edges:
        upcoming = sum(g.state == "pre" for g in games)
        st.info("Right now our simulations don't rate any team above Kalshi's price. "
                f"({upcoming} upcoming games checked.) New prices come in all day; this page updates as they do.")
    else:
        st.markdown(f'<div class="lv-grid">{"".join(edge_card(e, stake) for e in edges)}</div>',
                    unsafe_allow_html=True)
    st.caption(f"Updated {fetched.astimezone(ET):%I:%M %p} ET. Each game is played 1,000,000 times by our model, "
               "which rates every team from this season's results (who it played and by how much) plus home "
               "advantage, and nothing else; Kalshi's price reflects everything the market knows (injuries, lineups, "
               "form). So a gap can mean value, or that the market knows something results can't show. Teams with "
               "fewer than 8 games played are left out, and so are games where we're more than 25 points away from "
               "both Kalshi and DraftKings (that's our blind spot, not an edge). For information "
               "only, not betting advice. Must be 21+; if gambling stops being fun, call 1-800-GAMBLER.")
