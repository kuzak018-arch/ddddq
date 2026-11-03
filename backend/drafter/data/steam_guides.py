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
CACHE_VERSION = 4
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


def _walk(d, path=()):
    """Every (path of keys, key, value) in the tree, values of lists included."""
    if isinstance(d, dict):
        for k, v in d.items():
            for x in _as_list(v):
                yield path, str(k), x
                if isinstance(x, (dict, list)):
                    yield from _walk(x, path + (str(k),))
    elif isinstance(d, list):
        for x in d:
            if isinstance(x, (dict, list)):
                yield from _walk(x, path)


def _hero_of(kv, known: dict[str, str] | None) -> str | None:
    """The hero key a guide is for: a "hero" field, or any value naming an npc_dota_hero_…,
    or a "hero" field holding a key / an English name / an id the app knows."""
    for _, k, v in _walk(kv):
        if isinstance(v, str) and v.startswith("npc_dota_hero_"):
            return v.removeprefix("npc_dota_hero_")
    if known:
        for _, k, v in _walk(kv):
            if k.lower() in ("hero", "heroname", "hero_name", "heroid", "hero_id") and isinstance(v, (str, int)):
                hit = known.get(str(v).strip().lower())
                if hit:
                    return hit
    return None


def guide_from_kv(kv: dict, hero_hint: str | None = None, known: dict[str, str] | None = None) -> dict | None:
    """{hero key, title, items: [{name, items: [item keys]}], abilities: [ability keys]} or None.
    `hero_hint`: the hero the guide's own title names, when the file itself doesn't say;
    `known`: hero keys, English names and ids (lower case) -> hero key."""
    hero_key = _hero_of(kv, known) or hero_hint
    if not hero_key:
        return None
    title = _find(kv, lambda k, v: k.lower() == "title" and isinstance(v, str))
    items = []
    blocks = _find(kv, lambda k, v: k.lower() == "items" and isinstance(v, dict)
                   and any(isinstance(x, dict) for x in v.values()))
    for name, cat in (blocks[1].items() if blocks else []):
        if not isinstance(cat, dict):
            continue
        keys = [x.removeprefix("item_") for k, v in cat.items() if k.lower() == "item" for x in _as_list(v)
                if isinstance(x, str) and x.startswith("item_")]
        if keys:
            items.append({"name": _category(name), "items": keys})
    if not items:
        # any other layout: the item_… values, grouped by the block they are in
        groups: dict[tuple, list[str]] = {}
        for path, k, v in _walk(kv):
            if isinstance(v, str) and v.startswith("item_") and not v.startswith("item_recipe"):
                groups.setdefault(path, []).append(v.removeprefix("item_"))
        for path, keys in groups.items():
            name = next((p for p in reversed(path) if not p.isdigit() and p.lower() not in ("item", "items")), "")
            items.append({"name": _category(name) if name else CATEGORY_RU["other"], "items": keys})
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


def parse_binary_kv(data: bytes) -> dict:
    """Valve's binary KeyValues: a type byte, a 0-terminated name, then the value
    (0 = a block till 8, 1 = string, 2 = int32, 3 = float32, 4 = pointer, 5 = wide string, 6 = colour, 7 = uint64)."""
    import struct
    pos = 0

    def cstr() -> str:
        nonlocal pos
        end = data.index(b"\x00", pos)
        out = data[pos:end].decode("utf-8", "replace")
        pos = end + 1
        return out

    def block() -> dict:
        nonlocal pos
        out: dict = {}
        while pos < len(data):
            t = data[pos]
            pos += 1
            if t in (8, 11):
                return out
            key = cstr()
            if t == 0:
                v = block()
            elif t == 1:
                v = cstr()
            elif t in (2, 4, 6):
                v = str(struct.unpack_from("<i", data, pos)[0])
                pos += 4
            elif t == 3:
                v = str(struct.unpack_from("<f", data, pos)[0])
                pos += 4
            elif t == 7:
                v = str(struct.unpack_from("<Q", data, pos)[0])
                pos += 8
            else:
                raise ValueError(f"тип {t}")
            if key in out:
                out[key] = out[key] + [v] if isinstance(out[key], list) else [out[key], v]
            else:
                out[key] = v
        return out

    return block()


