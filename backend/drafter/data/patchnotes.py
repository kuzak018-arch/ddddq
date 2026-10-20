"""Patch notes in Russian for the «Патчи» tab.

Source: the game's own localisation file of patch notes, patchnotes_russian.txt, as extracted from
the Dota files by dotabuff/d2vpkr on GitHub (the same file OpenDota's dotaconstants build from). It
is a KeyValues list of lines "DOTA_Patch_<version>_<subject>[_N]" → text, where the subject is a
hero (antimage), a hero's ability (antimage_antimage_mana_break), a hero's talent
(antimage_talent), an item (item_bfury) or a general line. Downloaded at most once a day and kept
in data/patchnotes; offline, the last copy is used. The user's Dota files are never read.
"""

from __future__ import annotations

import html
import re
import threading
import time
from functools import lru_cache

import httpx

from .. import config, kv
from . import abilities, constants

URL = "https://raw.githubusercontent.com/dotabuff/d2vpkr/master/dota/resource/localization/patchnotes/patchnotes_russian.txt"
DIR = config.DATA / "patchnotes"
FILE = DIR / "patchnotes_russian.txt"
TTL = 24 * 3600
_lock = threading.Lock()
_KEY = re.compile(r"^DOTA_Patch_(\d+)_(\d+[a-z]?)_(.+)$")
_TAG = re.compile(r"<[^>]+>")


class PatchNotesError(RuntimeError):
    pass


def _download() -> None:
    try:
        r = httpx.get(URL, timeout=60, follow_redirects=True, headers={"User-Agent": config.USER_AGENT})
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise PatchNotesError(f"не скачал патчноуты: {e}") from e
    if b"DOTA_Patch_" not in r.content[:4000]:
        raise PatchNotesError("вместо патчноутов пришло что-то другое")
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_bytes(r.content)
    tmp.replace(FILE)


def ensure(refresh: bool = False) -> bool:
    """The file is there (fresh, or the last copy when the download fails). Returns whether it is stale."""
    with _lock:
        fresh = FILE.exists() and time.time() - FILE.stat().st_mtime < TTL
        if fresh and not refresh:
            return False
        try:
            _download()
            _parsed.cache_clear()
            return False
        except PatchNotesError:
            if FILE.exists():
                return True
            raise


def clean(text: str) -> str:
    """Valve's lines carry a little HTML (<br>, <font color>): plain text for the UI."""
    text = text.replace("<br>", " ").replace("<br/>", " ")
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub("", text))).strip()


@lru_cache(maxsize=1)
def _parsed(mtime: float) -> dict[str, list[tuple[str, str]]]:
    """version ("7.41f") → its lines in file order: (subject, text)."""
    raw = FILE.read_text(encoding="utf-8-sig", errors="replace")
    tokens = kv.loads(raw)
    tokens = tokens.get("patch", tokens)
    out: dict[str, list[tuple[str, str]]] = {}
    for key, text in tokens.items():
        m = _KEY.match(str(key))
        if not m or not isinstance(text, str):
            continue
        version = f"{m.group(1)}.{m.group(2)}"
        out.setdefault(version, []).append((m.group(3), text))
    return out


def _lines() -> dict[str, list[tuple[str, str]]]:
    return _parsed(FILE.stat().st_mtime)


def version_key(v: str) -> tuple:
    """7.41f > 7.41 > 7.40c: numbers, then the letter."""
    m = re.match(r"^(\d+)\.(\d+)([a-z]?)$", v)
    return (int(m.group(1)), int(m.group(2)), m.group(3)) if m else (0, 0, v)


def _strip_n(rest: str) -> str:
    """«_2», «_3» number the lines of one subject."""
    return re.sub(r"_\d+$", "", rest)


def _match_prefix(rest: str, names) -> str | None:
    best = None
    for n in names:
        if (rest == n or rest.startswith(n + "_")) and (best is None or len(n) > len(best)):
            best = n
    return best


