"""What search engines and link previews get: real HTML for every page, guides, sitemap, robots.txt and icons.

Streamlit serves one bare page and builds everything in the browser. These routes run on the same server
(see app.py) and answer first:

* every app page (/, /live, /bets, ...) gets Streamlit's own page with that page's title, description, share
  image and structured data, plus a plain-HTML version of the page inside the app's root element. Google reads
  it; visitors see the app replace it as soon as it loads.
* /live, /bets and the home page also list today's games and best bets in plain HTML, refreshed every few
  minutes, so Google sees fresh content every day.
* /guides/... are plain articles answering common searches ("what does +150 mean", "best FPL team"), each
  linking into the tool.
* /sitemap.xml, /robots.txt, favicons, the app icon and the share image.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import threading
import time
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from .content import GUIDE_BY_SLUG, GUIDES, NAME, PAGE_BY_PATH, PAGES, SITE, TAGLINE, Guide, Page

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "static" / "brand"
EASTERN = ZoneInfo("America/New_York")
OG_IMAGE = f"{SITE}/og.png"
THEME = "#0c1a2b"
e = html.escape


def esc(s: str) -> str:
    return html.escape(s, quote=True)


# ---------------------------------------------------------------- Streamlit's page, cleaned once

@lru_cache(maxsize=1)
def streamlit_shell() -> str:
    """Streamlit's index.html with its title and root emptied (and any older SEO patch removed)."""
    import streamlit
    text = (Path(streamlit.__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
    text = re.sub(r"<!-- seo:monte-sports-lab -->.*?</script>", "", text, flags=re.S)
    text = re.sub(r'<div id="root">.*?</div>\s*(?=</body>)', '<div id="root"></div>\n  ', text, flags=re.S)
    text = re.sub(r'<link rel="shortcut icon"[^>]*>', "", text)
    return re.sub(r"<title>.*?</title>", "<title></title>", text, count=1, flags=re.S)


# ---------------------------------------------------------------- shared pieces

def schema_graph(url: str, title: str, description: str, extra: list[dict] | None = None) -> str:
    graph = [
        {"@type": "Organization", "@id": f"{SITE}/#org", "name": NAME, "url": f"{SITE}/",
         "logo": {"@type": "ImageObject", "url": f"{SITE}/icon-512.png", "width": 512, "height": 512}},
        {"@type": "WebSite", "@id": f"{SITE}/#site", "name": NAME, "alternateName": ["Monte", "MC Sports Lab"],
         "url": f"{SITE}/", "publisher": {"@id": f"{SITE}/#org"}, "description": PAGES[0].description},
        {"@type": "WebPage", "@id": url, "url": url, "name": title, "description": description,
         "isPartOf": {"@id": f"{SITE}/#site"}, "primaryImageOfPage": OG_IMAGE, "inLanguage": "en-US"},
    ] + (extra or [])
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")


def head_tags(url: str, title: str, description: str, extra_schema: list[dict] | None = None,
              og_type: str = "website") -> str:
    return "\n".join([
        f'<meta name="description" content="{esc(description)}" />',
        '<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1" />',
        f'<link rel="canonical" href="{url}" />',
        '<link rel="icon" href="/favicon.ico" sizes="any" />',
        '<link rel="icon" type="image/svg+xml" href="/logo.svg" />',
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png" />',
        '<link rel="manifest" href="/manifest.webmanifest" />',
        f'<meta name="theme-color" content="{THEME}" />',
        f'<meta name="application-name" content="{NAME}" />',
        f'<meta name="apple-mobile-web-app-title" content="{NAME}" />',
        f'<meta property="og:type" content="{og_type}" />',
        f'<meta property="og:site_name" content="{NAME}" />',
        f'<meta property="og:title" content="{esc(title)}" />',
        f'<meta property="og:description" content="{esc(description)}" />',
        f'<meta property="og:url" content="{url}" />',
        f'<meta property="og:image" content="{OG_IMAGE}" />',
        '<meta property="og:image:width" content="1200" />',
        '<meta property="og:image:height" content="630" />',
        f'<meta property="og:image:alt" content="{NAME}: {esc(TAGLINE)}" />',
        '<meta property="og:locale" content="en_US" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{esc(title)}" />',
        f'<meta name="twitter:description" content="{esc(description)}" />',
        f'<meta name="twitter:image" content="{OG_IMAGE}" />',
        f'<script type="application/ld+json">{schema_graph(url, title, description, extra_schema)}</script>',
    ])


def page_url(path: str) -> str:
    return f"{SITE}/{path}" if path else f"{SITE}/"


def footer_links() -> str:
    tools = "".join(f'<li><a href="/{p.path}">{e(p.nav)}</a></li>' for p in PAGES[1:])
    guides = "".join(f'<li><a href="/guides/{g.slug}">{e(g.nav)}</a></li>' for g in GUIDES)
    return (f'<nav class="ms-foot"><div><h2>Tools</h2><ul>{tools}</ul></div>'
            f'<div><h2>Guides</h2><ul>{guides}</ul></div></nav>'
            f'<p class="ms-small">{NAME} shows simulated chances, not guarantees. Bet only what you can afford '
            f'to lose. 21+. Gambling problem? Call 1-800-GAMBLER.</p>')


LOGO_HTML = (f'<a class="ms-logo" href="/" aria-label="{NAME} home"><img src="/logo.svg" width="34" height="34" '
             f'alt="" /><span>Monte <b>Sports Lab</b></span></a>')


# ---------------------------------------------------------------- today's games and bets (plain HTML)

class Snapshot:
    """Today's board in plain HTML, rebuilt in the background at most every REFRESH seconds."""
    REFRESH = 600

    def __init__(self):
        self.games_html = ""
        self.bets_html = ""
        self.stamp = 0.0
        self._lock = threading.Lock()
        self._busy = False

    def get(self) -> "Snapshot":
        with self._lock:
            stale = time.time() - self.stamp > self.REFRESH
            if stale and not self._busy and not os.environ.get("MSL_NO_SNAPSHOT"):
                self._busy = True
                threading.Thread(target=self._rebuild, daemon=True).start()
        return self

    def _rebuild(self):
        try:
            games, bets = build_snapshot()
            self.games_html, self.bets_html = games, bets
        except Exception:                               # data sources down: keep the last good copy
            pass
        finally:
            self.stamp = time.time()
            self._busy = False


SNAPSHOT = Snapshot()


def american(o: int | None) -> str:
    return "" if o is None else (f"+{o}" if o > 0 else str(o))


def build_snapshot() -> tuple[str, str]:
    from ffmc import bestbets, live, winprob
    games = live.load_board()
    today = dt.datetime.now(EASTERN).strftime("%A, %B %-d, %Y")
    rows = []
    for g in sorted(games, key=lambda g: (g.league, g.start))[:60]:
        if len(g.sides) < 2:
            continue
        a, h = g.sides[0], g.sides[1]
        score = f"{a.score}-{h.score}" if g.state != "pre" and a.score != "" else ""
        dk = " / ".join(x for x in (american(a.dk), american(h.dk)) if x)
        ks = " / ".join(f"{x.kalshi * 100:.0f}%" for x in (a, h) if x.kalshi is not None)
        rows.append(f"<tr><td>{e(g.league)}</td><td>{e(a.name)} at {e(h.name)}</td><td>{e(g.detail)}</td>"
                    f"<td>{e(score)}</td><td>{e(dk)}</td><td>{e(ks)}</td></tr>")
    games_html = ""
    if rows:
        games_html = (f'<section><h2>Today\'s games and odds: {e(today)}</h2><table><thead><tr><th>League</th>'
                      f'<th>Game</th><th>Time / status</th><th>Score</th><th>DraftKings moneyline</th>'
                      f'<th>Kalshi chance</th></tr></thead><tbody>{"".join(rows)}</tbody></table></section>')
    edges = bestbets.model_edges(games, lambda g: winprob.own_odds(g, n_sims=200_000), top=10)
    items = []
    for x in edges:
        when = x.game.start.astimezone(EASTERN).strftime("%-I:%M %p ET")
        items.append(f"<li><strong>{e(x.side.name)}</strong> ({e(x.game.league)}, {e(x.game.label)}, {when}): "
                     f"our simulations give {x.ours * 100:.0f}%, Kalshi charges {x.ask * 100:.0f}¢ "
                     f"({x.gap * 100:+.0f} points).</li>")
    bets_html = ""
    if items:
        bets_html = (f'<section><h2>Best bets today: {e(today)}</h2><p>Teams our 1,000,000-game simulations rate '
                     f'higher than the Kalshi price, biggest gap first. Good value isn\'t the same as likely to '
                     f'win.</p><ol>{"".join(items)}</ol></section>')
    return games_html, bets_html


# ---------------------------------------------------------------- app pages

FALLBACK_CSS = """<style>
.ms-fb{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:920px;margin:0 auto;padding:0 1rem 3rem;
color:#111827;line-height:1.55}.ms-fb a{color:#1d5fa8}.ms-top{background:#0c1a2b;margin:0 -1rem 2rem;
padding:1rem}.ms-logo{display:inline-flex;align-items:center;gap:.6rem;color:#fff!important;
text-decoration:none;font-weight:800;font-size:1.3rem}.ms-logo b{font-weight:600;color:#c9d3df}
.ms-fb table{border-collapse:collapse;width:100%;font-size:.9rem}.ms-fb td,.ms-fb th{border-bottom:1px solid #e5e7eb;
padding:.35rem .5rem;text-align:left}.ms-foot{display:flex;gap:3rem;flex-wrap:wrap}.ms-foot ul{list-style:none;
padding:0}.ms-foot h2{font-size:1rem}.ms-small{color:#6b7280;font-size:.85rem}
@media (prefers-color-scheme:dark){.ms-fb{color:#e3e9f0}.ms-fb a{color:#7fb2f5}}
</style>"""


def page_root(p: Page) -> str:
    points = "".join(f"<li>{e(x)}</li>" for x in p.points)
    snap = ""
    if p.path in ("", "live", "bets"):
        s = SNAPSHOT.get()
        snap = (s.bets_html + s.games_html) if p.path in ("", "bets") else (s.games_html + s.bets_html)
    guides = "".join(f'<li><a href="/guides/{g}">{e(GUIDE_BY_SLUG[g].h1)}</a></li>' for g in p.guides
                     if g in GUIDE_BY_SLUG)
    return (f'<div id="root">{FALLBACK_CSS}<div class="ms-fb"><header class="ms-top">{LOGO_HTML}</header>'
            f'<main><h1>{e(p.h1)}</h1><p>{e(p.intro)}</p><ul>{points}</ul>{snap}'
            + (f"<section><h2>Learn more</h2><ul>{guides}</ul></section>" if guides else "")
            + f"</main>{footer_links()}</div></div>")


@lru_cache(maxsize=64)
def _page_head(path: str) -> tuple[str, str]:
    p = PAGE_BY_PATH[path]
    url = page_url(path)
    crumbs = [] if not path else [{"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": NAME, "item": f"{SITE}/"},
        {"@type": "ListItem", "position": 2, "name": p.nav, "item": url}]}]
    return f"<title>{e(p.title)}</title>", head_tags(url, p.title, p.description, crumbs)


