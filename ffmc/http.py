"""Small cached JSON fetcher shared by the Sleeper and ESPN clients."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests


class APIError(RuntimeError):
    pass


class CachedJSON:
    def __init__(self, cache_dir: str | Path | None = ".ffmc_cache", timeout: float = 30.0):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "ffmc-monte-carlo/0.1"

    def get(self, url: str, params: list[tuple[str, str]] | None = None, ttl: float = 0) -> Any:
        """GET ``url`` as JSON, reusing a cached copy younger than ``ttl`` seconds."""
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
            raise APIError(f"GET {url} failed: {exc}") from exc
        if cache_file is not None:
            with cache_file.open("w") as f:
                json.dump(data, f)
        return data
