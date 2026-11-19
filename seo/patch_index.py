"""Give search engines and link previews something to read.

Streamlit serves one bare page (title "Streamlit") and builds everything else in the browser, so Google and
link previews (iMessage, Discord, X...) see almost nothing. This rewrites that page once, at build time:

* the title and description Google shows in results,
* link-preview tags (Open Graph / Twitter) and structured data,
* a plain-HTML version of the site inside the app's root element, which search engines read and visitors see
  for a moment while the app loads (the app then replaces it).

Run it after installing requirements:  python seo/patch_index.py
It is safe to run more than once.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys

SITE = "https://montesportslab.com"
NAME = "Monte Sports Lab"
TITLE = "Best Bets, Live Odds & Fantasy Lineups | Monte Sports Lab"
DESCRIPTION = ("Today's best bets and live odds from DraftKings and Kalshi, plus the best fantasy lineup for NFL, "
               "FPL and F1 Fantasy. Every game simulated 1,000,000 times.")
KEYWORDS = ("best bets today, best bets, live odds, kalshi odds, draftkings odds, best fantasy lineup, "
            "best fantasy football lineup, who to start, fpl best team, f1 fantasy team, parlay picks, "
            "march madness bracket predictions, sports betting model, monte carlo simulation")
MARK = "<!-- seo:monte-sports-lab -->"

# The plain-HTML version of the site: real headings and sentences for each tool, with links.
SECTIONS = [
    ("live", "Live odds and scores",
     "Live scores and odds for the NFL, NBA, NHL, MLB, college football and basketball, the Premier League, "
     "Champions League and more, with DraftKings lines, Kalshi prices and our own win odds side by side."),
    ("bets", "Best bets today",
     "Today's best bets: teams our simulations rate higher than the Kalshi price, biggest gap first, with the "
     "exact payout for your stake."),
    ("football", "Best fantasy football lineup this week",
     "Who to start in your ESPN fantasy football league: your best lineup and your chance of beating this "
     "week's opponent, from projections, recent games and injuries."),
    ("f1", "Best F1 Fantasy team",
     "The best 5 drivers and 2 constructors for F1 Fantasy on your budget, plus who gets the DRS Boost, "
     "using official prices and every race simulated a million times."),
    ("fpl", "Best FPL team this gameweek",
     "Fantasy Premier League: the best XI, bench and captain for this gameweek on any budget, from xG, xA, "
     "minutes and fixtures."),
    ("parlays", "Parlay picks",
     "The best parlays for your risk and payout from 80,000+ DraftKings and Kalshi markets, each tested on a "
     "million simulated slates."),
    ("march-madness", "March Madness bracket predictions",
     "Title odds for every team and a full bracket to fill out, from every Division I score this season."),
    ("track-record", "Track record",
     "How every pick has done on real results: best bets, F1 Fantasy, FPL and NFL lineups."),
]


def head_tags() -> str:
    e = lambda s: html.escape(s, quote=True)
    schema = {"@context": "https://schema.org", "@type": "WebSite", "name": NAME, "url": SITE + "/",
              "description": DESCRIPTION}
    return "\n".join([
        MARK,
        f'<meta name="description" content="{e(DESCRIPTION)}" />',
        f'<meta name="keywords" content="{e(KEYWORDS)}" />',
        '<meta name="robots" content="index, follow" />',
        f'<link rel="canonical" href="{SITE}/" />',
        '<meta property="og:type" content="website" />',
        f'<meta property="og:site_name" content="{e(NAME)}" />',
        f'<meta property="og:title" content="{e(TITLE)}" />',
        f'<meta property="og:description" content="{e(DESCRIPTION)}" />',
        f'<meta property="og:url" content="{SITE}/" />',
        '<meta name="twitter:card" content="summary" />',
        f'<meta name="twitter:title" content="{e(TITLE)}" />',
        f'<meta name="twitter:description" content="{e(DESCRIPTION)}" />',
        '<meta name="theme-color" content="#0c1a2b" />',
        f'<script type="application/ld+json">{json.dumps(schema)}</script>',
    ])


def root_content() -> str:
    e = html.escape
    items = "".join(f'<li><h2><a href="/{path}">{e(head)}</a></h2><p>{e(text)}</p></li>' for path, head, text in SECTIONS)
    return (f'<div id="root"><main style="font-family:system-ui,sans-serif;max-width:860px;margin:3rem auto;'
            f'padding:0 1rem;color:#111827"><h1>{e(NAME)}: best bets, live odds and fantasy lineups</h1>'
            f'<p>{e(DESCRIPTION)}</p><ul style="list-style:none;padding:0">{items}</ul></main></div>')


def patch(text: str) -> str:
    if MARK in text:                                     # already done: refresh the parts we own
        text = re.sub(re.escape(MARK) + r".*?</script>", "", text, flags=re.S)
        text = re.sub(r'<div id="root">.*?</div>\s*(?=</body>)', '<div id="root"></div>\n  ', text, flags=re.S)
    text = re.sub(r"<title>.*?</title>", f"<title>{html.escape(TITLE)}</title>", text, count=1, flags=re.S)
    text = text.replace("</head>", head_tags() + "\n  </head>", 1)
    text = text.replace('<div id="root"></div>', root_content(), 1)
    return text


def index_path() -> str:
    import streamlit
    return os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")


def main() -> int:
    path = index_path()
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        new = patch(text)
        if new != text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
        print(f"SEO tags written to {path}")
        return 0
    except OSError as exc:                               # read-only install: the app still works, just without tags
        print(f"Could not update {path}: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
