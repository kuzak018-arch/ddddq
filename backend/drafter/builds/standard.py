"""The popular build for a hero on a position and rank bracket, assembled from Stratz data:
starting items, boots, early/core/situational items with timings and winrates,
ability max order and talent picks."""

from __future__ import annotations

import re
from collections import defaultdict
from functools import cache

from ..data import constants, stratz

START_MIN_SHARE = 0.35     # a starting item is in the build if this share of players buy it
CORE_MIN_SHARE = 0.25
SITUATIONAL_MIN_SHARE = 0.03
EARLY_BEFORE_MIN = 14      # finished before this minute on average and cheap -> early item
EARLY_MAX_COST = 2500
SKIP_ITEMS = {"tpscroll", "ward_observer", "ward_sentry", "ward_dispenser", "smoke_of_deceit", "dust", "tango",
              "flask", "clarity", "enchanted_mango", "faerie_fire", "blood_grenade", "aghanims_shard_roshan",
              "cheese", "refresher_shard", "aegis"}


@cache
def _maps():
    item_ids = {int(k): v for k, v in constants._load("item_ids").items() if k.isdigit()}
    # a few keys are "id1,id2" (shared abilities): map each id
    ability_ids = {int(i): v for k, v in constants._load("ability_ids").items() for i in k.split(",") if i.isdigit()}
    return item_ids, ability_ids, constants._load("items"), constants._load("abilities")


def _item(item_id: int) -> dict | None:
    item_ids, _, items, _ = _maps()
    key = item_ids.get(item_id)
    if not key or key not in items:
        return None
    return {"key": key, "name": items[key]["dname"], "cost": items[key].get("cost") or 0}


def _wr(w, n):
    return w / n if n else None


def _num(v: float) -> str:
    return f"{v:g}"


def talent_text(key: str, hero_id: int) -> str:
    """Russian talent text from Valve's feed with {s:...} filled in. Generic talents carry their own
    value; unique ones are stored as a bonus on the ability they modify."""
    vh = constants.valve_hero(hero_id)
    if not vh:
        return _maps()[3].get(key, {}).get("dname") or key
    talent = next((t for t in vh["talents"] if t["name"] == key), None)
    if not talent:
        return key
    own = {sv["name"]: sv["values_float"] for sv in talent.get("special_values", []) if sv.get("values_float")}
    bonus = None
    for ab in vh["abilities"] + vh.get("facet_abilities", []):
        for sv in ab.get("special_values", []):
            for b in sv.get("bonuses", []):
                if b.get("name") == key:
                    bonus = b.get("value")

    def fill(m):
        name = m.group(1)
        if name in own:
            return _num(own[name][0])
        if name.removeprefix("bonus_") in own:
            return _num(own[name.removeprefix("bonus_")][0])
        return _num(abs(bonus)) if bonus is not None else "?"

    return re.sub(r"\{s:(\w+)\}", fill, talent["name_loc"])


