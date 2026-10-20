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
CORE_FALLBACK_SHARE = 0.10
SITUATIONAL_MIN_COST = 1000  # cheaper finished items are early-game pieces, not situational choices
SITUATIONAL_MIN_SHARE = 0.03
EARLY_BEFORE_MIN = 14      # finished before this minute on average and cheap -> early item
EARLY_MAX_COST = 2500
TALENT_MIN_PICKS = 0.05    # below this share of matches the talent split at a level isn't shown as data
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
    if not key or key not in items or key in constants.RETIRED_ITEMS:
        return None
    return {"key": key, "name": items[key]["dname"], "cost": items[key].get("cost") or 0}


def _wr(w, n):
    return w / n if n else None


def _talent_pairs(hero_id: int, hero_key: str) -> list[list[str]]:
    """Talent pairs for levels 10/15/20/25. Valve's feed is current; OpenDota's list can be a
    patch behind (Invoker still had a removed talent there), so it is only the fallback."""
    vh = constants.valve_hero(hero_id)
    if vh and len(vh.get("talents", [])) == 8:
        names = [t["name"] for t in vh["talents"]]
        return [names[i:i + 2] for i in range(0, 8, 2)]
    od = constants._load("hero_abilities").get(f"npc_dota_hero_{hero_key}", {}).get("talents", [])
    return [[t["name"] for t in od if t["level"] == lv] for lv in (1, 2, 3, 4)]


