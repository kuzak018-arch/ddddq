"""Hero abilities for the build view: Russian name and a short description (Valve's hero feed,
OpenDota's English constants as the fallback), the ability a talent upgrades, and the icons,
kept in a local cache (data/icons/abilities) and downloaded the first time they are needed."""

from __future__ import annotations

import re
import threading
from functools import cache

import httpx

from .. import config
from . import constants

ICONS = constants.ICONS / "abilities"
CDN_PATH = "/apps/dota2/images/dota_react/abilities/{}.png"
ICON_PX = 64
SHORT_DESC = 220  # characters: the tooltip shows the gist, not the whole tooltip text from the game

_lock = threading.Lock()
_failed: set[str] = set()  # icons the CDN does not have: not asked again until restart


def _num(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def _fill(text: str, values: dict[str, list[float]]) -> str:
    """Valve's %name% placeholders -> the ability's numbers ("10 / 20 / 30 / 40"), %% -> %."""
    def sub(m: re.Match) -> str:
        name = m.group(1)
        if not name:
            return "%"
        vals = values.get(name) or values.get(name.removeprefix("bonus_"))
        if not vals:
            return "?"
        uniq = list(dict.fromkeys(vals))
        return " / ".join(_num(v) for v in (uniq if len(uniq) > 1 else vals[:1]))
    return re.sub(r"%(\w*)%", sub, text)


def short_desc(text: str, values: dict[str, list[float]] | None = None) -> str:
    """First paragraph, markup and placeholders cleaned, cut at a sentence end near SHORT_DESC."""
    text = re.sub(r"<[^>]+>", "", text or "").replace("\\n", "\n")
    text = _fill(text, values or {}).split("\n")[0].strip()
    if len(text) <= SHORT_DESC:
        return text
    cut = text[:SHORT_DESC]
    end = max(cut.rfind(". "), cut.rfind("! "))
    return cut[: end + 1] if end > 60 else cut.rstrip() + "…"


def _values(ab: dict) -> dict[str, list[float]]:
    return {sv["name"]: sv["values_float"] for sv in ab.get("special_values", []) if sv.get("values_float")}


@cache
def _hero(hero_id: int) -> dict:
    """{key: {key, name, desc, innate}} for the hero's abilities and the talent -> ability map."""
    vh = constants.valve_hero(hero_id)
    out: dict[str, dict] = {}
    talent_ability: dict[str, str] = {}
    if vh:
        for ab in vh["abilities"] + vh.get("facet_abilities", []):
            out[ab["name"]] = {"key": ab["name"], "name": ab.get("name_loc") or ab["name"],
                               "desc": short_desc(ab.get("desc_loc", ""), _values(ab)),
                               "innate": str(ab.get("ability_is_innate")) == "True"}
            # a unique talent is stored as a bonus on the ability it upgrades
            for sv in ab.get("special_values", []):
                for b in sv.get("bonuses", []):
                    if str(b.get("name", "")).startswith("special_bonus"):
                        talent_ability.setdefault(b["name"], ab["name"])
    else:
        od = constants._load("abilities")
        key = constants.hero_by_id()[hero_id]["key"]
        names = constants._load("hero_abilities").get(f"npc_dota_hero_{key}", {}).get("abilities", [])
        for k in names:
            a = od.get(k) or {}
            if a.get("dname"):
                out[k] = {"key": k, "name": a["dname"], "desc": short_desc(a.get("desc", "")), "innate": False}
    return {"abilities": out, "talent_ability": talent_ability}


def hero_abilities(hero_id: int, keys: set[str] | None = None, download: bool = True) -> dict[str, dict]:
    """Ability info with an icon path for the build view; `keys` limits it to what the build shows."""
    abilities = _hero(hero_id)["abilities"]
    if keys is not None:
        abilities = {k: v for k, v in abilities.items() if k in keys}
    have = ensure_icons(abilities, download)
    return {k: {**v, "icon": f"/icons/abilities/{k}.png" if k in have else None} for k, v in abilities.items()}


def talent_ability(hero_id: int, talent: str) -> str | None:
    return _hero(hero_id)["talent_ability"].get(talent)


def _shrink(png: bytes) -> bytes:
    """The CDN serves 128 px; the build view shows 20-30 px, so 64 px is plenty even at 200%
    display scaling and keeps the cache (and the installer) ~4 times smaller."""
    try:
        import cv2
        import numpy as np
        im = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
        if im is None or im.shape[0] <= ICON_PX:
            return png
        ok, out = cv2.imencode(".png", cv2.resize(im, (ICON_PX, ICON_PX), interpolation=cv2.INTER_AREA),
                               [cv2.IMWRITE_PNG_COMPRESSION, 9])
        return out.tobytes() if ok else png
    except Exception:
        return png


def ensure_icons(keys, download: bool = True) -> set[str]:
    """Download missing ability icons (a few per hero, once); returns the keys that have an icon."""
    keys = list(keys)
    missing = [k for k in keys if not (ICONS / f"{k}.png").exists() and k not in _failed] if download else []
    if missing:
        with _lock, httpx.Client(timeout=6, headers={"User-Agent": config.USER_AGENT}) as http:
            ICONS.mkdir(parents=True, exist_ok=True)
            for k in missing:
                dest = ICONS / f"{k}.png"
                if dest.exists():
                    continue
                try:
                    r = http.get(constants.CDN + CDN_PATH.format(k))
                except httpx.HTTPError:
                    _failed.add(k)
                    continue
                if r.is_success and r.headers.get("content-type", "").startswith("image"):
                    dest.write_bytes(_shrink(r.content))
                else:
                    _failed.add(k)
    return {k for k in keys if (ICONS / f"{k}.png").exists()}


def all_ability_keys() -> list[str]:
    """Every hero's abilities (for a full icon download after a patch)."""
    keys: list[str] = []
    for h in constants.hero_by_id():
        keys += list(_hero(h)["abilities"])
    return keys
