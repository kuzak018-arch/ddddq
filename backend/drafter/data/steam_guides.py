"""The best Steam Workshop guides for a hero: what Dota's in-game guide panel shows.

A guide is a Workshop item of Dota 2 (appid 570) whose file is a Valve KeyValues text with the
hero, the item build by category (`#DOTA_Item_Build_Starting_Items` and so on, or the author's
own category names) and often the ability order. Discovery needs the user's own Steam Web API
key (free: steamcommunity.com/dev/apikey); without one the module answers "no_key".

  1. `IPublishedFileService/QueryFiles` ranked by trend (votes in the last TREND_DAYS) with the
     hero's English name as search text: up to CANDIDATES items with their file urls, votes and
     subscriptions. Workshop tags are not relied on: which hero a guide is for is read from its
     own file (`"Hero" "npc_dota_hero_antimage"`).
  2. Each candidate's file is downloaded (a few KB) and parsed; guides for another hero, and
     anything that is not a guide, are dropped.
  3. The rest are ranked by votes up (with a penalty for down votes) and subscriptions, a guide
     older than the current patch after the fresh ones; the top SHOWN are kept, with the authors'
     names from `ISteamUser/GetPlayerSummaries`.
The result is cached per hero for CACHE_TTL. Only public HTTPS APIs of Steam are used.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable

import httpx

from .. import config
from . import constants

API = "https://api.steampowered.com"
APPID = 570
TREND_DAYS = 180
CANDIDATES = 20
SHOWN = 3
CACHE_TTL = 24 * 3600
ERROR_TTL = 15 * 60
DIR = config.DATA / "steam_guides"

CATEGORY_RU = {
    "starting": "Старт", "early": "Начало игры", "core": "Основные", "mid": "Середина игры",
    "late": "Поздняя игра", "luxury": "Роскошь", "situational": "По ситуации", "other": "Другое",
    "secret": "Секретная лавка", "support": "Для поддержки", "consumables": "Расходники",
}


class SteamError(RuntimeError):
    pass


# ---------- KeyValues ------------------------------------------------------------------------

_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|([^\s"{}]+)')


def parse_kv(text: str) -> dict:
    """Valve KeyValues to nested dicts; a key that repeats ("item" "item_tango" × 3) becomes a
    list. `//` comments and `[$WIN32]` conditionals are skipped."""
    text = re.sub(r"(?m)//[^\n]*", "", text.lstrip("﻿"))
    tokens = []
    for m in _TOKEN.finditer(text):
        if m.group(2):
            tokens.append(m.group(2))
        else:
            s = m.group(1) if m.group(1) is not None else m.group(3)
            if s.startswith("[$") and s.endswith("]"):
                continue
            tokens.append(("s", s.replace('\\"', '"').replace("\\n", "\n")))

    def block(i: int) -> tuple[dict, int]:
        out: dict = {}
        while i < len(tokens):
            t = tokens[i]
            if t == "}":
                return out, i + 1
            if t == "{":  # a block without a key: skip it
                _, i = block(i + 1)
                continue
            key = t[1]
            if i + 1 >= len(tokens):
                break
            nxt = tokens[i + 1]
            if nxt == "{":
                value, i = block(i + 2)
            elif nxt == "}":
                value, i = "", i + 1
            else:
                value, i = nxt[1], i + 2
            if key in out:
                out[key] = out[key] + [value] if isinstance(out[key], list) else [out[key], value]
            else:
                out[key] = value
        return out, i

    return block(0)[0]


def _find(d, want: Callable[[str, object], bool]):
    """The first (key, value) anywhere in the tree for which `want` is true."""
    if isinstance(d, dict):
        for k, v in d.items():
            if want(k, v):
                return k, v
        for v in d.values():
            r = _find(v, want)
            if r:
                return r
    elif isinstance(d, list):
        for v in d:
            r = _find(v, want)
            if r:
                return r
    return None


def _category(name: str) -> str:
    if not name.startswith("#"):
        return name.strip() or CATEGORY_RU["other"]
    low = name.lower()
    for key, ru in (("start", "starting"), ("early", "early"), ("core", "core"), ("mid", "mid"), ("late", "late"),
                    ("luxury", "luxury"), ("situational", "situational"), ("secret", "secret"),
                    ("support", "support"), ("consum", "consumables")):
        if key in low:
            return CATEGORY_RU[ru]
    return CATEGORY_RU["other"]


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def guide_from_kv(kv: dict) -> dict | None:
    """{hero key, title, items: [{name, items: [item keys]}], abilities: [ability keys]} or None."""
    hero = _find(kv, lambda k, v: k.lower() == "hero" and isinstance(v, str) and v.startswith("npc_dota_hero_"))
    if not hero:
        return None
    hero_key = hero[1].removeprefix("npc_dota_hero_")
    title = _find(kv, lambda k, v: k.lower() == "title" and isinstance(v, str))
    blocks = _find(kv, lambda k, v: k.lower() == "items" and isinstance(v, dict)
                   and any(isinstance(x, dict) for x in v.values()))
    items = []
    for name, cat in (blocks[1].items() if blocks else []):
        if not isinstance(cat, dict):
            continue
        keys = [x.removeprefix("item_") for k, v in cat.items() if k.lower() == "item" for x in _as_list(v)
                if isinstance(x, str) and x.startswith("item_")]
        if keys:
            items.append({"name": _category(name), "items": keys})
    # ability order: a block keyed "1", "2", … whose values are this hero's abilities or talents
    order = _find(kv, lambda k, v: isinstance(v, dict) and "1" in v and isinstance(v["1"], str)
                  and (v["1"].startswith(hero_key) or v["1"].startswith("special_bonus")))
    abilities = []
    if order:
        nums = sorted((int(k), v) for k, v in order[1].items() if k.isdigit() and isinstance(v, str))
        abilities = [v for _, v in nums]
    if not items and not abilities:
        return None
    return {"hero": hero_key, "title": title[1].strip() if title else None, "items": items, "abilities": abilities}


# ---------- Steam ----------------------------------------------------------------------------

def _get(http: httpx.Client, path: str, params: dict) -> dict:
    try:
        r = http.get(path if path.startswith("http") else f"{API}{path}", params=params)
    except httpx.HTTPError as e:
        raise SteamError(f"Steam не отвечает: {e.__class__.__name__}") from e
    if r.status_code in (401, 403):
        raise SteamError("Steam не принял ключ API: проверь его в настройках")
    if r.status_code == 429:
        raise SteamError("Steam просит подождать: слишком много запросов")
    if not r.is_success:
        raise SteamError(f"Steam ответил {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise SteamError("Steam прислал не JSON") from e


def _query(http: httpx.Client, key: str, text: str) -> list[dict]:
    params = {"key": key, "appid": APPID, "query_type": 3, "days": TREND_DAYS, "numperpage": CANDIDATES,
              "search_text": text, "return_vote_data": "true", "return_metadata": "true",
              "return_tags": "true", "return_short_description": "true", "return_previews": "false",
              "strip_description_bbcode": "true"}
    return (_get(http, "/IPublishedFileService/QueryFiles/v1/", params).get("response") or {}).get("publishedfiledetails") or []


def _names(http: httpx.Client, key: str, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    try:
        d = _get(http, "/ISteamUser/GetPlayerSummaries/v2/", {"key": key, "steamids": ",".join(ids)})
    except SteamError:
        return {}
    return {p["steamid"]: p.get("personaname") or "" for p in (d.get("response") or {}).get("players") or []}


def _score(f: dict, patch_ts: int) -> float:
    v = f.get("vote_data") or {}
    up, down = int(v.get("votes_up") or 0), int(v.get("votes_down") or 0)
    subs = int(f.get("subscriptions") or f.get("lifetime_subscriptions") or 0)
    fresh = int(f.get("time_updated") or 0) >= patch_ts
    return (1000 if fresh else 0) + 10 * math.log1p(max(0, up - down)) + math.log1p(subs)


def search(hero_id: int, key: str, http: httpx.Client | None = None) -> list[dict]:
    hero = constants.hero_by_id()[hero_id]
    own = http is None
    http = http or httpx.Client(timeout=15, headers={"User-Agent": config.USER_AGENT}, follow_redirects=True)
    try:
        found = []
        for f in _query(http, key, hero["name"]):
            url = f.get("file_url")
            if not url or int(f.get("result") or 1) != 1:
                continue
            try:
                r = http.get(url)
            except httpx.HTTPError:
                continue
            if not r.is_success or len(r.content) > 512_000:
                continue
            g = guide_from_kv(parse_kv(r.content.decode("utf-8", "replace")))
            if not g or g["hero"] != hero["key"]:
                continue
            v = f.get("vote_data") or {}
            found.append({
                "id": str(f.get("publishedfileid")), "title": g["title"] or f.get("title") or "Руководство",
                "author_id": str(f.get("creator") or ""), "author": None,
                "url": f"https://steamcommunity.com/sharedfiles/filedetails/?id={f.get('publishedfileid')}",
                "subscriptions": int(f.get("subscriptions") or 0),
                "lifetime_subscriptions": int(f.get("lifetime_subscriptions") or 0),
                "votes_up": int(v.get("votes_up") or 0), "votes_down": int(v.get("votes_down") or 0),
                "updated": int(f.get("time_updated") or 0), "description": (f.get("short_description") or "").strip()[:400] or None,
                "items": g["items"], "abilities": g["abilities"], "_score": _score(f, constants.current_patch()["ts"]),
            })
        found.sort(key=lambda g: -g.pop("_score"))
        top = found[:SHOWN]
        names = _names(http, key, [g["author_id"] for g in top if g["author_id"]])
        for g in top:
            g["author"] = names.get(g["author_id"]) or None
        return top
    finally:
        if own:
            http.close()


def for_hero(hero_id: int, refresh: bool = False, now: float | None = None, http: httpx.Client | None = None) -> dict:
    """{"status": "ok" | "no_key" | "error", "error", "guides", "fetched", "patch_ts", "item_names"} with a
    day cache."""
    out = _for_hero(hero_id, refresh, now, http)
    items = constants._load("items")
    keys = {k for g in out["guides"] for c in g["items"] for k in c["items"]}
    return {**out, "item_names": {k: (items.get(k) or {}).get("dname") or k for k in keys}}


def _for_hero(hero_id: int, refresh: bool, now: float | None, http: httpx.Client | None) -> dict:
    now = now or time.time()
    key = config.settings().steam_api_key
    patch_ts = constants.current_patch()["ts"]
    if not key:
        return {"status": "no_key", "error": None, "guides": [], "fetched": None, "patch_ts": patch_ts}
    p = DIR / f"{hero_id}.json"
    try:
        cached = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        cached = None
    if cached and not refresh:
        ttl = CACHE_TTL if cached.get("status") == "ok" else ERROR_TTL
        if now - (cached.get("fetched") or 0) < ttl:
            return {**cached, "patch_ts": patch_ts}
    try:
        out = {"status": "ok", "error": None, "guides": search(hero_id, key, http), "fetched": now}
    except SteamError as e:
        out = {"status": "error", "error": str(e), "guides": (cached or {}).get("guides") or [], "fetched": now}
    DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return {**out, "patch_ts": patch_ts}
