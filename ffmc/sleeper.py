"""Thin client for the free, public Sleeper API (no API key required).

Docs: https://docs.sleeper.com/

Endpoints used:
  /v1/state/nfl                         current season / week
  /v1/players/nfl                       full player database (~5 MB, cached for a day)
  /projections/nfl/{season}/{week}      weekly stat projections
  /stats/nfl/{season}/{week}            actual weekly stats (used to estimate variance)
  /v1/user/{username}                   user lookup
  /v1/league/{id}[/rosters|/users|/matchups/{week}]
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.sleeper.app"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")

DAY = 24 * 3600


class SleeperError(RuntimeError):
    pass


class SleeperClient:
    def __init__(self, cache_dir: str | os.PathLike | None = ".ffmc_cache", timeout: float = 30.0):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "ffmc-monte-carlo/0.1"

    # ------------------------------------------------------------------ http
    def _get(self, path: str, params: list[tuple[str, str]] | None = None, ttl: float = 0) -> Any:
        url = BASE_URL + path
        cache_file = None
        if self.cache_dir and ttl > 0:
            key = hashlib.sha1((url + json.dumps(params or [])).encode()).hexdigest()
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists() and time.time() - cache_file.stat().st_mtime < ttl:
                with cache_file.open() as f:
                    return json.load(f)
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise SleeperError(f"GET {url} failed: {exc}") from exc
        if cache_file is not None:
            with cache_file.open("w") as f:
                json.dump(data, f)
        return data

    # ------------------------------------------------------------- endpoints
    def state(self) -> dict:
        return self._get("/v1/state/nfl", ttl=600)

    def players(self) -> dict[str, dict]:
        return self._get("/v1/players/nfl", ttl=DAY)

    def projections(self, season: int, week: int, season_type: str = "regular") -> dict[str, dict]:
        params = [("season_type", season_type)] + [("position[]", p) for p in POSITIONS]
        try:
            data = self._get(f"/projections/nfl/{season}/{week}", params, ttl=3600)
        except SleeperError:
            data = self._get(f"/v1/projections/nfl/{season_type}/{season}/{week}", ttl=3600)
        return normalize_weekly(data)

    def stats(self, season: int, week: int, season_type: str = "regular") -> dict[str, dict]:
        params = [("season_type", season_type)] + [("position[]", p) for p in POSITIONS]
        try:
            data = self._get(f"/stats/nfl/{season}/{week}", params, ttl=7 * DAY)
        except SleeperError:
            data = self._get(f"/v1/stats/nfl/{season_type}/{season}/{week}", ttl=7 * DAY)
        return normalize_weekly(data)

    def user(self, username_or_id: str) -> dict:
        data = self._get(f"/v1/user/{username_or_id}", ttl=DAY)
        if not data:
            raise SleeperError(f"Sleeper user '{username_or_id}' not found")
        return data

    def league(self, league_id: str) -> dict:
        return self._get(f"/v1/league/{league_id}", ttl=3600)

    def league_users(self, league_id: str) -> list[dict]:
        return self._get(f"/v1/league/{league_id}/users", ttl=3600)

    def league_rosters(self, league_id: str) -> list[dict]:
        return self._get(f"/v1/league/{league_id}/rosters", ttl=300)

    def matchups(self, league_id: str, week: int) -> list[dict]:
        return self._get(f"/v1/league/{league_id}/matchups/{week}", ttl=300)


def normalize_weekly(data: Any) -> dict[str, dict]:
    """Normalize projection/stat payloads to {player_id: {"stats", "team", "opponent"}}.

    Sleeper returns either a list of rows (``/projections``, ``/stats``) or a
    dict of player_id -> stats (legacy ``/v1`` endpoints).
    """
    out: dict[str, dict] = {}
    if isinstance(data, list):
        for row in data:
            pid = str(row.get("player_id", ""))
            if not pid:
                continue
            player = row.get("player") or {}
            out[pid] = {
                "stats": row.get("stats") or {},
                "team": row.get("team") or player.get("team"),
                "opponent": row.get("opponent"),
            }
    elif isinstance(data, dict):
        for pid, stats in data.items():
            out[str(pid)] = {"stats": stats or {}, "team": None, "opponent": None}
    return out