def page_html(path: str) -> str:
    title, head = _page_head(path)
    text = streamlit_shell().replace("<title></title>", title, 1)
    text = text.replace("</head>", head + "\n  </head>", 1)
    return text.replace('<div id="root"></div>', page_root(PAGE_BY_PATH[path]), 1)


# ---------------------------------------------------------------- guides

GUIDE_CSS = """<style>
:root{--ink:#111827;--sub:#374151;--muted:#6b7280;--line:#e5e7eb;--bg:#fff;--soft:#f5f6f8;--link:#1d5fa8;
--accent:#d6232a}
@media (prefers-color-scheme:dark){:root{--ink:#e3e9f0;--sub:#c3ccd6;--muted:#93a1b1;--line:#2a3644;--bg:#0d141d;
--soft:#18222f;--link:#7fb2f5;--accent:#ff4d55}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:17px/1.65 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--link)}.top{background:#0c1a2b}.top .in{max-width:1160px;margin:0 auto;padding:0 1rem;height:68px;
display:flex;align-items:center;justify-content:space-between;gap:1rem}
.ms-logo{display:inline-flex;align-items:center;gap:.6rem;color:#fff;text-decoration:none;font:800 1.3rem Archivo,
sans-serif;letter-spacing:-.01em;white-space:nowrap}.ms-logo b{font-weight:600;color:#c9d3df}
.top nav{display:flex;gap:1.1rem;overflow-x:auto}.top nav a{color:#c9d3df;text-decoration:none;font-weight:600;
font-size:.95rem;white-space:nowrap}.top nav a:hover{color:#fff}
@media (max-width:760px){.top nav{display:none}}
article{max-width:740px;margin:0 auto;padding:2.2rem 1rem 1rem}.crumb{font-size:.85rem;color:var(--muted)}
.crumb a{color:var(--muted)}h1{font:800 2.3rem/1.12 Archivo,sans-serif;letter-spacing:-.02em;margin:.4rem 0 1rem}
@media (max-width:520px){h1{font-size:1.8rem}}h2{font:800 1.35rem/1.25 Archivo,sans-serif;margin:2rem 0 .5rem}
.lede{font-size:1.15rem;color:var(--sub)}.cta{display:inline-block;background:var(--accent);color:#fff;
text-decoration:none;font-weight:700;padding:.75rem 1.3rem;border-radius:6px;margin:1rem 0}
.cta:hover{filter:brightness(1.08)}.box{background:var(--soft);border:1px solid var(--line);border-radius:8px;
padding:1rem 1.2rem;margin:2rem 0}.faq h3{font-size:1.02rem;margin:1.1rem 0 .2rem}.faq p{margin:0}
.more ul{padding-left:1.2rem}.wrap{max-width:740px;margin:0 auto;padding:0 1rem 3rem}
.ms-foot{display:flex;gap:3rem;flex-wrap:wrap;border-top:1px solid var(--line);margin-top:2rem;padding-top:1rem}
.ms-foot h2{font-size:1rem;margin:.6rem 0}.ms-foot ul{list-style:none;padding:0;margin:0;font-size:.95rem}
.ms-small{color:var(--muted);font-size:.85rem}
</style>"""
FONTS = ('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;800&'
         'family=IBM+Plex+Sans:wght@400;600;700&display=swap" />')


