"""Dota's own interface glyphs, from Valve's CDN like every hero and item icon: the talent tree and
the innate-ability mark. Downloaded once into data/icons/ui; a name not found on the CDN is tried
again after a day (the app draws its own glyph meanwhile)."""

from __future__ import annotations

import json
import time

import httpx

from .. import config

DIR = config.DATA / "icons" / "ui"
HOSTS = ("https://cdn.cloudflare.steamstatic.com", "https://cdn.akamai.steamstatic.com")
# where dota2.com keeps them (several guesses for the innate mark: the site has moved files before)
CANDIDATES = {
    "talent": ["/apps/dota2/images/dota_react/icons/talents.svg"],
    "innate": ["/apps/dota2/images/dota_react/icons/innate_icon.png", "/apps/dota2/images/dota_react/icons/innate.svg",
               "/apps/dota2/images/dota_react/icons/innate.png", "/apps/dota2/images/dota_react/heroes/innate_icon.png"],
}
RETRY_AFTER = 24 * 3600
FAILED = DIR / "failed.json"


def _have(name: str):
    return next((p for p in sorted(DIR.glob(f"{name}.*")) if p.suffix in (".svg", ".png")), None) if DIR.exists() else None


def paths() -> dict[str, str | None]:
    """{name: "/icons/ui/<file>" or None}."""
    return {n: (f"/icons/ui/{p.name}" if (p := _have(n)) else None) for n in CANDIDATES}


def ensure(http: httpx.Client | None = None, now: float | None = None) -> dict[str, str | None]:
    now = now or time.time()
    try:
        failed = json.loads(FAILED.read_text(encoding="utf-8")) if FAILED.exists() else {}
    except (OSError, ValueError):
        failed = {}
    todo = [n for n in CANDIDATES if not _have(n) and (n not in failed or now - failed[n] > RETRY_AFTER)]
    if not todo:
        return paths()
    own = http is None
    http = http or httpx.Client(timeout=8, headers={"User-Agent": config.USER_AGENT}, follow_redirects=True)
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        for name in todo:
            got = False
            for path in CANDIDATES[name]:
                for host in HOSTS:
                    try:
                        r = http.get(host + path)
                    except httpx.HTTPError:
                        continue
                    kind = r.headers.get("content-type", "")
                    ext = ".svg" if "svg" in kind else ".png" if kind.startswith("image") else None
                    if r.is_success and ext and r.content:
                        (DIR / f"{name}{ext}").write_bytes(r.content)
                        got = True
                        break
                if got:
                    break
            if got:
                failed.pop(name, None)
            else:
                failed[name] = now
        FAILED.write_text(json.dumps(failed), encoding="utf-8")
    finally:
        if own:
            http.close()
    return paths()
