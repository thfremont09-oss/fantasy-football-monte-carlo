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

from typing import Any

from .http import APIError, CachedJSON

BASE_URL = "https://api.sleeper.app"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")

DAY = 24 * 3600

SleeperError = APIError


class SleeperClient:
    def __init__(self, cache_dir=".ffmc_cache", timeout: float = 30.0):
        self.http = CachedJSON(cache_dir, timeout)

    def _get(self, path: str, params: list[tuple[str, str]] | None = None, ttl: float = 0) -> Any:
        return self.http.get(BASE_URL + path, params, ttl)

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