def build(hero_id: int, pos: int, bracket: str) -> dict | None:
    raw = stratz.hero(bracket, hero_id)
    if not raw:
        return None
    p = raw["positions"].get(stratz.POSITIONS[pos - 1])
    if not p:
        return None
    # Stratz item tables come from a somewhat larger sample than the position stats, so the
    # denominator is the most common first starting purchase (nearly every player buys it).
    n = max([p["matches"], *(r["matchCount"] for r in p["start"] if r["instance"] == 0)]) or 1
    hero = constants.hero_by_id()[hero_id]
    _, ability_ids, _, abilities = _maps()

    # starting items: one row per (item, copy number)
    copies: dict[str, dict] = {}
    for r in p["start"]:
        it = _item(r["itemId"])
        if not it or r["matchCount"] / n < START_MIN_SHARE:
            continue
        c = copies.setdefault(it["key"], {**it, "count": 0, "share": 0.0})
        c["count"] = max(c["count"], r["instance"] + 1)
        c["share"] = max(c["share"], r["matchCount"] / n)
    starting = sorted(copies.values(), key=lambda x: -x["share"])

    boots_ids = set()
    boots = []
    for r in sorted(p["boots"], key=lambda r: -r["matchCount"]):
        it = _item(r["itemId"])
        if not it:
            continue
        boots_ids.add(it["key"])
        if r["matchCount"] / n >= SITUATIONAL_MIN_SHARE:
            boots.append({**it, "share": r["matchCount"] / n, "wr": _wr(r["winCount"], r["matchCount"]),
                          "minute": round(r["time"] / r["matchCount"] / 60, 1)})

    # full items: rows are per (item, copy, minute bucket); first copy only
    agg = defaultdict(lambda: {"m": 0, "w": 0, "t": 0.0})
    for r in p["full"]:
        if r["instance"] != 0:
            continue
        a = agg[r["itemId"]]
        a["m"] += r["matchCount"]
        a["w"] += r["winCount"]
        a["t"] += r["time"] * r["matchCount"]
    hero_wr = None
    items = []
    for iid, a in agg.items():
        it = _item(iid)
        if not it or it["key"] in SKIP_ITEMS or it["key"] in boots_ids or a["m"] / n < SITUATIONAL_MIN_SHARE:
            continue
        items.append({**it, "share": a["m"] / n, "wr": _wr(a["w"], a["m"]), "minute": round(a["t"] / a["m"], 1)})
    total_w = sum(r["winCount"] for r in p["start"] if r["instance"] == 0)  # rough hero wr on this position
    total_m = sum(r["matchCount"] for r in p["start"] if r["instance"] == 0)
    hero_wr = _wr(total_w, total_m)

    early = sorted([i for i in items if i["minute"] < EARLY_BEFORE_MIN and i["cost"] <= EARLY_MAX_COST
                    and i["share"] >= CORE_MIN_SHARE / 2], key=lambda i: i["minute"])
    early_keys = {i["key"] for i in early}
    core = sorted([i for i in items if i["key"] not in early_keys and i["share"] >= CORE_MIN_SHARE],
                  key=lambda i: i["minute"])[:6]
    core_keys = {i["key"] for i in core}
    situational = sorted([i for i in items if i["key"] not in early_keys | core_keys],
                         key=lambda i: -(i["wr"] or 0))[:10]

    # ability max order: weighted median level at which each ability was maxed
    lv = defaultdict(list)
    for r in p["amax"]:
        key = ability_ids.get(r["abilityId"])
        if key and not key.startswith("special_bonus"):
            lv[key].append((r["level"], r["matchCount"]))
    first = defaultdict(list)
    for r in p["amin"]:
        key = ability_ids.get(r["abilityId"])
        if key and not key.startswith("special_bonus"):
            first[key].append((r["level"], r["matchCount"]))

    def wmedian(pairs):
        pairs = sorted(pairs)
        half, acc = sum(c for _, c in pairs) / 2, 0
        for level, c in pairs:
            acc += c
            if acc >= half:
                return level
        return None

    skills = sorted(({"key": k, "name": abilities.get(k, {}).get("dname", k), "max_level": wmedian(v),
                      "first_level": wmedian(first.get(k, []))} for k, v in lv.items()),
                    key=lambda s: s["max_level"] or 99)

    # talents: pick share for each side of a level
    talent_rows = {ability_ids.get(r["abilityId"]): r for r in p["talent"]}
    talents = []
    hero_talents = constants._load("hero_abilities").get(f"npc_dota_hero_{hero['key']}", {}).get("talents", [])
    for level in (1, 2, 3, 4):
        pair = [t["name"] for t in hero_talents if t["level"] == level]
        counts = [talent_rows.get(k, {}).get("matchCount", 0) for k in pair]
        tot = sum(counts) or 1
        talents.append({"level": 5 + 5 * level, "options": [
            {"key": k, "name": talent_text(k, hero_id), "share": c / tot,
             "wr": _wr(talent_rows.get(k, {}).get("winCount", 0), c)} for k, c in zip(pair, counts)]})

    return {"hero": hero_id, "pos": pos, "bracket": bracket, "week": raw["week"], "matches": p["matches"],
            "hero_wr": hero_wr, "starting": starting, "boots": boots[:3], "early": early, "core": core,
            "situational": situational, "skills": skills, "talents": talents,
            "item_share": {i["key"]: round(i["share"], 4) for i in items + boots},
            "facets": hero["facets"]}