def split(version: str, lines: list[tuple[str, str]], heroes: list[dict], items: dict, abilities: dict) -> dict:
    """One patch's lines grouped as the UI shows them: general (with its section titles), items and
    heroes (own lines, abilities, talents). Lines that are only markup are dropped."""
    hero_keys = {h["key"]: h for h in heroes}
    item_keys = set(items)
    general: list[dict] = []
    by_item: dict[str, list[str]] = {}
    by_hero: dict[str, dict] = {}
    for subject, text in lines:
        note = clean(text)
        if not note:
            continue
        if subject.endswith("_Title") or subject.endswith("_title"):
            general.append({"title": note, "notes": []})
            continue
        if subject.startswith("item_") and (it := _match_prefix(subject[5:], item_keys)):
            by_item.setdefault(it, []).append(note)
            continue
        hero = _match_prefix(subject, hero_keys)
        if hero:
            h = by_hero.setdefault(hero, {"notes": [], "abilities": {}, "talents": []})
            rest = _strip_n(subject[len(hero) + 1:]) if subject != hero else ""
            if rest.isdigit() or not rest:
                h["notes"].append(note)
            elif rest.startswith("talent"):
                h["talents"].append(note)
            else:
                h["abilities"].setdefault(rest, []).append(note)
            continue
        if not general:
            general.append({"title": None, "notes": []})
        general[-1]["notes"].append(note)
    general = [g for g in general if g["notes"]]
    return {
        "version": version,
        "general": general,
        "items": [{"key": k, "name": (items.get(k) or {}).get("dname") or k, "icon": f"/icons/items/{k}.png", "notes": n}
                  for k, n in by_item.items()],
        "heroes": [
            {"id": hero_keys[k]["id"], "key": k, "name": hero_keys[k]["name"], "notes": v["notes"], "talents": v["talents"],
             "abilities": [{"key": a, "name": (abilities.get(a) or {}).get("dname") or a.replace("_", " "), "notes": n}
                           for a, n in v["abilities"].items()]}
            for k, v in by_hero.items()
        ],
    }


def _dates() -> dict[str, int]:
    try:
        return {p["name"]: p["ts"] for p in constants._load("patches")}
    except (OSError, ValueError, KeyError):
        return {}


def patch_list(mine: set[int] | None = None, limit: int = 40) -> dict:
    stale = ensure()
    lines = _lines()
    dates = _dates()
    heroes, items, abil = constants.hero_index(), constants._load("items"), constants._load("abilities")
    out = []
    for v in sorted(lines, key=version_key, reverse=True)[:limit]:
        d = split(v, lines[v], heroes, items, abil)
        touched = {h["id"] for h in d["heroes"]}
        out.append({"version": v, "date": dates.get(v), "heroes": len(d["heroes"]), "items": len(d["items"]),
                    "lines": sum(len(g["notes"]) for g in d["general"]) + sum(len(i["notes"]) for i in d["items"])
                    + sum(len(h["notes"]) + len(h["talents"]) + sum(len(a["notes"]) for a in h["abilities"]) for h in d["heroes"]),
                    "mine": sorted(touched & mine) if mine else []})
    return {"patches": out, "stale": stale, "source": URL}


def patch(version: str, mine: set[int] | None = None) -> dict:
    stale = ensure()
    lines = _lines().get(version)
    if lines is None:
        raise PatchNotesError(f"нет патча {version}")
    out = split(version, lines, constants.hero_index(), constants._load("items"), constants._load("abilities"))
    for h in out["heroes"]:
        # Russian names and cached icons, as in the build view (no downloads here: a patch touches ~100 heroes)
        try:
            ru = abilities.hero_abilities(h["id"], {a["key"] for a in h["abilities"]}, download=False)
        except Exception:  # noqa: BLE001 - a hero the feed has no data for keeps the English names
            ru = {}
        for a in h["abilities"]:
            if a["key"] in ru:
                a["name"] = ru[a["key"]]["name"]
                a["icon"] = ru[a["key"]]["icon"]
    if mine:
        out["heroes"].sort(key=lambda h: h["id"] not in mine)
    out["mine"] = sorted({h["id"] for h in out["heroes"]} & (mine or set()))
    out["date"] = _dates().get(version)
    out["stale"] = stale
    return out