def _top_nav() -> str:
    links = "".join(f'<a href="/{p.path}">{e(p.nav)}</a>' for p in PAGES[1:8])
    return f'<header class="top"><div class="in">{LOGO_HTML}<nav>{links}</nav></div></header>'


def _doc(title: str, head: str, body: str) -> str:
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8" />'
            f'<meta name="viewport" content="width=device-width, initial-scale=1" /><title>{e(title)}</title>'
            f"{head}{FONTS}{GUIDE_CSS}</head><body>{_top_nav()}{body}</body></html>")


@lru_cache(maxsize=64)
def guide_html(slug: str) -> str:
    g: Guide = GUIDE_BY_SLUG[slug]
    url = f"{SITE}/guides/{slug}"
    cta_path, cta_text = g.cta
    sections = "".join(f"<h2>{e(h)}</h2>" + "".join(f"<p>{e(p)}</p>" for p in ps) for h, ps in g.sections)
    faq = "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in g.faq)
    related = "".join(f'<li><a href="/guides/{o.slug}">{e(o.h1)}</a></li>' for o in GUIDES if o.slug != slug)
    schema = [
        {"@type": "Article", "headline": g.h1, "description": g.description, "image": OG_IMAGE,
         "mainEntityOfPage": url, "author": {"@id": f"{SITE}/#org"}, "publisher": {"@id": f"{SITE}/#org"},
         "datePublished": "2026-11-19", "dateModified": dt.date.today().isoformat()},
        {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q,
                                             "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in g.faq]},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": NAME, "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "Guides", "item": f"{SITE}/guides"},
            {"@type": "ListItem", "position": 3, "name": g.nav, "item": url}]},
    ]
    body = (f'<article><div class="crumb"><a href="/">Home</a> › <a href="/guides">Guides</a> › {e(g.nav)}</div>'
            f'<h1>{e(g.h1)}</h1><p class="lede">{e(g.lede)}</p>'
            f'<a class="cta" href="/{cta_path}">{e(cta_text)} →</a>{sections}'
            f'<div class="box"><strong>Try it now:</strong> <a href="/{cta_path}">{e(cta_text)}</a>. Free, no '
            f'sign-up, every game simulated 1,000,000 times.</div>'
            f'<section class="faq"><h2>Questions</h2>{faq}</section>'
            f'<section class="more"><h2>More guides</h2><ul>{related}</ul></section></article>'
            f'<div class="wrap">{footer_links()}</div>')
    return _doc(g.title, head_tags(url, g.title, g.description, schema, og_type="article"), body)


