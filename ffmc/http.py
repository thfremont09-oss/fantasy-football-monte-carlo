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

    def get(self, url: str, params: list[tuple[str, str]] | None = None, ttl: float = 0,
            headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None) -> Any:
        """GET ``url`` as JSON, reusing a cached copy younger than ``ttl`` seconds.

        Requests made with ``cookies`` (someone's login) are never cached to disk.
        """
        cache_file = None
        if self.cache_dir and ttl > 0 and not cookies:
            key = hashlib.sha1((url + json.dumps(params or []) + json.dumps(headers or {}, sort_keys=True)).encode()).hexdigest()
            cache_file = self.cache_dir / f"{key}.json"
            if cache_file.exists() and time.time() - cache_file.stat().st_mtime < ttl:
                with cache_file.open() as f:
                    return json.load(f)
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout, headers=headers, cookies=cookies)
            if resp.status_code >= 400:
                raise APIError(_error_message(resp))
            data = resp.json()
        except requests.RequestException as exc:
            raise APIError(f"GET {url} failed: {exc}") from exc
        except ValueError as exc:
            raise APIError(f"GET {url} returned something that isn't JSON") from exc
        if cache_file is not None:
            with cache_file.open("w") as f:
                json.dump(data, f)
        return data


def _error_message(resp: requests.Response) -> str:
    """Readable error from an HTTP error response (ESPN puts details in JSON)."""
    try:
        body = resp.json()
        details = body.get("details") or []
        if details and details[0].get("type"):
            return f"{resp.status_code} {details[0]['type']}: {details[0].get('message', '')}"
        if body.get("messages"):
            return f"{resp.status_code}: {body['messages'][0]}"
    except ValueError:
        pass
    return f"{resp.status_code} error from {resp.url.split('?')[0]}"