def decode_file(content: bytes) -> tuple[str, dict | None]:
    """(kind, tree) of a downloaded Workshop file: text KeyValues, binary KeyValues, JSON, or a zip
    with one of those inside; other kinds (an image) give no tree."""
    import io
    import zipfile
    if content[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                for name in z.namelist():
                    if name.lower().endswith((".txt", ".vdf", ".json", ".kv", ".bin")) and z.getinfo(name).file_size < 512_000:
                        kind, tree = decode_file(z.read(name))
                        if tree:
                            return f"zip/{kind}", tree
        except zipfile.BadZipFile:
            pass
        return "zip", None
    if content[:3] in (b"\x89PN", b"\xff\xd8\xff") or content[:4] in (b"GIF8", b"RIFF"):
        return "image", None
    head = content.lstrip(b"\xef\xbb\xbf \t\r\n")[:1]
    if head in (b"{", b"["):
        try:
            tree = json.loads(content.decode("utf-8"))
            return "json", tree if isinstance(tree, dict) else {"root": tree}
        except ValueError:
            pass
    if content[:1] == b"\x00" or b"\x00" in content[:64]:
        try:
            return "binary", parse_binary_kv(content)
        except (ValueError, IndexError):
            return "binary?", None
    text = content.decode("utf-8", "replace")
    tree = parse_kv(text)
    return ("text" if tree else "text?"), tree


SAMPLES = 4


def fid_of(f: dict) -> str:
    return str(f.get("publishedfileid") or "x")


def _keep_sample(fid: str, kind: str, content: bytes) -> None:
    """The first downloaded files are kept as they are (data/steam_guides/samples), so a format the
    reader doesn't know can be looked at."""
    d = DIR / "samples"
    try:
        d.mkdir(parents=True, exist_ok=True)
        if len(list(d.iterdir())) < SAMPLES:
            (d / f"{fid}.{kind.replace('/', '-').replace('?', '')}").write_bytes(content[:256_000])
    except OSError:
        pass


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


# Steam's EPublishedFileInfoMatchingFileType: Dota's in-game guides are not «items» to Steam's
# default filter but game-managed items (20); integrated guides (12) and plain items (0) are tried too
FILETYPES = (20, 12, 0)


def _query(http: httpx.Client, key: str, text: str, filetype: int, query_type: int = 3) -> list[dict]:
    params = {"key": key, "appid": APPID, "query_type": query_type, "days": TREND_DAYS, "numperpage": CANDIDATES,
              "filetype": filetype, "search_text": text, "return_vote_data": "true", "return_metadata": "true",
              "return_tags": "true", "return_short_description": "true", "return_previews": "false",
              "strip_description_bbcode": "true"}
    return (_get(http, "/IPublishedFileService/QueryFiles/v1/", params).get("response") or {}).get("publishedfiledetails") or []


def _file_url(http: httpx.Client, key: str, f: dict) -> str | None:
    """The guide file's address: given directly, or asked for by its content handle."""
    if f.get("file_url"):
        return f["file_url"]
    ugc = f.get("hcontent_file")
    if not ugc or str(ugc) == "0":
        return None
    try:
        d = _get(http, "/ISteamRemoteStorage/GetUGCFileDetails/v1/", {"key": key, "appid": APPID, "ugcid": ugc})
    except SteamError:
        return None
    return (d.get("data") or {}).get("url") or None


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
        diag = {"queried": 0, "with_file": 0, "downloaded": 0, "guides": 0, "this_hero": 0}
        seen: set[str] = set()
        files = []
        for filetype in FILETYPES:
            for text in dict.fromkeys((hero["name"], f"npc_dota_hero_{hero['key']}")):
                for f in _query(http, key, text, filetype):
                    fid = str(f.get("publishedfileid"))
                    if fid not in seen and int(f.get("result") or 1) == 1:
                        seen.add(fid)
                        files.append(f)
            if len(files) >= CANDIDATES:
                break
        diag["queried"] = len(files)
        known = {}
        for hid, h in constants.hero_by_id().items():
            for k in (h["key"], h["name"], hid):
                known[str(k).lower()] = h["key"]
        for f in files[:CANDIDATES * 2]:
            url = _file_url(http, key, f)
            if not url:
                continue
            diag["with_file"] += 1
            try:
                r = http.get(url)
            except httpx.HTTPError:
                continue
            if not r.is_success or len(r.content) > 512_000:
                continue
            diag["downloaded"] += 1
            kind, tree = decode_file(r.content)
            diag.setdefault("kinds", {})[kind] = diag.get("kinds", {}).get(kind, 0) + 1
            _keep_sample(fid_of(f), kind, r.content)
            hint = hero["key"] if hero["name"].lower() in str(f.get("title") or "").lower() else None
            g = guide_from_kv(tree, hint, known) if tree else None
            if not g:
                continue
            diag["guides"] += 1
            if g["hero"] != hero["key"]:
                continue
            diag["this_hero"] += 1
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
        search.diag = diag
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
    if cached and cached.get("v") != CACHE_VERSION:
        cached = None          # made by an older search (it found nothing for anybody): ask again
    if cached and not refresh:
        ttl = CACHE_TTL if cached.get("status") == "ok" else ERROR_TTL
        if now - (cached.get("fetched") or 0) < ttl:
            return {**cached, "patch_ts": patch_ts}
    try:
        guides = search(hero_id, key, http)
        out = {"status": "ok", "error": None, "guides": guides, "fetched": now, "diag": getattr(search, "diag", None),
               "v": CACHE_VERSION}
    except SteamError as e:
        out = {"status": "error", "error": str(e), "guides": (cached or {}).get("guides") or [], "fetched": now,
               "v": CACHE_VERSION}
    DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return {**out, "patch_ts": patch_ts}