def _wmedian(pairs: list[tuple[float, int]]) -> float | None:
    """Median of values given as (value, count) pairs."""
    pairs = sorted(pairs)
    half, acc = sum(c for _, c in pairs) / 2, 0
    for value, c in pairs:
        acc += c
        if acc >= half:
            return value
    return None


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
        od = _maps()[3].get(key, {}).get("dname")
        return re.sub(r"\{s:\w+\}", "?", od) if od else key
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
    # Stratz's item tables come from larger (and different) samples than the position stats: on
    # Anti-Mage pos 1, 73k matches in stats but Power Treads bought in 99.6k. Nearly every game buys
    # boots and a first starting item, so the largest count over all tables is the match total.
    full_first = defaultdict(int)
    for r in p["full"]:
        if r["instance"] == 0:
            full_first[r["itemId"]] += r["matchCount"]
    n = max([p["matches"],
             *(r["matchCount"] for r in p["start"] if r["instance"] == 0),
             *(r["matchCount"] for r in p["boots"]),
             *full_first.values()]) or 1
    hero = constants.hero_by_id()[hero_id]
    _, ability_ids, all_items, abilities = _maps()

    # starting items: one row per (item, copy number)
    copies: dict[str, dict] = {}
    for r in p["start"]:
        it = _item(r["itemId"])
        if not it or r["matchCount"] / n < START_MIN_SHARE:
            continue
        c = copies.setdefault(it["key"], {**it, "count": 0, "share": 0.0})
        c["count"] = max(c["count"], r["instance"] + 1)
        c["share"] = max(c["share"], min(1.0, r["matchCount"] / n))
    starting = sorted(copies.values(), key=lambda x: -x["share"])

    boots_ids = set()
    boots = []
    for r in sorted(p["boots"], key=lambda r: -r["matchCount"]):
        it = _item(r["itemId"])
        if not it:
            continue
        boots_ids.add(it["key"])
        if r["matchCount"] / n >= SITUATIONAL_MIN_SHARE:
            boots.append({**it, "share": min(1.0, r["matchCount"] / n), "wr": _wr(r["winCount"], r["matchCount"]),
                          "minute": round(r["time"] / r["matchCount"] / 60, 1)})

    # full items: rows are per (item, copy, minute bucket); first copy only.
    # The minute histogram gives a median purchase minute (the mean is dragged by very late buys).
    agg = defaultdict(lambda: {"m": 0, "w": 0, "hist": []})
    for r in p["full"]:
        if r["instance"] != 0:
            continue
        a = agg[r["itemId"]]
        a["m"] += r["matchCount"]
        a["w"] += r["winCount"]
        a["hist"].append((r["time"], r["matchCount"]))
    medians = {iid: _wmedian(a["hist"]) for iid, a in agg.items()}
    for b in boots:  # boots timing: median from the same per-minute rows when Stratz has them there
        iid = next((i for i, k in _maps()[0].items() if k == b["key"]), None)
        if iid in medians:
            b["minute"] = float(medians[iid])
    items = []
    for iid, a in agg.items():
        it = _item(iid)
        # no cost = map pickups / consumables (Healing Lotus etc.), not something you build
        if (not it or not it["cost"] or "consumable" in (all_items[it["key"]].get("qual") or "")
                or it["key"] in SKIP_ITEMS or it["key"] in boots_ids or a["m"] / n < SITUATIONAL_MIN_SHARE):
            continue
        items.append({**it, "share": min(1.0, a["m"] / n), "wr": _wr(a["w"], a["m"]),
                      "minute": float(medians[iid])})
    total_w = sum(r["winCount"] for r in p["start"] if r["instance"] == 0)  # rough hero wr on this position
    total_m = sum(r["matchCount"] for r in p["start"] if r["instance"] == 0)
    hero_wr = _wr(total_w, total_m)

    early = sorted([i for i in items if i["minute"] < EARLY_BEFORE_MIN and i["cost"] <= EARLY_MAX_COST
                    and i["share"] >= CORE_MIN_SHARE / 2], key=lambda i: i["minute"])
    early_keys = {i["key"] for i in early}
    later = [i for i in items if i["key"] not in early_keys and i["cost"] >= SITUATIONAL_MIN_COST]
    core = [i for i in later if i["share"] >= CORE_MIN_SHARE]
    if len(core) < 3:  # supports and rare positions rarely have items above 25%: take the most common ones
        extra = sorted((i for i in later if i not in core and i["share"] >= CORE_FALLBACK_SHARE),
                       key=lambda i: -i["share"])
        core += extra[:3 - len(core)]
    core = sorted(core, key=lambda i: i["minute"])[:6]
    core_keys = {i["key"] for i in core}
    # a component bought on the way to an item that is already in the build is not a separate choice
    built = {i["key"] for i in items}
    parts_of_built = {c for k in built for c in (all_items.get(k, {}).get("components") or [])}
    situational = sorted([i for i in later if i["key"] not in core_keys and i["key"] not in parts_of_built],
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

    skills = sorted(({"key": k, "name": abilities.get(k, {}).get("dname", k), "max_level": _wmedian(v),
                      "first_level": _wmedian(first.get(k, []))} for k, v in lv.items()),
                    key=lambda s: s["max_level"] or 99)

    # talents: pick share for each side of a level
    talent_rows = {ability_ids.get(r["abilityId"]): r for r in p["talent"]}
    talents = []
    for level, pair in enumerate(_talent_pairs(hero_id, hero["key"]), 1):
        counts = [talent_rows.get(k, {}).get("matchCount", 0) for k in pair]
        tot = sum(counts)
        talents.append({"level": 5 + 5 * level, "picks": tot, "enough": tot >= TALENT_MIN_PICKS * n,
                        "options": [{"key": k, "name": talent_text(k, hero_id), "share": c / tot if tot else 0.0,
                                     "wr": _wr(talent_rows.get(k, {}).get("winCount", 0), c)}
                                    for k, c in zip(pair, counts)]})

    return {"hero": hero_id, "pos": pos, "bracket": bracket, "week": raw["week"], "matches": p["matches"],
            "hero_wr": hero_wr, "starting": starting, "boots": boots[:3], "early": early, "core": core,
            "situational": situational, "skills": skills, "talents": talents,
            "item_share": {i["key"]: round(i["share"], 4) for i in items + boots},
            "facets": hero["facets"]}


# ---------- the same shape as the match-based builds (fallback, marked approximate) ---------------

BOOTS_T2 = {"phase_boots", "power_treads", "arcane_boots", "tranquil_boots"}
BOOTS_UP = {"travel_boots", "travel_boots_2", "guardian_greaves", "boots_of_bearing"}
ALT_MIN_SHARE = 0.15


def _choice(options: list[dict]) -> dict | None:
    """Mutually exclusive options (boots): the most common one plus "or" alternatives."""
    options = sorted(options, key=lambda o: -o["share"])
    if not options:
        return None
    main = {k: options[0][k] for k in ("key", "name", "cost", "share", "minute")}
    main["alternatives"] = [{k: o[k] for k in ("key", "name", "cost", "share", "minute")}
                            for o in options[1:] if o["share"] >= ALT_MIN_SHARE]
    return main


def approximate(b: dict) -> dict:
    """Aggregated item popularity (no per-match sequences) in the build format. Only boots are
    known to exclude each other here, so only boots get "or"; core items are the most popular ones
    in median-purchase order, and the result is flagged approximate."""
    boots = [x for x in b["boots"] if x["key"] in BOOTS_T2] or [x for x in b["boots"] if x["key"] == "boots"]
    ups = _choice([x for x in b["boots"] if x["key"] in BOOTS_UP])
    entry = lambda x: {"key": x["key"], "name": x["name"], "cost": x["cost"], "share": round(x["share"], 3),
                       "minute": x["minute"], "alternatives": []}
    from .sequences import _parents
    core_keys = {x["key"] for x in b["core"]} | {x["key"] for x in b["situational"]}
    # intermediate components (Maelstrom -> Mjollnir, Yasha -> Sange and Yasha) are steps, not core items
    part = lambda x: bool(_parents().get(x["key"], set()) & core_keys)
    core = [x for x in b["core"] if not part(x)]
    return {
        "title": "Популярные предметы", "approximate": True, "games": b["matches"], "wins": None,
        "wr": b["hero_wr"], "reliable": False, "share": 1.0,
        "starting": [{"key": x["key"], "name": x["name"], "count": x.get("count", 1)} for x in b["starting"]],
        "starting_share": None,
        "early": [entry(x) for x in b["early"] if not part(x)],  # Perseverance -> Battle Fury
        "boots": _choice(boots),
        "boots_upgrade": ups if ups and ups["share"] >= ALT_MIN_SHARE else None,
        "core": [entry(x) for x in core],
        "situational": [entry(x) | {"wr": x.get("wr")} for x in b["situational"] if not part(x)],
        "skills": [], "skill_order": b["skills"], "talents": b["talents"],
    }