@lru_cache(maxsize=1)
def guides_index_html() -> str:
    url = f"{SITE}/guides"
    title = f"Sports Betting & Fantasy Guides | {NAME}"
    desc = ("Plain-English guides to betting odds, best bets, parlays and fantasy lineups for NFL, FPL and "
            "F1 Fantasy, from the team that simulates every game a million times.")
    items = "".join(f'<li><a href="/guides/{g.slug}"><strong>{e(g.h1)}</strong></a><br />{e(g.description)}</li>'
                    for g in GUIDES)
    body = (f'<article><h1>Guides</h1><p class="lede">{e(desc)}</p><ul class="list" style="padding-left:1.2rem">'
            f'{items}</ul></article><div class="wrap">{footer_links()}</div>')
    return _doc(title, head_tags(url, title, desc), body)


# ---------------------------------------------------------------- sitemap, robots, manifest

def sitemap_xml() -> str:
    today = dt.date.today().isoformat()
    urls = [(page_url(p.path), "hourly" if p.path in ("", "live", "bets") else "daily",
             "1.0" if not p.path else "0.8") for p in PAGES]
    urls += [(f"{SITE}/guides", "weekly", "0.6")] + [(f"{SITE}/guides/{g.slug}", "monthly", "0.7") for g in GUIDES]
    body = "".join(f"<url><loc>{u}</loc><lastmod>{today}</lastmod><changefreq>{c}</changefreq>"
                   f"<priority>{pr}</priority></url>" for u, c, pr in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{body}</urlset>\n")


ROBOTS = f"""User-agent: *
Allow: /
Disallow: /_stcore/
Disallow: /media/

Sitemap: {SITE}/sitemap.xml
"""

MANIFEST = json.dumps({
    "name": NAME, "short_name": "Monte", "description": PAGES[0].description, "start_url": "/",
    "display": "standalone", "background_color": THEME, "theme_color": THEME,
    "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
              {"src": "/logo.svg", "sizes": "any", "type": "image/svg+xml"}]})


