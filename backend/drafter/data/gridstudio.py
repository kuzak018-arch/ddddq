"""GridStudio's workshop (gridstudio.me) inside the app: grids, ready-made arts and menu backgrounds.

Their catalog has an open API (the same server code is in github.com/linsisss/dota2-grid-toolkit,
server/catalog-api.mjs, GPL-3.0): GET /api/catalog/works (grids), /works/<id>/download (the grid as
hero_grid_config.json), /backgrounds (menu backgrounds) with /backgrounds/<id>/poster.jpg,
preview.webm and video.webm, /arts (the arts library) and /preview/work/<id>.jpg (a grid's
picture). By the workshop's rules a published grid or art may be downloaded, changed and posted
again by anyone; the app still shows the author and links to the work.

Everything goes through this backend: the app window may load pictures and videos only from it
(CSP), and the files are cached, so the workshop is asked as little as possible. Works tagged
18+ are left out.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import httpx

from .. import config

BASE = "https://gridstudio.me/api/catalog"
SITE = "https://gridstudio.me"
DIR = config.DATA / "gridstudio"
LIST_TTL = 10 * 60
ARTS_TTL = 60 * 60
ADULT = "18+"
SORTS = {"new": None, "popular": "popular", "week": "week", "downloads": "downloads"}
GRID_TAGS = ["Аниме", "Милота", "Рамки", "С упором на героя", "Мемы", "Dead inside"]
BACKGROUND_TAGS = ["Аниме", "Dota 2", "Игры", "Милота", "Мемы", "Dead inside", "Природа", "Космос", "Абстракция"]
ASPECTS = ["16:9", "16:10", "21:9", "4:3"]
MAX_FILE = 40_000_000
_WORK_ID = re.compile(r"^[0-9a-f-]{36}$")
_BG_ID = re.compile(r"^[1-9]\d{0,12}$")
BG_FILES = {"poster.jpg": "image/jpeg", "preview.webm": "video/webm", "video.webm": "video/webm"}


class WorkshopError(RuntimeError):
    pass


def _get(path: str, params: dict | None = None) -> httpx.Response:
    try:
        r = httpx.get(BASE + path, params=params, timeout=30, follow_redirects=True,
                      headers={"User-Agent": f"{config.USER_AGENT} (Dota Drafter; workshop browser)"})
    except httpx.HTTPError as e:
        raise WorkshopError(f"GridStudio не ответил: {e}") from e
    if r.status_code == 429:
        raise WorkshopError("GridStudio просит подождать: слишком много запросов, попробуй через минуту")
    if r.status_code == 404:
        raise WorkshopError("в мастерской этого больше нет (удалено или скрыто)")
    if r.status_code >= 400:
        try:
            msg = r.json().get("error") or r.text[:200]
        except ValueError:
            msg = r.text[:200]
        raise WorkshopError(f"GridStudio: {msg}")
    return r


def _cache_path(kind: str, key: str) -> Path:
    return DIR / kind / hashlib.sha1(key.encode()).hexdigest()[:20]


def _cached_json(kind: str, key: str, ttl: float, fetch):
    p = _cache_path(kind, key).with_suffix(".json")
    if p.exists() and time.time() - p.stat().st_mtime < ttl:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    try:
        data = fetch()
    except WorkshopError:
        if p.exists():   # offline or busy: the last answer is better than nothing
            return {**json.loads(p.read_text(encoding="utf-8")), "stale": True}
        raise
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _adult(item: dict) -> bool:
    return ADULT in (item.get("tags") or [])


def _author(item: dict) -> str:
    return (item.get("creator") or {}).get("name") or item.get("author") or "аноним"


def _params(q: str, tag: str, sort: str, page: int, **extra) -> dict:
    p = {"q": q.strip()[:80] or None, "tag": tag or None, "sort": SORTS.get(sort), "page": max(0, min(1000, page)), **extra}
    return {k: v for k, v in p.items() if v not in (None, "")}


def grids(q: str = "", tag: str = "", sort: str = "popular", page: int = 0) -> dict:
    if tag and tag not in GRID_TAGS:
        raise WorkshopError("неизвестный тег")
    params = _params(q, tag, sort, page)
    raw = _cached_json("lists", "works?" + json.dumps(params, sort_keys=True), LIST_TTL, lambda: _get("/works", params).json())
    items = [{"id": w["id"], "revision": w.get("revision"), "title": w.get("title") or "Без названия", "author": _author(w),
              "credit": w.get("credit") or "", "tags": w.get("tags") or [], "likes": w.get("likes", 0),
              "downloads": w.get("downloads", 0), "stats": w.get("stats") or {}, "updated": w.get("updated"),
              "url": f"{SITE}/workshop?id={w['id']}"}
             for w in raw.get("items") or [] if not _adult(w)]
    return {"items": items, "total": raw.get("total", len(items)), "page": raw.get("page", page), "stale": raw.get("stale", False)}


def grid_file(work_id: str) -> dict:
    """The grid as Dota's hero_grid_config.json (the workshop counts it as a download, as on the site)."""
    if not _WORK_ID.match(work_id):
        raise WorkshopError("неверный номер сетки")
    data = _cached_json("grids", work_id, 24 * 3600, lambda: _get(f"/works/{work_id}/download").json())
    if not isinstance(data, dict) or not isinstance(data.get("configs"), list):
        raise WorkshopError("GridStudio прислал не файл сеток")
    return data


