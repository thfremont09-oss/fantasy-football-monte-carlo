"""Home page: a sports front page. Scores, top stories, what our model thinks, and the tools.

How the simulators work (and their code) lives on its own page: views/method.py.
"""

from __future__ import annotations

import html
from urllib.parse import quote

import streamlit as st

from ffmc import news, winprob
from ffmc.live_view import ET, board, ours_for
from ffmc.ui import APP_VERSION

esc = html.escape


@st.cache_data(ttl=600, show_spinner=False)
def stories() -> list[news.Story]:
    return news.lead_order(news.top_stories())


# ----------------------------------------------------------------- styles
# Every colour is a variable (see ffmc/ui.py), so text stays readable in light and dark mode.
st.markdown("""
<style>
/* scores strip */
.ticker { display: flex; overflow-x: auto; margin: -1rem 0 1.6rem; border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line); scrollbar-width: thin; }
.ticker a { flex: 0 0 auto; min-width: 158px; padding: .5rem .8rem .55rem; border-right: 1px solid var(--line);
  text-decoration: none !important; color: var(--ink) !important; }
.ticker a:hover { background: var(--soft); }
.tk-top { display: flex; justify-content: space-between; gap: .6rem; font-size: .68rem; font-weight: 700;
  color: var(--muted); margin-bottom: .2rem; white-space: nowrap; }
.tk-top .live { color: var(--accent); }
.tk-row { display: flex; align-items: center; gap: .4rem; font-size: .86rem; line-height: 1.5; color: var(--ink); }
.tk-row .lg { width: 16px; height: 16px; flex: 0 0 16px; background: center / contain no-repeat; }
.tk-row span.n { flex: 1; }
.tk-row b { font-variant-numeric: tabular-nums; }
.tk-row.lose { color: var(--muted); }

/* page grid: stories on the left, headlines and our model on the right */
.front { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 2.2rem; align-items: start; }
@media (max-width: 900px) { .front { grid-template-columns: 1fr; gap: 1.6rem; } }
.hd { font-family: "Archivo", sans-serif; font-weight: 800; font-size: 1.3rem; letter-spacing: -.01em;
  color: var(--ink); margin: 0 0 .8rem; padding-bottom: .45rem; position: relative; border-bottom: 1px solid var(--line); }
.hd::after { content: ""; position: absolute; left: 0; bottom: -1px; width: 44px; height: 3px; background: var(--accent); }

.lead { display: block; text-decoration: none !important; color: var(--ink) !important; margin-bottom: 1.6rem; }
.lead .img { aspect-ratio: 16 / 9; background: var(--soft) center / cover no-repeat; border-radius: 6px; }
.kick { display: inline-block; font-size: .75rem; font-weight: 800; margin: .75rem 0 .3rem; }
.lead h2 { font-family: "Source Serif 4", Georgia, serif !important; font-size: clamp(1.7rem, 3.4vw, 2.4rem) !important;
  line-height: 1.12 !important; letter-spacing: -.01em !important; margin: 0 0 .5rem !important; padding: 0 !important;
  font-weight: 700 !important; color: var(--ink) !important; }
.lead p { font-size: 1.04rem; line-height: 1.6; color: var(--sub); margin: 0 0 .4rem; max-width: 62ch; }
.meta { font-size: .8rem; color: var(--muted); }
.lead:hover h2, .story:hover h3, .heads a:hover .t { text-decoration: underline; text-underline-offset: 3px; }

.more { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.3rem 1.2rem; }
@media (max-width: 1100px) { .more { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 520px) { .more { grid-template-columns: 1fr; } }
.story { display: block; text-decoration: none !important; color: var(--ink) !important; }
.story .img { aspect-ratio: 3 / 2; background: var(--soft) center / cover no-repeat; border-radius: 6px; }
.story .kick { margin-top: .55rem; }
.story h3 { font-family: "Source Serif 4", Georgia, serif !important; font-size: 1.1rem !important; line-height: 1.28 !important;
  letter-spacing: 0 !important; margin: 0 0 .3rem !important; padding: 0 !important; font-weight: 700 !important;
  color: var(--ink) !important; }

.heads { list-style: none; margin: 0 0 1.8rem; padding: 0; }
.heads li { border-bottom: 1px solid var(--line); }
.heads a { display: flex; gap: .75rem; align-items: flex-start; padding: .7rem 0; text-decoration: none !important;
  color: var(--ink) !important; }
.heads .th { width: 72px; height: 54px; flex: 0 0 72px; border-radius: 4px; background: var(--soft) center / cover no-repeat; }
.heads .t { font-weight: 600; font-size: .93rem; line-height: 1.38; color: var(--ink); }
.heads small { display: block; font-size: .72rem; font-weight: 700; margin-bottom: .15rem; }

.model { border: 1px solid var(--line); border-radius: 8px; padding: .95rem 1.05rem 1rem; background: var(--card); }
.model .hd { font-size: 1.12rem; }
.model p.lede { margin: 0 0 .5rem; font-size: .88rem; color: var(--muted); }
.take { padding: .65rem 0; border-top: 1px solid var(--line); font-size: .92rem; line-height: 1.5; color: var(--sub); }
.take b { color: var(--ink); }
.take .big { font-family: "Barlow Condensed", sans-serif; font-weight: 700; font-size: 1.3rem; color: var(--accent); }
.take a, .model .go a { color: var(--accent) !important; font-weight: 700; text-decoration: none !important; }
.model .go { display: flex; gap: 1.1rem; margin-top: .55rem; font-size: .88rem; }

/* tools: a plain list, like a site's section index */
.tools { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .2rem 1.6rem; }
@media (max-width: 900px) { .tools { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 520px) { .tools { grid-template-columns: 1fr; } }
.tools a { display: block; padding: .75rem 0 .8rem; border-bottom: 1px solid var(--line); text-decoration: none !important; }
.tools b { display: flex; align-items: center; gap: .5rem; font-family: "Archivo", sans-serif; font-weight: 800;
  font-size: 1rem; color: var(--ink); }
.tools b i { width: 4px; height: 16px; border-radius: 2px; }
.tools span { display: block; font-size: .86rem; line-height: 1.45; color: var(--muted); margin-top: .2rem; }
.tools a:hover b { color: var(--accent); }
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------- scores
def ticker() -> str:
    try:
        games, _ = board()
    except Exception:          # the front page should never fail because of the scores strip
        return ""
    picks = [g for g in games if g.state == "in"] + [g for g in games if g.state == "pre"][:14] + \
            [g for g in games if g.state == "post"][:10]
    boxes = []
    for g in picks:
        if g.sport == "Tennis" or len(g.sides) != 2:
            continue
        if g.state == "in":
            status = f'<span class="live">● {esc(g.detail)}</span>'
        elif g.state == "post":
            status = "<span>Final</span>"
        else:
            t = g.start.astimezone(ET)
            status = f"<span>{t:%a} {t.strftime('%I:%M %p').lstrip('0')}</span>"
        done = g.state == "post" and any(s.winner for s in g.sides)
        rows = "".join(
            f'<div class="tk-row{" lose" if done and not s.winner else ""}">'
            f'<span class="lg" style="background-image:url(\'{esc(s.logo or "")}\')"></span>'
            f'<span class="n">{esc(s.short or s.name)}</span><b>{esc(s.score) if g.state != "pre" else ""}</b></div>'
            for s in g.sides)
        boxes.append(f'<a href="live?game={quote(g.key)}" target="_self"><div class="tk-top"><span>{esc(g.league)}</span>'
                     f'{status}</div>{rows}</a>')
        if len(boxes) >= 26:
            break
    return f'<div class="ticker">{"".join(boxes)}</div>' if boxes else ""


# --------------------------------------------------------- what our model thinks
def model_box() -> str:
    """Where our Monte Carlo disagrees most with Kalshi on today's games, and its surest pick."""
    try:
        games, _ = board()
    except Exception:
        return ""
    gaps, sure = [], []
    for g in games:
        if g.state != "pre" or len(g.sides) != 2 or g.sport in ("Tennis", "MMA"):
            continue
        # Only teams with a real track record: early-season records say too little to argue with the market.
        if min((winprob._share(x.record) or (0, 0))[1] for x in g.sides) < 8:
            continue
        mine = ours_for(g)
        if not mine:
            continue
        for s, p in ((g.sides[0], mine.away), (g.sides[1], mine.home)):
            if s.kalshi is not None and 0.08 <= s.kalshi <= 0.92:
                gaps.append((p - s.kalshi, s, p, g))
            sure.append((p, s, g))

    def link(g) -> str:
        return f'<a href="live?game={quote(g.key)}" target="_self">{esc(" vs ".join(x.short or x.name for x in g.sides))}</a>'
    takes = []
    if gaps:
        _, s, p, g = max(gaps, key=lambda x: x[0])
        takes.append(f'<div class="take">We like <b>{esc(s.name)}</b> more than the market does. Our sims give them '
                     f'<span class="big">{p * 100:.0f}%</span>; Kalshi has {s.kalshi * 100:.0f}%. {link(g)}</div>')
        others = [x for x in gaps if x[3].key != g.key] or gaps
        _, s, p, g = min(others, key=lambda x: x[0])
        takes.append(f'<div class="take">We\'re cooler on <b>{esc(s.name)}</b>: '
                     f'<span class="big">{p * 100:.0f}%</span> to win, against {s.kalshi * 100:.0f}% on Kalshi. '
                     f'{link(g)}</div>')
    if sure:
        p, s, g = max(sure, key=lambda x: x[0])
        takes.append(f'<div class="take">Safest call on the board: <b>{esc(s.name)}</b>, winning '
                     f'<span class="big">{p * 100:.0f}%</span> of a million simulated games. {link(g)}</div>')
    if not takes:
        takes.append('<div class="take">Nothing to simulate right now. Check back closer to game time.</div>')
    return ('<div class="model"><div class="hd">What our model thinks</div>'
            '<p class="lede">Today\'s games, each played a million times.</p>' + "".join(takes) +
            '<div class="go"><a href="bets" target="_self">Best bets →</a><a href="live" target="_self">All odds →</a>'
            '</div></div>')


# ------------------------------------------------------------ top stories
def front(all_stories: list[news.Story]) -> str:
    def img(s: news.Story, cls: str = "img") -> str:
        return f'<div class="{cls}" style="background-image:url(\'{esc(s.image)}\')"></div>'

    def kick(s: news.Story) -> str:
        return f'<span class="kick" style="color:{s.color}">{esc(s.league)}</span>'

    def meta(s: news.Story) -> str:
        return f'<div class="meta">{esc(s.byline) + " · " if s.byline else ""}{news.ago(s.published)}</div>'

    if not all_stories:
        main = '<div><div class="hd">Top stories</div><p>Stories couldn\'t load right now.</p></div>'
        heads = ""
    else:
        lead, rest = all_stories[0], all_stories[1:]
        grid = [s for s in rest if s.image][:6]
        side = [s for s in rest if s not in grid][:8]
        main = ('<div><div class="hd">Top stories</div>'
                f'<a class="lead" href="{esc(lead.url)}" target="_blank" rel="noopener">{img(lead)}{kick(lead)}'
                f'<h2>{esc(lead.headline)}</h2><p>{esc(lead.dek)}</p>{meta(lead)}</a>'
                '<div class="more">' + "".join(
                    f'<a class="story" href="{esc(s.url)}" target="_blank" rel="noopener">{img(s)}{kick(s)}'
                    f'<h3>{esc(s.headline)}</h3>{meta(s)}</a>' for s in grid) + "</div></div>")
        heads = ('<div class="hd">Latest</div><ul class="heads">' + "".join(
            f'<li><a href="{esc(s.url)}" target="_blank" rel="noopener">'
            + (img(s, "th") if s.image else "")
            + f'<div><small style="color:{s.color}">{esc(s.league)} · {news.ago(s.published)}</small>'
              f'<div class="t">{esc(s.headline)}</div></div></a></li>' for s in side) + "</ul>")
    return f'<div class="front">{main}<div>{heads}{model_box()}</div></div>'


def tools() -> str:
    items = [
        ("#1f6feb", "Live Odds", "live", "Every game today with DraftKings, Kalshi and our own odds."),
        ("#5b3cc4", "Best Bets", "bets", "Prices that look too generous, and exactly what you'd win."),
        ("#0b6e4f", "Player Stats", "players", "Any player's season, career and last game, plus fun facts."),
        ("#2e7d3a", "NFL Lineups", "football", "Who to start in your ESPN league this week."),
        ("#d0021b", "F1 Fantasy", "f1", "Five drivers, two constructors and your DRS Boost."),
        ("#0f7a86", "Fantasy Premier League", "fpl", "Your best XI and captain, on any budget."),
        ("#c75a1c", "March Madness", "march-madness", "Title odds and a full bracket to fill out."),
        ("#5b3cc4", "Parlay Lab", "parlays", "Parlays built for your risk and payout."),
        ("#a3243f", "Niche Sports", "niche", "Table tennis, esports and every obscure market."),
        ("#c0392b", "Track record", "track-record", "How every tool did on games that already happened."),
        ("#6b7280", "How it works", "how-it-works", "The method and the code, in plain English."),
    ]
    return ('<div class="hd">Tools</div><div class="tools">' + "".join(
        f'<a href="{u}" target="_self"><b><i style="background:{c}"></i>{esc(n)}</b><span>{esc(d)}</span></a>'
        for c, n, u, d in items) + "</div>")


st.markdown(ticker(), unsafe_allow_html=True)
st.markdown(front(stories()), unsafe_allow_html=True)
st.write("")
st.markdown(tools(), unsafe_allow_html=True)
st.write("")
st.page_link("views/method.py", label="How the simulations work, with the code", icon=":material/menu_book:")

# ------------------------------------------------------------------- footer
st.divider()
st.caption("Stories and photos from ESPN (tap one to read it there). Scores, odds and model numbers: ESPN, "
           "DraftKings via ESPN, Kalshi and our own simulations. Not affiliated with ESPN, DraftKings, Kalshi, the "
           "NFL, the NCAA, the Premier League or Formula 1. For entertainment; betting is 21+; if gambling stops "
           f"being fun, call 1-800-GAMBLER. Version {APP_VERSION}.")
