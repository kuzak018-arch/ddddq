"""Hero threat tags for item recommendations.

Tags are detected from the current patch's ability data (damage type, description text,
attributes), so reworks are picked up automatically, then corrected by hand in
shared/hero_tags_manual.yaml (`add` / `remove`). Result: shared/hero_tags.json.
"""

from __future__ import annotations

import json
import re
from functools import cache

import yaml

from .. import config
from ..data import constants

TAGS = {
    "magic_burst": "много магического урона",
    "pure_damage": "чистый урон",
    "illusions": "иллюзии",
    "summons": "призванные существа",
    "invis": "невидимость",
    "heal": "лечение и регенерация",
    "evasion": "уклонение",
    "silence": "сайленсы",
    "targeted_disable": "точечный контроль",
    "bkb_pierce": "контроль сквозь BKB",
    "mobility": "мобильность, сложно поймать",
    "passives": "сильные пассивки (Break)",
    "physical_burst": "физический урон",
    "armor_reduction": "снижение брони",
    "saves": "сейвы союзников",
}

_DISABLE = re.compile(r"\b(stun|stuns|stunned|stunning|hex|hexes|root|roots|rooted|taunt|sleep|cyclone|banish|fear)", re.I)


@cache
def _raw():
    return constants._load("abilities"), constants._load("hero_abilities")


def _flat(xs):
    for x in xs:
        yield from (_flat(x) if isinstance(x, list) else [x])


def _abilities(hero_full: str) -> list[dict]:
    a, ha = _raw()
    out = []
    for key in _flat(ha.get(hero_full, {}).get("abilities", [])):
        x = a.get(key)
        if key == "generic_hidden" or not x:
            continue
        beh = x.get("behavior") or []
        beh = [beh] if isinstance(beh, str) else beh
        attrib_keys = " ".join(at.get("key", "") for at in x.get("attrib", []) or [])
        out.append({"key": key, "behavior": beh, "dmg_type": x.get("dmg_type"),
                    "bkbpierce": x.get("bkbpierce"), "desc": x.get("desc") or "", "attrib": attrib_keys})
    return out


def auto_tags(hero_full: str, roles: list[str], attack: str) -> dict[str, float]:
    """Tag -> strength 0..1 from ability data."""
    ab = _abilities(hero_full)
    t: dict[str, float] = {}

    def add(tag, v):
        t[tag] = min(1.0, t.get(tag, 0) + v)

    for x in ab:
        d, k, beh = x["desc"].lower(), x["attrib"].lower(), x["behavior"]
        dealing = "damage" in d or "damage" in k
        if x["dmg_type"] == "Magical" and dealing:
            add("magic_burst", 0.35)
        if x["dmg_type"] == "Pure" and dealing:
            add("pure_damage", 0.5)
        if re.search(r"\b(creates?|summons?|conjures?)\b[^.]*\billusions?\b", d) or "illusion_damage" in k \
                or re.search(r"\billusions? of (himself|herself|itself)", d):
            add("illusions", 0.6)
        if re.search(r"\b(summons?|spawns?|creates?)\b[^.]*\b(unit|units|spiderling|golem|wolves|wolf|treants?|"
                     r"skeletons?|eidolons?|serpent wards?|familiars?|spirits?|bear|forge spirits?|zombies?|boar|hawk)\b", d):
            add("summons", 0.5)
        if re.search(r"\b(becomes?|turns?|turning|becoming|go|goes)\b[^.]*\binvisib", d) or "fade_time" in k \
                or "invis" in x["key"]:
            add("invis", 0.7)
        if re.search(r"\b(heals?|healing|restores? (?:\w+ )?health|lifesteal|health regen)", d) and \
                "enemy" not in d.split("heal")[0][-40:]:
            add("heal", 0.35)
        if "evasion" in d or "evasion" in k or "miss" in k:
            add("evasion", 0.5)
        if re.search(r"\bsilenc", d):
            add("silence", 0.5)
        if "Unit Target" in beh and _DISABLE.search(d):
            add("targeted_disable", 0.5)
        if x["bkbpierce"] == "Yes" and _DISABLE.search(d):
            add("bkb_pierce", 0.5)
        if re.search(r"\b(blinks?|teleports?|leaps?|dashes|jumps?|charges?|rushes)\b", d) and "Passive" not in beh:
            add("mobility", 0.35)
        if re.search(r"armor (reduction|by)|reduc\w* [^.]{0,30}armor|-\d+ armor|minus armor", d) or "armor_reduction" in k:
            add("armor_reduction", 0.5)
    if "Carry" in roles and attack:
        add("physical_burst", 0.5 if attack == "Melee" else 0.4)
    if "Escape" in roles:
        add("mobility", 0.3)
    return {k: round(v, 2) for k, v in t.items() if v >= 0.3}


# Detected from ability data well enough; the rest are hand-labelled (auto detection was too noisy).
AUTO = {"magic_burst": 0.7, "pure_damage": 0.5, "physical_burst": 0.4, "armor_reduction": 0.5}  # tag -> min strength


def build() -> dict[str, dict[str, float]]:
    manual = yaml.safe_load((config.SHARED / "hero_tags_manual.yaml").read_text(encoding="utf-8")) or {}
    keys = {h["key"] for h in constants.hero_index()}
    for tag, heroes in manual.items():
        if tag not in TAGS or tag in AUTO:
            raise ValueError(f"hero_tags_manual.yaml: тег {tag} неизвестен или размечается автоматически")
        if bad := set(heroes) - keys:
            raise ValueError(f"hero_tags_manual.yaml, {tag}: нет таких героев {bad}")
    out = {}
    for h in constants.hero_index():
        auto = auto_tags(f"npc_dota_hero_{h['key']}", h["roles"], h["attack"])
        tags = {t: v for t, v in auto.items() if t in AUTO and v >= AUTO[t]}
        # 'Carry' in OpenDota roles also marks spell carries (Zeus, Necrophos): not physical threats
        if h["attr"] == "int" or tags.get("magic_burst", 0) >= 1.0:
            tags.pop("physical_burst", None)
        for tag, heroes in manual.items():
            if h["key"] in heroes:
                tags[tag] = float(heroes[h["key"]])
        out[h["key"]] = dict(sorted(tags.items()))
    (config.SHARED / "hero_tags.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def load() -> dict[str, dict[str, float]]:
    return json.loads((config.SHARED / "hero_tags.json").read_text(encoding="utf-8"))