# ---------------------------------------------------------------- Starlette routes

def routes() -> list:
    from starlette.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response
    from starlette.routing import Route

    no_cache = {"Cache-Control": "no-cache"}
    day = {"Cache-Control": "public, max-age=86400"}

    def app_page(path: str):
        async def handler(request):
            return HTMLResponse(page_html(path), headers=no_cache)
        return handler

    async def guide(request):
        slug = request.path_params["slug"]
        if slug not in GUIDE_BY_SLUG:
            return RedirectResponse("/guides", status_code=301)
        return HTMLResponse(guide_html(slug), headers={"Cache-Control": "public, max-age=3600"})

    async def guides(request):
        return HTMLResponse(guides_index_html(), headers={"Cache-Control": "public, max-age=3600"})

    async def sitemap(request):
        return Response(sitemap_xml(), media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})

    async def robots(request):
        return PlainTextResponse(ROBOTS, headers=day)

    async def manifest(request):
        return Response(MANIFEST, media_type="application/manifest+json", headers=day)

    def file(name: str, media: str):
        async def handler(request):
            return FileResponse(BRAND / name, media_type=media, headers=day)
        return handler

    out = [Route(("/" + p.path) if p.path else "/", app_page(p.path), methods=["GET", "HEAD"]) for p in PAGES]
    out += [
        Route("/guides", guides, methods=["GET", "HEAD"]),
        Route("/guides/{slug}", guide, methods=["GET", "HEAD"]),
        Route("/sitemap.xml", sitemap, methods=["GET", "HEAD"]),
        Route("/robots.txt", robots, methods=["GET", "HEAD"]),
        Route("/manifest.webmanifest", manifest, methods=["GET", "HEAD"]),
        Route("/favicon.ico", file("favicon.ico", "image/x-icon"), methods=["GET", "HEAD"]),
        Route("/favicon.png", file("favicon-48.png", "image/png"), methods=["GET", "HEAD"]),
        Route("/apple-touch-icon.png", file("apple-touch-icon.png", "image/png"), methods=["GET", "HEAD"]),
        Route("/icon-192.png", file("icon-192.png", "image/png"), methods=["GET", "HEAD"]),
        Route("/icon-512.png", file("icon-512.png", "image/png"), methods=["GET", "HEAD"]),
        Route("/logo.svg", file("mark.svg", "image/svg+xml"), methods=["GET", "HEAD"]),
        Route("/og.png", file("og.png", "image/png"), methods=["GET", "HEAD"]),
    ]
    return out
