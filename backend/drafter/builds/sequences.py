"""Whole builds from real per-match purchase sequences.

Per game (one player on the hero and position):
  starting  - everything bought before the horn (exact multiset)
  boots     - the first "finished" boots (Phase, Treads, Arcane, Tranquil), else plain Boots of Speed;
              a later upgrade (Travel, Greaves, Bearing) is a separate step
  early     - cheap finished items (< 1200 gold) bought before minute 15
  core      - finished items in purchase order: no consumables, no recipes, no boots, and no
              intermediate components (an item that later goes into something this player builds,
              e.g. Maelstrom -> Mjollnir, Yasha -> Sange and Yasha)
  skills    - ability learned at each hero level; talents separately

Games are grouped by their first two core items; the 2-3 most common groups become builds.
Inside a build: the most common exact starting set; boots and every later core slot with
explicit alternatives ("or", with share); median purchase minutes; situational items; skill order
by level and talents from the same games; games and winrate over all of them (wins and losses).
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import cache

from ..data import constants
from . import standard

CONSUMABLES = {"tango", "clarity", "flask", "tpscroll", "ward_observer", "ward_sentry", "ward_dispenser",
               "smoke_of_deceit", "dust", "faerie_fire", "enchanted_mango", "famango", "great_famango",
               "greater_famango", "blood_grenade", "cheese", "aghanims_shard_roshan", "refresher_shard",
               "tome_of_knowledge", "royal_jelly", "river_painter"}
BOOTS = {"phase_boots", "power_treads", "arcane_boots", "tranquil_boots"}
BOOTS_BASE = "boots"
BOOTS_UPGRADES = {"travel_boots", "travel_boots_2", "guardian_greaves", "boots_of_bearing"}
SHARD = "aghanims_shard"
EARLY_MAX_COST = 1200
EARLY_BEFORE_S = 15 * 60
START_BEFORE_S = 10
MIN_BUILD_GAMES = 15
MIN_BUILD_SHARE = 0.08
RELIABLE_GAMES = 100
ALT_MIN_SHARE = 0.15
CORE_SLOT_MIN_SHARE = 0.12   # later core slot: its most common item in >= 12% of the build's games...
CORE_SLOT_COVER = 0.35       # ...and the options shown ("X or Y or Z") together in >= 35%
LATE_ALT_MIN_SHARE = 0.08
SITUATIONAL_MIN_SHARE = 0.08
MAX_CORE = 6
# hero levels that give a skill point (none at 17, 19, 21-24): the n-th learn happens at POINT_LEVELS[n]
POINT_LEVELS = [*range(1, 17), 18, 20, *range(25, 31)]
SPLIT_SHARE = 0.6      # one 2-item opening above this share of games is split by the 3rd item


@cache
def _items() -> dict:
    return constants._load("items")


@cache
def _abilities() -> dict:
    return constants._load("abilities")


@cache
def _parents() -> dict[str, set[str]]:
    """item -> every item it is a (direct or nested) component of."""
    items = _items()
    direct: dict[str, set[str]] = defaultdict(set)
    for key, it in items.items():
        for c in it.get("components") or []:
            direct[c].add(key)
    closure: dict[str, set[str]] = {}

    def up(k, seen=()):
        if k in closure:
            return closure[k]
        res = set()
        for p in direct.get(k, ()):
            if p not in seen:
                res |= {p} | up(p, seen + (k,))
        closure[k] = res
        return res

    for k in list(items):
        up(k)
    return closure


def _cost(key: str) -> int:
    return int(_items().get(key, {}).get("cost") or 0)


def _is_finished_item(key: str) -> bool:
    it = _items().get(key)
    if not it or key.startswith("recipe_") or key in CONSUMABLES or not it.get("cost"):
        return False
    return "consumable" not in (it.get("qual") or "")


@dataclass
class Game:
    win: bool
    starting: tuple[str, ...]
    early: dict[str, int]                 # item -> second bought
    boots: tuple[str, int] | None         # (item, second)
    upgrade: tuple[str, int] | None
    core: list[tuple[str, int]]           # (item, second) in order
    later: dict[str, int] = field(default_factory=dict)   # every finished non-boot item -> second
    skills: list[str | None] = field(default_factory=list)  # ability per skill point, None = talent there
    talents: list[str] = field(default_factory=list)


def parse(rec: dict) -> Game | None:
    items = [(int(t), k) for t, k in rec.get("items") or [] if isinstance(k, str)]
    if not items:
        return None
    items.sort()
    parents = _parents()
    starting = tuple(sorted(k for t, k in items if t <= START_BEFORE_S and not k.startswith("recipe_")))
    # intermediate: something this player buys at the same time or later is built from it
    later_keys = defaultdict(list)
    for t, k in items:
        later_keys[k].append(t)

    def consumed(k: str, t: int) -> bool:
        return any(p in later_keys and max(later_keys[p]) >= t for p in parents.get(k, ()))

    boots = upgrade = None
    early: dict[str, int] = {}
    core: list[tuple[str, int]] = []
    later: dict[str, int] = {}
    plain_boots = None
    for t, k in items:
        if k == BOOTS_BASE:
            plain_boots = plain_boots or (k, t)
            continue
        if k in BOOTS:
            boots = boots or (k, t)
            continue
        if k in BOOTS_UPGRADES:
            upgrade = upgrade or (k, t)
            continue
        if t <= START_BEFORE_S or not _is_finished_item(k) or consumed(k, t):
            continue
        later.setdefault(k, t)
        if _cost(k) < EARLY_MAX_COST:
            if t < EARLY_BEFORE_S:
                early.setdefault(k, t)
            continue
        if k != SHARD and k not in dict(core):
            core.append((k, t))
    if boots is None:
        boots = plain_boots
    # one entry per skill point, in order (POINT_LEVELS maps it to the hero level); talents (and ability ids Stratz
    # reports that aren't real abilities, e.g. id 0 on some talent levels) leave a gap
    abilities = _abilities()
    skills: list[str | None] = []
    talents = []
    for a in rec.get("skills") or []:
        if a.startswith("special_bonus"):
            talents.append(a)
        is_ability = not a.startswith("special_bonus") and bool(abilities.get(a, {}).get("dname"))
        skills.append(a if is_ability else None)
    return Game(bool(rec.get("w")), starting, early, boots, upgrade, core[:MAX_CORE], later, skills, talents)


# ---------- aggregation ----------------------------------------------------------------------

def _minute(seconds: list[int]) -> float:
    return round(statistics.median(seconds) / 60, 1)


def _name(key: str) -> str:
    return _items().get(key, {}).get("dname") or key


def _entry(key: str, seconds: list[int], share: float, games: int | None = None, wins: int | None = None) -> dict:
    e = {"key": key, "name": _name(key), "cost": _cost(key), "share": round(share, 3), "minute": _minute(seconds)}
    if games is not None:
        e["games"] = games
        e["wr"] = round(wins / games, 3) if games else None
    return e


def _choice(values: list[tuple[str, int]], total: int) -> dict | None:
    """Most common option + alternatives with >= ALT_MIN_SHARE, shares of `total` games."""
    if not values:
        return None
    by: dict[str, list[int]] = defaultdict(list)
    for k, t in values:
        by[k].append(t)
    ranked = sorted(by.items(), key=lambda kv: -len(kv[1]))
    main_k, main_t = ranked[0]
    main = _entry(main_k, main_t, len(main_t) / total)
    main["alternatives"] = [_entry(k, ts, len(ts) / total) for k, ts in ranked[1:] if len(ts) / total >= ALT_MIN_SHARE]
    return main


def _skills(games: list[Game], hero_key: str) -> list[dict]:
    abilities = _abilities()
    out = []
    for level in range(min(len(POINT_LEVELS), max((len(g.skills) for g in games), default=0))):
        reached = [g.skills[level] for g in games if len(g.skills) > level]
        if len(reached) < len(games) * 0.3:
            break  # few games got this far
        c = Counter(k for k in reached if k)
        if sum(c.values()) < len(reached) / 2:
            out.append({"level": POINT_LEVELS[level], "key": "talent", "name": "Талант",
                        "share": round(1 - sum(c.values()) / len(reached), 3)})
            continue
        (key, n), total = c.most_common(1)[0], sum(c.values())
        out.append({"level": POINT_LEVELS[level], "key": key, "name": abilities.get(key, {}).get("dname", key),
                    "share": round(n / total, 3)})
    return out


def _talents(games: list[Game], hero_id: int, hero_key: str) -> list[dict]:
    rows = []
    for tier, pair in enumerate(standard._talent_pairs(hero_id, hero_key), 1):
        counts = [sum(1 for g in games if k in g.talents) for k in pair]
        tot = sum(counts)
        rows.append({"level": 5 + 5 * tier, "picks": tot, "enough": tot >= max(10, len(games) * 0.15),
                     "options": [{"key": k, "name": standard.talent_text(k, hero_id),
                                  "share": round(c / tot, 3) if tot else 0.0} for k, c in zip(pair, counts)]})
    return rows


def build_one(games: list[Game], hero_id: int, hero_key: str, total_games: int, sig: int = 2) -> dict:
    n = len(games)
    wins = sum(g.win for g in games)
    starting_set, start_n = Counter(g.starting for g in games).most_common(1)[0]
    start_counts = Counter(starting_set)
    early = []
    for k in {k for g in games for k in g.early}:
        ts = [g.early[k] for g in games if k in g.early]
        if len(ts) / n >= 0.3:
            early.append(_entry(k, ts, len(ts) / n))
    early.sort(key=lambda e: e["minute"])

    boots = _choice([g.boots for g in games if g.boots], n)
    upgrade = _choice([g.upgrade for g in games if g.upgrade], n)
    if upgrade and upgrade["share"] < ALT_MIN_SHARE:
        upgrade = None

    # core: the items that define the build (2, or 3 when one opening is played by almost everyone), then slot by slot. Every game has its own pointer
    # to "its next item", so an alternative taken in one slot never blocks the next slot.
    signature = {k for k, _ in games[0].core[:sig]}
    core = [_entry(k, [t for g in games for kk, t in g.core[:sig] if kk == k], 1.0) | {"alternatives": []}
            for k in signature]
    core.sort(key=lambda e: e["minute"])
    ptr = [sig] * n
    shown = set(signature)
    for _ in range(MAX_CORE - sig):
        nexts = []
        for i in range(n):   # each game's next item that hasn't been shown in an earlier slot
            while ptr[i] < len(games[i].core) and games[i].core[ptr[i]][0] in shown:
                ptr[i] += 1
            if ptr[i] < len(games[i].core):
                nexts.append((i, games[i].core[ptr[i]]))
        if not nexts:
            break
        by: dict[str, list[int]] = defaultdict(list)
        for _, (k, t) in nexts:
            by[k].append(t)
        ranked = sorted(by.items(), key=lambda kv: -len(kv[1]))
        main_k, main_t = ranked[0]
        alts = [(k, ts) for k, ts in ranked[1:] if len(ts) / n >= LATE_ALT_MIN_SHARE][:3]
        covered = len(main_t) + sum(len(ts) for _, ts in alts)
        # late slots often have no single favourite (Abyssal / Butterfly / Skadi): still a real slot
        # if its options together cover enough games; shown as "X or Y or Z"
        if len(main_t) < max(5, CORE_SLOT_MIN_SHARE * n) or covered < CORE_SLOT_COVER * n:
            break
        entry = _entry(main_k, main_t, len(main_t) / n)
        entry["alternatives"] = [_entry(k, ts, len(ts) / n) for k, ts in alts]
        core.append(entry)
        shown |= {main_k} | {k for k, _ in alts}
        for i, _ in nexts:
            ptr[i] += 1
    core.sort(key=lambda e: e["minute"])
    shown = {e["key"] for e in core} | {a["key"] for e in core for a in e["alternatives"]}

    situational = []
    for k in {k for g in games for k in g.later} - shown:
        if _cost(k) < 1000 and k != SHARD:
            continue
        with_k = [g for g in games if k in g.later]
        if len(with_k) / n >= SITUATIONAL_MIN_SHARE:
            situational.append(_entry(k, [g.later[k] for g in with_k], len(with_k) / n,
                                      len(with_k), sum(g.win for g in with_k)))
    situational.sort(key=lambda e: -e["share"])

    return {
        "title": " → ".join(e["name"] for e in core[:3]) or "без кора",
        "games": n, "wins": wins, "wr": round(wins / n, 3), "reliable": n >= RELIABLE_GAMES,
        "share": round(n / total_games, 3),
        "starting": [{"key": k, "name": _name(k), "count": c} for k, c in start_counts.items()],
        "starting_share": round(start_n / n, 3),
        "early": early, "boots": boots, "boots_upgrade": upgrade, "core": core,
        "situational": situational[:10],
        "skills": _skills(games, hero_key), "talents": _talents(games, hero_id, hero_key),
    }


def builds(records: list[dict], hero_id: int, pos: int, accounts: set[int] | None = None, top: int = 3) -> dict:
    hero = constants.hero_by_id()[hero_id]
    games = [g for r in records
             if not r.get("unparsed") and r.get("pos") == pos and (accounts is None or r.get("acc") in accounts)
             and (g := parse(r)) is not None]
    with_core = [g for g in games if len(g.core) >= 2]
    groups: dict[frozenset, list[Game]] = defaultdict(list)
    for g in with_core:
        groups[frozenset(k for k, _ in g.core[:2])].append(g)
    big_enough = max(MIN_BUILD_GAMES, MIN_BUILD_SHARE * len(with_core))
    ranked = [(grp, 2) for grp in sorted(groups.values(), key=len, reverse=True)]
    # one opening played by almost everyone (Anti-Mage: Battle Fury -> Manta): the builds differ
    # by the third item, so split that group on it
    if ranked and len(ranked[0][0]) > SPLIT_SHARE * len(with_core):
        sub: dict[frozenset, list[Game]] = defaultdict(list)
        for g in ranked[0][0]:
            if len(g.core) >= 3:
                sub[frozenset(k for k, _ in g.core[:3])].append(g)
        parts = [(grp, 3) for grp in sorted(sub.values(), key=len, reverse=True) if len(grp) >= big_enough]
        if len(parts) >= 2:
            ranked = sorted(parts + ranked[1:], key=lambda x: -len(x[0]))
    chosen = [(grp, sig) for grp, sig in ranked if len(grp) >= big_enough][:top]
    if not chosen and ranked and len(ranked[0][0]) >= 5:
        chosen = ranked[:1]
    return {"hero": hero_id, "pos": pos, "games": len(games), "with_core": len(with_core),
            "builds": [build_one(grp, hero_id, hero["key"], len(with_core), sig) for grp, sig in chosen]}
