"""Home page: a sports front page. Scores ticker, top stories, our model's takes, and the tools.

How the simulators work (and their code) lives on its own page: views/method.py.
"""

from __future__ import annotations

import html
from urllib.parse import quote

import streamlit as st

from ffmc import news, winprob
from ffmc.live_view import ET, board, ours_for
from ffmc.ui import APP_VERSION, card_top

FOOTBALL, MADNESS, FPL = "views/football.py", "views/march_madness.py", "views/fpl.py"
F1 = "views/f1.py"
PARLAYS, NICHE, LIVE = "views/parlays.py", "views/niche.py", "views/live.py"
BETS = "views/bets.py"

esc = html.escape


@st.cache_data(ttl=600, show_spinner=False)
def stories() -> list[news.Story]:
    return news.lead_order(news.top_stories())


# ----------------------------------------------------------------- styles
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,600;8..60,700&display=swap');
.serif { font-family: "Source Serif 4", Georgia, serif; }

/* scores ticker */
.ticker { display: flex; gap: 0; overflow-x: auto; margin: -1rem 0 1.4rem; border: 1px solid #dfe3e8;
  border-radius: 6px; background: #fff; scrollbar-width: thin; }
.ticker a { flex: 0 0 auto; min-width: 150px; padding: .45rem .75rem .5rem; border-right: 1px solid #edf0f3;
  text-decoration: none !important; color: inherit !important; }
.ticker a:hover { background: #f6f8fa; }
.tk-top { display: flex; justify-content: space-between; gap: .5rem; font-size: .66rem; font-weight: 700;
  letter-spacing: .06em; text-transform: uppercase; color: #6b7889; margin-bottom: .15rem; }
.tk-top .live { color: #d93025; }
.tk-row { display: flex; justify-content: space-between; gap: .8rem; font-size: .84rem; line-height: 1.35; }
.tk-row b { font-variant-numeric: tabular-nums; }
.tk-row.win span { font-weight: 700; }

/* front page: rail / main / side */
.front { display: grid; grid-template-columns: 200px minmax(0, 1fr) 300px; gap: 1.6rem; align-items: start; }
@media (max-width: 1100px) { .front { grid-template-columns: minmax(0, 1fr) 280px; } .rail { display: none; } }
@media (max-width: 760px) { .front { grid-template-columns: 1fr; } }
.sec { font-family: "Barlow Condensed", sans-serif; font-size: 1.15rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .03em; border-bottom: 3px solid #14202e; padding-bottom: .25rem; margin: 0 0 .7rem; }

.rail .intro { font-size: .88rem; line-height: 1.5; color: #3b4857; margin: 0 0 1rem; }
.rail .intro b { display: block; font-family: "Barlow Condensed", sans-serif; font-size: 1.35rem; line-height: 1.05;
  text-transform: uppercase; color: #14202e; margin-bottom: .35rem; }
.rail a.tool { display: flex; align-items: center; gap: .55rem; padding: .5rem .2rem; border-bottom: 1px solid #edf0f3;
  font-weight: 600; font-size: .92rem; text-decoration: none !important; color: #14202e !important; }
.rail a.tool i { width: 8px; height: 8px; flex: 0 0 8px; border-radius: 2px; }
.rail a.tool:hover { color: #1d5fa8 !important; }

.lead { display: block; text-decoration: none !important; color: inherit !important; margin-bottom: 1.2rem; }
.lead .img { aspect-ratio: 16 / 9; background: #e7ebf0 center / cover no-repeat; border-radius: 4px; }
.tag { display: inline-block; font-size: .68rem; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
  margin: .7rem 0 .25rem; }
.lead h2 { font-family: "Source Serif 4", Georgia, serif !important; font-size: clamp(1.6rem, 3.2vw, 2.25rem) !important;
  line-height: 1.15 !important; text-transform: none !important; letter-spacing: 0 !important; margin: 0 0 .4rem !important;
  padding: 0 !important; font-weight: 700; color: #14202e; }
.lead p { font-size: 1.02rem; line-height: 1.55; color: #3b4857; margin: 0 0 .35rem; }
.meta { font-size: .78rem; color: #6b7889; }
.lead:hover h2 { text-decoration: underline; text-decoration-thickness: 2px; }

.more { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.1rem 1.2rem; }
@media (max-width: 520px) { .more { grid-template-columns: 1fr; } }
.story { display: block; text-decoration: none !important; color: inherit !important; }
.story .img { aspect-ratio: 16 / 9; background: #e7ebf0 center / cover no-repeat; border-radius: 4px; }
.story .tag { margin-top: .5rem; }
.story h3 { font-family: "Source Serif 4", Georgia, serif !important; font-size: 1.12rem !important; line-height: 1.25 !important;
  margin: 0 0 .25rem !important; padding: 0 !important; font-weight: 700; color: #14202e; }
.story:hover h3 { text-decoration: underline; }

.side .heads { list-style: none; margin: 0 0 1.4rem; padding: 0; }
.side .heads li { border-bottom: 1px solid #edf0f3; padding: .55rem 0; }
.side .heads a { display: block; text-decoration: none !important; color: #14202e !important; font-weight: 600;
  font-size: .93rem; line-height: 1.35; }
.side .heads a:hover { color: #1d5fa8 !important; }
.side .heads small { display: block; font-size: .7rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
  margin-bottom: .1rem; }
.lab { background: #f7f8fa; border: 1px solid #dfe3e8; border-top: 4px solid #c0392b; border-radius: 6px;
  padding: .85rem 1rem .9rem; }
.lab .sec { border: none; padding: 0; margin-bottom: .2rem; color: #c0392b; }
.lab .take { padding: .55rem 0; border-bottom: 1px solid #e3e7ec; font-size: .9rem; line-height: 1.45; }
.lab .take:last-of-type { border-bottom: none; }
.lab .take b.num { font-family: "Barlow Condensed", sans-serif; font-size: 1.2rem; }
.lab a { font-weight: 700; color: #c0392b !important; text-decoration: none !important; }
.lab .go { display: flex; gap: 1rem; margin-top: .4rem; font-size: .86rem; }
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------- ticker
def ticker() -> str:
    try:
        games, _ = board()
    except Exception:          # the front page should never fail because of the scores strip
        return ""
    order = [g for g in games if g.state == "in"] + [g for g in games if g.state == "pre"][:14] + \
            [g for g in games if g.state == "post"][:10]
    boxes = []
    for g in order[:30]:
        if g.sport == "Tennis" or len(g.sides) != 2:
            continue
        if g.state == "in":
            status = f'<span class="live">● {esc(g.detail)}</span>'
        elif g.state == "post":
            status = "<span>Final</span>"
        else:
            t = g.start.astimezone(ET)
            status = f"<span>{t:%a} {t:%I:%M %p}".replace(" 0", " ") + "</span>"
        rows = "".join(
            f'<div class="tk-row{" win" if s.winner else ""}"><span>{esc(s.short or s.name)}</span>'
            f'<b>{esc(s.score) if g.state != "pre" else ""}</b></div>' for s in g.sides)
        boxes.append(f'<a href="live?game={quote(g.key)}" target="_self"><div class="tk-top"><span>{esc(g.league)}</span>'
                     f'{status}</div>{rows}</a>')
    return f'<div class="ticker">{"".join(boxes)}</div>' if boxes else ""


# --------------------------------------------------------------- the lab
def lab_takes() -> str:
    """Our model's takes on today's games: where it disagrees most with Kalshi, and its surest pick."""
    try:
        games, _ = board()
    except Exception:
        return ""
    gaps, sure = [], []
    for g in games:
        if g.state != "pre" or len(g.sides) != 2 or g.sport in ("Tennis", "MMA"):
            continue
        mine = ours_for(g)
        if not mine:
            continue
        # Only teams with a real track record: early-season records say too little to argue with the market.
        played = [(winprob._share(x.record) or (0, 0))[1] for x in g.sides]
        if min(played) < 8:
            continue
        for s, p in ((g.sides[0], mine.away), (g.sides[1], mine.home)):
            if s.kalshi is not None and 0.08 <= s.kalshi <= 0.92:
                gaps.append((p - s.kalshi, s, p, g))
            sure.append((p, s, g))
    takes = []
    if gaps:
        gap, s, p, g = max(gaps, key=lambda x: x[0])
        takes.append(f'<div class="take">Our model likes <b>{esc(s.name)}</b> more than the market does: '
                     f'<b class="num">{p * 100:.0f}%</b> vs Kalshi\'s {s.kalshi * 100:.0f}% '
                     f'(<a href="live?game={quote(g.key)}" target="_self">{esc(g.league)}</a>).</div>')
        first = g
        others = [x for x in gaps if x[3].key != first.key] or gaps      # a different game from the first take
        gap, s, p, g = min(others, key=lambda x: x[0])
        takes.append(f'<div class="take">Most skeptical of <b>{esc(s.name)}</b>: we say '
                     f'<b class="num">{p * 100:.0f}%</b>, Kalshi says {s.kalshi * 100:.0f}% '
                     f'(<a href="live?game={quote(g.key)}" target="_self">{esc(g.league)}</a>).</div>')
    if sure:
        p, s, g = max(sure, key=lambda x: x[0])
        takes.append(f'<div class="take">Surest pick on the board: <b>{esc(s.name)}</b> wins in '
                     f'<b class="num">{p * 100:.0f}%</b> of 1,000,000 simulated games.</div>')
    if not takes:
        takes.append('<div class="take">No games to simulate right now. Check back closer to game time.</div>')
    return ('<div class="lab"><div class="sec">From the Lab</div>' + "".join(takes) +
            '<div class="go"><a href="bets" target="_self">Best bets now →</a>'
            '<a href="live" target="_self">All live odds →</a></div></div>')


# ------------------------------------------------------------ front page
def front(all_stories: list[news.Story]) -> str:
    tools = [("#1f6feb", "Live Odds", "live"), ("#5b3cc4", "Best Bets Now", "bets"), ("#2e7d3a", "NFL Lineups", "football"),
             ("#d0021b", "F1 Fantasy", "f1"), ("#0f7a86", "Fantasy Premier League", "fpl"),
             ("#c75a1c", "March Madness", "march-madness"), ("#5b3cc4", "Parlay Lab", "parlays"),
             ("#a3243f", "Niche Sports", "niche"), ("#c0392b", "How it works", "how-it-works")]
    rail = ('<div class="rail"><p class="intro"><b>Every game, played a million times.</b>Real data in, a million '
            'simulated games out, and the choice that comes out ahead most often.</p><div class="sec">Tools</div>'
            + "".join(f'<a class="tool" href="{u}" target="_self"><i style="background:{c}"></i>{esc(n)}</a>'
                      for c, n, u in tools) + "</div>")

    def img(s: news.Story) -> str:
        return f'<div class="img" style="background-image:url(\'{esc(s.image)}\')"></div>' if s.image else ""

    def tag(s: news.Story) -> str:
        return f'<span class="tag" style="color:{s.color}">{esc(s.league)}</span>'

    def meta(s: news.Story) -> str:
        return f'<div class="meta">{esc(s.byline) + " · " if s.byline else ""}{news.ago(s.published)}</div>'

    if not all_stories:
        main = '<div class="main"><div class="sec">Top Stories</div><p>Stories couldn\'t load right now.</p></div>'
        side_heads = ""
    else:
        lead, rest = all_stories[0], all_stories[1:]
        cards = [s for s in rest if s.image][:6]
        heads = [s for s in rest if s not in cards][:10]
        main = ('<div class="main"><div class="sec">Top Stories</div>'
                f'<a class="lead" href="{esc(lead.url)}" target="_blank" rel="noopener">{img(lead)}{tag(lead)}'
                f'<h2>{esc(lead.headline)}</h2><p>{esc(lead.dek)}</p>{meta(lead)}</a>'
                '<div class="more">' + "".join(
                    f'<a class="story" href="{esc(s.url)}" target="_blank" rel="noopener">{img(s)}{tag(s)}'
                    f'<h3>{esc(s.headline)}</h3>{meta(s)}</a>' for s in cards) + "</div></div>")
        side_heads = ('<div class="sec">Top Headlines</div><ul class="heads">' + "".join(
            f'<li><a href="{esc(s.url)}" target="_blank" rel="noopener"><small style="color:{s.color}">'
            f'{esc(s.league)} · {news.ago(s.published)}</small>{esc(s.headline)}</a></li>' for s in heads) + "</ul>")
    side = f'<div class="side">{side_heads}{lab_takes()}</div>'
    return f'<div class="front">{rail}{main}{side}</div>'


st.markdown(ticker(), unsafe_allow_html=True)
st.markdown(front(stories()), unsafe_allow_html=True)
st.caption("Stories and photos from ESPN; tap a story to read it there.")

# ------------------------------------------------------------------- tools
st.write("")
st.markdown('<div class="sec">Our tools</div>', unsafe_allow_html=True)
cards = [
    ("live", "Live · Every league", "Live Odds", LIVE, "Open Live Odds",
     "Scores for the top leagues worldwide with DraftKings, Kalshi and our own Monte Carlo odds side by side, "
     "search, and a page for every game with stats and a live odds chart, updated every 15 seconds."),
    ("bets", "Kalshi + DraftKings", "Best Bets Now", BETS, "Open Best Bets",
     "The best win/lose bets on today's and tomorrow's games: each app's price checked against the other, "
     "every pick played out a million times."),
    ("nfl", "NFL · Weekly", "Fantasy Football Lineups", FOOTBALL, "Open lineup optimizer",
     "Who to start this week. Connect your ESPN league or enter your roster, and see "
     "your chance of beating this week's opponent."),
    ("ncaa", "NCAA · March", "March Madness Bracket", MADNESS, "Open bracket simulator",
     "Title odds for every team and a complete bracket to fill out. Shows a projected field until "
     "Selection Sunday, then the real bracket."),
    ("epl", "Premier League · Weekly", "Fantasy Premier League", FPL, "Open FPL team picker",
     "Your best XI, bench order and captain, on any budget from £100m up or none at all. Or enter your "
     "FPL team ID."),
    ("f1", "Formula 1 · Race weekends", "F1 Fantasy", F1, "Open F1 Fantasy picker",
     "The best 5 drivers and 2 constructors for the F1 app's fantasy game, on your budget, plus who gets "
     "the DRS Boost. Prices straight from F1 Fantasy."),
    ("bets", "Parlays · Every day", "Parlay Lab", PARLAYS, "Open Parlay Lab",
     "The best parlays for your risk and payout, from 80,000+ DraftKings and Kalshi markets, niche sports "
     "included, each tested on a million simulated slates."),
    ("niche", "Off the beaten path", "Niche Sports", NICHE, "Open Niche Sports",
     "Russian table tennis, Bosnian basketball, Valorant, women's cricket: every obscure market on the board, "
     "ranked by a Niche-o-meter, with the best bets for your risk and payout."),
]
for row in (cards[:4], cards[4:]):
    for col, (sport, label, title, path, cta, text) in zip(st.columns(len(row), gap="medium"), row):
        slug = path.split("/")[-1].removesuffix(".py")       # unique per card (two cards can share a color)
        with col, st.container(key=f"card_{slug}"):
            st.markdown(card_top(sport, label), unsafe_allow_html=True)
            st.subheader(title)
            st.markdown(f'<p class="card-text">{text}</p>', unsafe_allow_html=True)
            with st.container(key=f"cardlink_{slug}"):
                st.page_link(path, label=cta, icon=":material/arrow_forward:", width="stretch")
st.page_link("views/method.py", label="How the simulations work, with the code", icon=":material/menu_book:")

# ------------------------------------------------------------------- footer
st.divider()
st.caption("Data: ESPN (news, scores, fantasy), DraftKings odds via ESPN, Kalshi's public market data, the official "
           "Fantasy Premier League and F1 Fantasy games, Formula 1 images and the Jolpica F1 database. Not affiliated "
           "with ESPN, DraftKings, Kalshi, the NFL, the NCAA, the Premier League or Formula 1. For entertainment; no "
           "outcome is guaranteed. Betting is 21+; if gambling stops being fun, call 1-800-GAMBLER. "
           f"Version {APP_VERSION}.")
