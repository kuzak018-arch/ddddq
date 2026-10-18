"""Hero/item/ability constants, patch dates and icons, cached in data/constants."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from functools import cache
from pathlib import Path

import httpx

from .. import config
from .http import OpenDota

DIR = config.DATA / "constants"
ICONS = config.DATA / "icons"
CDN = "https://cdn.cloudflare.steamstatic.com"
RAW = ("heroes", "items", "abilities", "hero_abilities", "item_ids", "ability_ids")


def _save(name: str, data) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = DIR / f"{name}.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DIR / f"{name}.json")


def _load(name: str):
    return json.loads((DIR / f"{name}.json").read_text(encoding="utf-8"))


def fetch_patches(http: httpx.Client) -> list[dict]:
    patches = http.get(config.VALVE_PATCHES).json()["patches"]
    return [{"name": p["patch_name"], "ts": int(p["patch_timestamp"])} for p in patches]


def build_hero_index() -> list[dict]:
    """Compact hero list for the backend and UI: names (en/ru/slang), roles, talents, active facets."""
    heroes = _load("heroes")
    abil = _load("hero_abilities")
    ru = json.loads((config.SHARED / "hero_names.json").read_text(encoding="utf-8"))
    out, missing = [], []
    for h in sorted(heroes.values(), key=lambda h: h["id"]):
        full = h["name"]  # npc_dota_hero_antimage
        key = full.removeprefix("npc_dota_hero_")
        names = ru.get(key)
        if names is None:
            missing.append(h["localized_name"])
        a = abil.get(full, {})
        out.append({
            "id": h["id"],
            "key": key,
            "name": h["localized_name"],
            "ru": (names or {}).get("ru", []),
            "alias": (names or {}).get("alias", []),
            "attr": h["primary_attr"],
            "attack": h["attack_type"],
            "roles": h.get("roles", []),
            "talents": a.get("talents", []),
            "facets": [
                {"name": f["name"], "title": f.get("title"), "description": f.get("description")}
                for f in a.get("facets", []) if str(f.get("deprecated")) != "true"
            ],
            "abilities": [x for x in a.get("abilities", []) if x != "generic_hidden"],
        })
    if missing:
        print(f"  ! нет русского имени: {', '.join(missing)} — допиши в shared/hero_names.json")
    return out


def download_icons(http: httpx.Client, force: bool = False) -> int:
    heroes, items = _load("heroes"), _load("items")
    jobs: list[tuple[str, Path]] = []
    for h in heroes.values():
        key = h["name"].removeprefix("npc_dota_hero_")
        jobs.append((f"/apps/dota2/images/dota_react/heroes/{key}.png", ICONS / "heroes" / f"{key}.png"))
    for key, it in items.items():
        if it.get("img"):
            jobs.append((it["img"].split("?")[0], ICONS / "items" / f"{key}.png"))
    n = 0
    for path, dest in jobs:
        if dest.exists() and not force:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = http.get(CDN + path)
        if r.is_success and r.headers.get("content-type", "").startswith("image"):
            dest.write_bytes(r.content)
            n += 1
    return n


VALVE_HERO = "https://www.dota2.com/datafeed/herodata?language=russian&hero_id={}"


def fetch_valve_heroes(http: httpx.Client) -> int:
    """Valve's hero feed in Russian: ability descriptions and talents with their numbers."""
    import time
    out = DIR / "valve_heroes"
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for h in _load("heroes").values():
        r = http.get(VALVE_HERO.format(h["id"]))
        if r.is_success:
            heroes = r.json().get("result", {}).get("data", {}).get("heroes", [])
            if heroes:
                (out / f"{h['id']}.json").write_text(json.dumps(heroes[0], ensure_ascii=False), encoding="utf-8")
                n += 1
        time.sleep(0.3)
    return n


def valve_hero(hero_id: int) -> dict | None:
    p = DIR / "valve_heroes" / f"{hero_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def refresh(icons: bool = True) -> None:
    od = OpenDota()
    try:
        for name in RAW:
            _save(name, od.get(f"/constants/{name}"))
            print(f"  ✓ {name}")
    finally:
        od.close()
    with httpx.Client(timeout=30, headers={"User-Agent": config.USER_AGENT}) as http:
        patches = fetch_patches(http)
        _save("patches", patches)
        last = patches[-1]
        print(f"  ✓ патч {last['name']} от {datetime.fromtimestamp(last['ts'], timezone.utc):%Y-%m-%d}")
        index = build_hero_index()
        _save("hero_index", index)
        print(f"  ✓ героев: {len(index)}")
        print(f"  ✓ описания Valve на русском: {fetch_valve_heroes(http)}")
        if icons:
            print(f"  ✓ иконок скачано: {download_icons(http)}")
            from . import abilities  # needs the constants saved above
            abilities._hero.cache_clear()
            print(f"  ✓ иконок способностей: {len(abilities.ensure_icons(abilities.all_ability_keys()))}")
    hero_index.cache_clear()


@cache
def hero_index() -> list[dict]:
    return _load("hero_index")


def hero_by_id() -> dict[int, dict]:
    return {h["id"]: h for h in hero_index()}


def current_patch() -> dict:
    return _load("patches")[-1]
