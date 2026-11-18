"""Top stories: the latest headlines across the sports the site covers, from ESPN's public news feed.

Each story keeps its headline, short summary, photo, writer, time and a link to the full article on ESPN.
"""

from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .http import APIError, CachedJSON

NEWS = "https://site.api.espn.com/apis/site/v2/sports/{path}/news"

# (label shown on the story, ESPN path, how many to fetch, weight when choosing the lead stories)
FEEDS = [
    ("NFL", "football/nfl", 12, 1.0),
    ("NBA", "basketball/nba", 10, 0.95),
    ("College Football", "football/college-football", 6, 0.8),
    ("NHL", "hockey/nhl", 6, 0.75),
    ("Premier League", "soccer/eng.1", 6, 0.8),
    ("Champions League", "soccer/uefa.champions", 4, 0.75),
    ("F1", "racing/f1", 5, 0.8),
    ("MLB", "baseball/mlb", 5, 0.7),
    ("College Basketball", "basketball/mens-college-basketball", 5, 0.7),
]

# Story tag colours (one per sport, matching the rest of the site).
TAG_COLORS = {"NFL": "#2e7d3a", "College Football": "#2e7d3a", "NBA": "#c75a1c", "College Basketball": "#c75a1c",
              "NHL": "#0f6fa8", "MLB": "#b3261e", "Premier League": "#0f7a86", "Champions League": "#0f7a86",
              "F1": "#d0021b"}


@dataclass
class Story:
    league: str
    headline: str
    dek: str
    url: str
    image: str
    byline: str
    published: dt.datetime
    weight: float = 1.0

    @property
    def color(self) -> str:
        return TAG_COLORS.get(self.league, "#5b6878")


def ago(when: dt.datetime, now: dt.datetime | None = None) -> str:
    """'12m ago', '3h ago', 'Yesterday', 'Nov 14'."""
    now = now or dt.datetime.now(dt.timezone.utc)
    mins = int((now - when).total_seconds() // 60)
    if mins < 1:
        return "Just now"
    if mins < 60:
        return f"{mins}m ago"
    if mins < 24 * 60:
        return f"{mins // 60}h ago"
    if mins < 48 * 60:
        return "Yesterday"
    return f"{when:%b} {when.day}"


def _story(a: dict, league: str, weight: float) -> Story | None:
    try:
        when = dt.datetime.fromisoformat(a["published"].replace("Z", "+00:00"))
    except (KeyError, ValueError, AttributeError):
        return None
    url = ((a.get("links") or {}).get("web") or {}).get("href", "")
    if not a.get("headline") or not url:
        return None
    imgs = [i for i in a.get("images") or [] if isinstance(i, dict) and i.get("url")]
    # Prefer a wide header photo for the big slots.
    imgs.sort(key=lambda i: (i.get("type") != "header", -(i.get("width") or 0)))
    return Story(league=league, headline=a["headline"].strip(), dek=(a.get("description") or "").strip(), url=url,
                 image=imgs[0]["url"] if imgs else "", byline=(a.get("byline") or "").strip(), published=when,
                 weight=weight)


def top_stories(cache_dir=".ffmc_cache", limit: int = 30, now: dt.datetime | None = None) -> list[Story]:
    """The newest stories across all feeds, freshest and most important first, without duplicates."""
    now = now or dt.datetime.now(dt.timezone.utc)
    http = CachedJSON(cache_dir)

    def one(feed):
        league, path, n, weight = feed
        try:
            data = http.get(NEWS.format(path=path), [("limit", str(n))], ttl=600)
        except APIError:
            return []
        return [s for s in (_story(a, league, weight) for a in data.get("articles") or [])
                if s is not None]

    with ThreadPoolExecutor(6) as pool:
        stories = [s for part in pool.map(one, FEEDS) for s in part]
    seen, out = set(), []
    for s in sorted(stories, key=lambda s: -s.published.timestamp()):
        key = s.headline.lower()[:60]
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out[:limit]


def lead_order(stories: list[Story], now: dt.datetime | None = None) -> list[Story]:
    """Order for the front page: recent stories with photos first, bigger sports a little ahead."""
    now = now or dt.datetime.now(dt.timezone.utc)

    def score(s: Story) -> float:
        hours = max((now - s.published).total_seconds() / 3600, 0)
        return s.weight * (1.0 if s.image else 0.55) / (1 + hours / 6)
    return sorted(stories, key=lambda s: -score(s))