def backgrounds(q: str = "", tag: str = "", aspect: str = "", sort: str = "popular", page: int = 0) -> dict:
    if tag and tag not in BACKGROUND_TAGS:
        raise WorkshopError("неизвестный тег")
    if aspect and aspect not in ASPECTS:
        raise WorkshopError("неизвестный формат экрана")
    params = _params(q, tag, sort, page, aspect=aspect or None)
    raw = _cached_json("lists", "bg?" + json.dumps(params, sort_keys=True), LIST_TTL, lambda: _get("/backgrounds", params).json())
    items = [{"id": b["id"], "title": b.get("title") or "Без названия", "author": _author(b), "credit": b.get("credit") or "",
              "tags": b.get("tags") or [], "aspect": b.get("aspect"), "seconds": b.get("seconds"), "bytes": b.get("bytes"),
              "likes": b.get("likes", 0), "downloads": b.get("downloads", 0), "has_preview": bool(b.get("preview")),
              "url": f"{SITE}/background?background={b['id']}"}
             for b in raw.get("items") or [] if not _adult(b)]
    return {"items": items, "total": raw.get("total", len(items)), "aspects": raw.get("aspects") or {}, "stale": raw.get("stale", False)}


def arts() -> dict:
    raw = _cached_json("lists", "arts", ARTS_TTL, lambda: _get("/arts").json())
    items = [{"id": a["id"], "name": a.get("name") or "Арт", "category": a.get("category") or "", "author": a.get("author") or "",
              "credit": a.get("credit") or "", "text": a.get("text") or "", "rows": a.get("rows")}
             for a in raw.get("items") or [] if (a.get("category") or "") != ADULT]
    return {"items": items, "stale": raw.get("stale", False)}


def _file(kind: str, path: str, key: str) -> Path:
    dest = _cache_path(kind, key)
    if dest.exists():
        return dest
    r = _get(path)
    if len(r.content) > MAX_FILE:
        raise WorkshopError("файл в мастерской слишком большой")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    return dest


def background_file(bg_id: str, name: str) -> tuple[Path, str]:
    """A background's poster, short preview or full video, kept for good (they never change)."""
    if not _BG_ID.match(bg_id) or name not in BG_FILES:
        raise WorkshopError("неверный файл фона")
    return _file("backgrounds", f"/backgrounds/{bg_id}/{name}", f"{bg_id}/{name}"), BG_FILES[name]


def grid_preview(work_id: str, revision: str = "") -> Path:
    if not _WORK_ID.match(work_id):
        raise WorkshopError("неверный номер сетки")
    return _file("previews", f"/preview/work/{work_id}.jpg", f"{work_id}@{revision}")


def meta() -> dict:
    return {"grid_tags": GRID_TAGS, "background_tags": BACKGROUND_TAGS, "aspects": ASPECTS, "sorts": list(SORTS), "site": SITE}
