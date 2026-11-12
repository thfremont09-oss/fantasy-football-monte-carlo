"""Men's college basketball data from ESPN's public scoreboard (no key needed)."""

from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .http import APIError, CachedJSON

SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
NCAA_TOURNAMENT_ID = 22
DAY = 24 * 3600

ROUND_NAMES = ["1st Round", "2nd Round", "Sweet 16", "Elite 8", "Final Four", "National Championship"]


@dataclass
class Game:
    date: dt.date
    home_id: str
    away_id: str
    home_score: int
    away_score: int
    neutral: bool
    completed: bool
    tournament: bool = False
    region: str | None = None
    round: str | None = None
    home_seed: int | None = None
    away_seed: int | None = None


class ESPNClient:
    def __init__(self, cache_dir=".ffmc_cache"):
        self.http = CachedJSON(cache_dir)
        self.teams: dict[str, dict] = {}   # id -> {"name", "short", "logo"}

    def day(self, date: dt.date, tournament_only: bool = False) -> list[Game]:
        """All Division I games on one date."""
        age = (dt.date.today() - date).days
        ttl = 30 * DAY if age > 3 else 600   # finished days never change
        params = [("dates", date.strftime("%Y%m%d")), ("groups", "100" if tournament_only else "50"),
                  ("limit", "1000")]
        data = self.http.get(SCOREBOARD, params, ttl=ttl)
        return [g for e in data.get("events", []) if (g := self._parse(e, date))]

    def days(self, start: dt.date, end: dt.date, tournament_only: bool = False) -> list[Game]:
        dates = [start + dt.timedelta(d) for d in range((end - start).days + 1)]
        with ThreadPoolExecutor(8) as pool:
            chunks = pool.map(lambda d: self._safe_day(d, tournament_only), dates)
        return [g for chunk in chunks for g in chunk]

    def _safe_day(self, date, tournament_only):
        try:
            return self.day(date, tournament_only)
        except APIError:
            return []

    def _parse(self, event: dict, date: dt.date) -> Game | None:
        comp = event["competitions"][0]
        sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
        if "home" not in sides or "away" not in sides:
            return None
        for c in sides.values():
            t = c.get("team", {})
            if t.get("id") and t["id"] not in self.teams:
                self.teams[t["id"]] = {"name": t.get("location") or t.get("displayName", "?"),
                                       "short": t.get("abbreviation", ""), "logo": t.get("logo")}
        headline = " ".join(n.get("headline", "") for n in comp.get("notes", []))
        is_ncaa = comp.get("tournamentId") == NCAA_TOURNAMENT_ID or "Men's Basketball Championship" in headline
        region = rnd = None
        if is_ncaa:
            parts = [p.strip() for p in headline.split(" - ")]
            region = next((p.replace(" Region", "") for p in parts if p.endswith("Region")), None)
            rnd = parts[-1] if parts else None
        home, away = sides["home"], sides["away"]
        return Game(
            date=date, home_id=home["team"].get("id", ""), away_id=away["team"].get("id", ""),
            home_score=int(home.get("score") or 0), away_score=int(away.get("score") or 0),
            neutral=bool(comp.get("neutralSite")),
            completed=bool(comp.get("status", {}).get("type", {}).get("completed")),
            tournament=is_ncaa, region=region, round=rnd,
            home_seed=(home.get("curatedRank") or {}).get("current") if is_ncaa else None,
            away_seed=(away.get("curatedRank") or {}).get("current") if is_ncaa else None,
        )
