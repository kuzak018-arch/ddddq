"""HTTP access to OpenDota with a polite rate limit and retries."""

from __future__ import annotations

import time

import httpx

from .. import config


class RateLimited(RuntimeError):
    pass


class OpenDota:
    """Thin OpenDota client. Free tier: 60 req/min, ~3000/day, so we keep >= 1.1 s between calls."""

    def __init__(self, min_interval: float = 1.1, timeout: float = 60) -> None:
        self.min_interval = min_interval
        self._last = 0.0
        key = config.settings().opendota_key
        self._params = {"api_key": key} if key else {}
        self.http = httpx.Client(timeout=timeout, headers={"User-Agent": config.USER_AGENT})
        self.remaining_day: int | None = None

    def close(self) -> None:
        self.http.close()

    def get(self, path: str, params: dict | None = None, retries: int = 5):
        return self._call("GET", path, params, retries)

    def post(self, path: str, params: dict | None = None, retries: int = 2):
        """A parse request (POST /request/{match_id}) counts as 10 calls for OpenDota's rate limit."""
        return self._call("POST", path, params, retries)

    def _call(self, method: str, path: str, params: dict | None, retries: int):
        url = path if path.startswith("http") else f"{config.OPENDOTA}{path}"
        for attempt in range(retries):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.http.request(method, url, params={**self._params, **(params or {})})
            except httpx.TransportError:
                time.sleep(2 ** attempt)
                continue
            if "X-Rate-Limit-Remaining-Day" in r.headers:
                self.remaining_day = int(r.headers["X-Rate-Limit-Remaining-Day"])
            if r.status_code == 429:
                if self.remaining_day == 0:
                    raise RateLimited("дневной лимит OpenDota исчерпан")
                time.sleep(30)
                continue
            if r.status_code >= 500 or (r.status_code == 400 and "timeout" in r.text):
                time.sleep(2 ** attempt * 2)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"OpenDota не ответил после {retries} попыток: {url}")

    def sql(self, query: str) -> list[dict]:
        res = self.get("/explorer", {"sql": query})
        if res.get("err"):
            raise RuntimeError(f"explorer: {res['err']}")
        return res["rows"]
