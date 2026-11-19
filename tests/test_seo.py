"""The search-engine pages: titles, descriptions, guides, sitemap and routes."""

import json
import os
import re

os.environ["MSL_NO_SNAPSHOT"] = "1"          # no network in tests

from seo import site  # noqa: E402
from seo.content import GUIDES, PAGES, SITE  # noqa: E402


def test_titles_and_descriptions_fit_in_google():
    for p in PAGES:
        assert len(p.title) <= 65, p.title
        assert 70 <= len(p.description) <= 170, p.path
    for g in GUIDES:
        assert len(g.title) <= 75, g.title
        assert 70 <= len(g.description) <= 170, g.slug
    assert len({p.title for p in PAGES} | {g.title for g in GUIDES}) == len(PAGES) + len(GUIDES)


def test_every_app_page_gets_its_own_head_and_content():
    for p in PAGES:
        text = site.page_html(p.path)
        assert text.count("<title>") == 1 and f"<title>{site.e(p.title)}</title>" in text
        assert f'<link rel="canonical" href="{site.page_url(p.path)}" />' in text
        assert "og:image" in text and "<h1>" in text
        assert re.search(r'<script type="module"[^>]+index\.[^"]+\.js', text), "Streamlit's app script must stay"
        data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S).group(1))
        assert any(n["@type"] == "WebPage" for n in data["@graph"])


def test_guides_are_complete_pages_with_faq_schema():
    for g in GUIDES:
        text = site.guide_html(g.slug)
        assert text.startswith("<!DOCTYPE html>") and f"<h1>{site.e(g.h1)}</h1>" in text
        assert f'href="/{g.cta[0]}"' in text
        data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', text, re.S).group(1))
        assert {"Article", "FAQPage", "BreadcrumbList"} <= {n["@type"] for n in data["@graph"]}
        assert g.cta[0] in {p.path for p in PAGES}
        for p in g.sections:
            assert p[1], g.slug


def test_sitemap_lists_pages_and_guides():
    xml = site.sitemap_xml()
    assert xml.count("<url>") == len(PAGES) + 1 + len(GUIDES)
    assert f"<loc>{SITE}/</loc>" in xml and f"<loc>{SITE}/guides/{GUIDES[0].slug}</loc>" in xml
    assert f"Sitemap: {SITE}/sitemap.xml" in site.ROBOTS


def test_routes_answer():
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    client = TestClient(Starlette(routes=site.routes()))
    for path in ["/", "/bets", "/guides", f"/guides/{GUIDES[0].slug}", "/sitemap.xml", "/robots.txt",
                 "/favicon.ico", "/og.png", "/logo.svg", "/manifest.webmanifest"]:
        assert client.get(path).status_code == 200, path
    assert client.get("/guides/nope", follow_redirects=False).status_code == 301
