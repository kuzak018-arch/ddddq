"""Hints during a match for the overlay, from Game State Integration only (what Dota itself sends:
the clock, gold, the hero's items, buyback; no memory reading).

- Timers of the map objects, by the map rules since 7.33 (checked against the patch notes up to
  7.41f): power runes from 6:00 every 2 minutes (water runes at 2:00 and 4:00), bounty runes every
  3 minutes, wisdom runes from 7:00 every 7 minutes, lotuses from 3:00 every 3 minutes, day and
  night switching every 5 minutes.
- The next item of the build the overlay shows (the top players' order): its cost minus the parts
  already in the inventory, and whether there is enough gold now.
- Buyback: the cost against the gold, and whether it is on cooldown.
- The skill to take: the hero's ability levels (GSI "abilities" block) and talents against the
  build's skill order, and whether a point is free now (hero level above the points spent).
- Neutral item tiers: the Madstone limit opens a tier at 5, 15, 25, 35 and 60 minutes.
- Roshan and the Tormentor: from Dota's own Roshan state when the map block carries it, else from
  the kill the user marks with a button (the kill itself is not sent to a player). Roshan comes
  back 8–11 minutes after his death, the Aegis lasts 5 minutes; the Tormentor first appears at
  15:00 and 10 minutes after its death, at night on the Radiant side, by day on the Dire side
  (patch 7.38); from 15:00 Roshan walks to the top pit at night and to the bottom one by day.
"""

from __future__ import annotations

import threading
import time
from collections import Counter

from .data import constants

INVENTORY = [f"slot{i}" for i in range(9)] + [f"stash{i}" for i in range(6)] + ["neutral0"]

# (name, first spawn s, period s, until s or None)
TIMERS = [
    ("power", 6 * 60, 2 * 60, None),
    ("water", 2 * 60, 2 * 60, 4 * 60),
    ("bounty", 0, 3 * 60, None),
    ("wisdom", 7 * 60, 7 * 60, None),
    ("lotus", 3 * 60, 3 * 60, None),
]
TIMER_NAMES = {"power": "Руна силы", "water": "Руна воды", "bounty": "Руны богатства", "wisdom": "Руны мудрости", "lotus": "Лотосы"}
DAY_NIGHT = 5 * 60
NEUTRAL_TIERS = {1: 5 * 60, 2: 15 * 60, 3: 25 * 60, 4: 35 * 60, 5: 60 * 60}
ROSHAN_MIN, ROSHAN_MAX, AEGIS = 8 * 60, 11 * 60, 5 * 60
TORMENTOR_FIRST, TORMENTOR_RESPAWN = 15 * 60, 10 * 60
WANDERING_FROM = 15 * 60      # Roshan follows day and night from here on
NO_POINT_LEVELS = (17, 19, 21, 22, 23, 24)   # hero levels that give no skill point


def live_from_payload(payload: dict) -> dict:
    """The part of a GSI message the hints use."""
    m = payload.get("map") or {}
    p = payload.get("player") or {}
    h = payload.get("hero") or {}
    items = payload.get("items")
    owned = []
    neutral = None
    if isinstance(items, dict):
        for slot in INVENTORY:
            name = str((items.get(slot) or {}).get("name") or "")
            if name.startswith("item_"):
                owned.append(name.removeprefix("item_"))
                if slot == "neutral0":
                    neutral = name.removeprefix("item_")
    abil = payload.get("abilities")
    abilities = []
    if isinstance(abil, dict):
        for k in sorted(abil, key=lambda x: int(x[7:]) if x[7:].isdigit() else 99):
            a = abil[k]
            if isinstance(a, dict) and a.get("name"):
                abilities.append({"name": str(a["name"]), "level": int(a.get("level") or 0),
                                  "ultimate": bool(a.get("ultimate")), "cooldown": a.get("cooldown")})
    talent_keys = [f"talent_{i}" for i in range(1, 9)]
    return {
        "clock": m.get("clock_time"), "daytime": m.get("daytime"), "paused": bool(m.get("paused")),
        "gold": p.get("gold"), "gpm": p.get("gpm"), "xpm": p.get("xpm"), "last_hits": p.get("last_hits"),
        "net_worth": p.get("net_worth"), "hero_id": h.get("id"),
        "level": h.get("level"), "alive": h.get("alive"), "respawn": h.get("respawn_seconds"),
        "buyback_cost": h.get("buyback_cost"), "buyback_cooldown": h.get("buyback_cooldown"),
        "has_items": isinstance(items, dict), "items": owned, "neutral": neutral,
        "has_abilities": isinstance(abil, dict), "abilities": abilities,
        "talents": sum(1 for t in talent_keys if h.get(t) is True) if any(t in h for t in talent_keys) else None,
        "attributes": h.get("attributes_level") if isinstance(h.get("attributes_level"), int) else None,
        "match_id": str(m.get("matchid") or "") or None,
        "roshan_state": m.get("roshan_state"), "roshan_end": m.get("roshan_state_end_seconds"),
        "ts": time.time(),
    }


def next_spawn(clock: float, first: int, period: int, until: int | None = None) -> int | None:
    """Seconds until the next spawn at game time `clock` (a spawn right now counts as now)."""
    if clock <= first:
        return int(first - clock)
    n = -(-(clock - first) // period)  # ceil
    at = first + n * period
    if until is not None and at > until:
        return None
    return int(at - clock)


def timers(clock: float | None, daytime: bool | None) -> list[dict]:
    if clock is None:
        return []
    out = []
    for key, first, period, until in TIMERS:
        s = next_spawn(clock, first, period, until)
        if s is not None:
            out.append({"key": key, "name": TIMER_NAMES[key], "in": s, "period": period if clock >= first else first})
    if clock >= 0:
        flip = int(DAY_NIGHT - clock % DAY_NIGHT)
        night_now = (clock // DAY_NIGHT) % 2 == 1 if daytime is None else not daytime
        out.append({"key": "night", "name": "День" if night_now else "Ночь", "in": flip, "period": DAY_NIGHT})
    return sorted(out, key=lambda t: t["in"])


def item_progress(target: str, owned: list[str], gold: int | None, items: dict) -> dict | None:
    """How much a target item still costs given the parts already owned (one level of recipe)."""
    it = items.get(target)
    if not it:
        return None
    cost = int(it.get("cost") or 0)
    pool = list(owned)
    have = []
    for comp in it.get("components") or []:
        if comp in pool:
            pool.remove(comp)
            have.append(comp)
            cost -= int((items.get(comp) or {}).get("cost") or 0)
    cost = max(0, cost)
    missing = max(0, cost - int(gold or 0))
    return {"key": target, "name": it.get("dname") or target, "cost": int(it.get("cost") or 0), "left": cost,
            "missing": missing, "ready": missing == 0, "have": have}


def next_skill(live: dict | None, order: list[str]) -> dict | None:
    """The build's next skill given what is already taken: `order` is the build's key per level
    ("talent" for a talent level). Walking the order, the first key taken fewer times than the
    order has asked for so far is the next one, so a different order of the user is followed.
    `at` is the place in the order (the n-th point), not the hero level."""
    if not live or not live.get("has_abilities") or not order:
        return None
    have = Counter()
    for a in live.get("abilities") or []:
        have[a["name"]] = max(have[a["name"]], a["level"])
    level = int(live.get("level") or 0)
    # the levels without a skill point give the attribute bonus by themselves: Dota says how many
    attrs = live.get("attributes")
    earned = level - attrs if isinstance(attrs, int) else level - sum(1 for lv in NO_POINT_LEVELS if lv <= level)
    in_order = set(order) - {"talent"}
    spent_abilities = sum(have[k] for k in in_order)
    talents = live.get("talents")
    if talents is None:  # an older Dota without talent flags: the points left over are talents
        talents = max(0, min(earned - spent_abilities, sum(1 for i, k in enumerate(order) if k == "talent" and i < earned)))
    have["talent"] = talents
    spent = spent_abilities + talents
    seen = Counter()
    for i, k in enumerate(order):
        seen[k] += 1
        if seen[k] > have[k]:
            return {"key": k, "at": i + 1, "points": max(0, earned - spent), "now": earned > spent}
    return None


def neutral_tier(clock: float | None) -> dict | None:
    """The tier open now (with how long ago it opened) and the next one."""
    if clock is None:
        return None
    cur = max((t for t, at in NEUTRAL_TIERS.items() if clock >= at), default=None)
    nxt = min((t for t, at in NEUTRAL_TIERS.items() if clock < at), default=None)
    return {"tier": cur, "ago": int(clock - NEUTRAL_TIERS[cur]) if cur else None,
            "next": nxt, "in": int(NEUTRAL_TIERS[nxt] - clock) if nxt else None}


# kills marked with the overlay's buttons, for the current match only
_marks: dict = {"match": None}
_marks_lock = threading.Lock()


def mark(kind: str, live: dict | None, undo: bool = False) -> dict:
    """Remember a Roshan / Tormentor kill at the current game clock (or forget it)."""
    if kind not in ("roshan", "tormentor"):
        raise ValueError(kind)
    with _marks_lock:
        match = (live or {}).get("match_id")
        if _marks.get("match") != match:
            _marks.clear()
            _marks["match"] = match
        if undo:
            _marks.pop(kind, None)
        elif live and live.get("clock") is not None:
            _marks[kind] = float(live["clock"])
        return dict(_marks)


def _marked(live: dict) -> dict:
    with _marks_lock:
        if _marks.get("match") != live.get("match_id"):
            return {}
        return {k: v for k, v in _marks.items() if k != "match"}


def objectives(live: dict | None) -> dict | None:
    """Roshan and the Tormentor: alive / maybe / dead with the seconds to the next change."""
    if not live or live.get("clock") is None:
        return None
    clock = float(live["clock"])
    night = (clock // DAY_NIGHT) % 2 == 1 if live.get("daytime") is None else not live["daytime"]
    marks = _marked(live)
    rosh: dict = {"source": "mark" if "roshan" in marks else "none"}
    state = str(live.get("roshan_state") or "")
    if state and "roshan" not in marks:
        end = live.get("roshan_end")
        rosh = {"source": "dota", "state": "alive" if state == "alive" else "maybe" if "variable" in state else "dead",
                "in": int(end) if isinstance(end, (int, float)) and end > 0 else None}
    elif "roshan" in marks:
        since = clock - marks["roshan"]
        rosh.update({"killed_at": int(marks["roshan"]),
                     "aegis": int(AEGIS - since) if since < AEGIS else None,
                     "state": "dead" if since < ROSHAN_MIN else "maybe" if since < ROSHAN_MAX else "alive",
                     "in": int(ROSHAN_MIN - since) if since < ROSHAN_MIN else int(ROSHAN_MAX - since) if since < ROSHAN_MAX else None})
    else:
        rosh["state"] = "alive"
    rosh["pit"] = None if clock < WANDERING_FROM else ("top" if night else "bottom")
    if "tormentor" in marks:
        since = clock - marks["tormentor"]
        torm = {"source": "mark", "killed_at": int(marks["tormentor"]),
                "state": "dead" if since < TORMENTOR_RESPAWN else "alive",
                "in": int(TORMENTOR_RESPAWN - since) if since < TORMENTOR_RESPAWN else None}
    else:
        torm = {"source": "none", "state": "dead" if clock < TORMENTOR_FIRST else "alive",
                "in": int(TORMENTOR_FIRST - clock) if clock < TORMENTOR_FIRST else None}
    torm["side"] = "radiant" if night else "dire"
    return {"roshan": rosh, "tormentor": torm, "night": night}


BOOTS = {"boots", "power_treads", "phase_boots", "arcane_boots", "tranquil_boots", "travel_boots", "travel_boots_2",
         "guardian_greaves", "boots_of_bearing"}
NOT_A_CHOICE = BOOTS | {"aghanims_shard", "aghanims_shard_roshan", "ultimate_scepter_roshan", "cheese", "refresher_shard",
                        "aegis", "ward_observer", "ward_sentry", "ward_dispenser", "dust", "smoke_of_deceit", "tpscroll"}
OFFPLAN_MIN_COST = 1200
REPLACES_SHARE = 0.6     # an item off the build replaces the next one when it costs at least this share of it


def _parts(key: str, items: dict, depth: int = 4) -> set[str]:
    out: set[str] = set()
    for c in (items.get(key) or {}).get("components") or []:
        out.add(c)
        if depth:
            out |= _parts(c, items, depth - 1)
    return out


def next_target(targets: list[str], owned: list[str], items: dict, skipped: set[str] | None = None) -> tuple[str | None, list[dict]]:
    """The build's next item given what the player really built. An item of the build is passed
    when a later one of the build is already owned, when the player skipped it by hand, or when a
    finished item off the build took its place (Nullifier instead of Basher, Aghanim's Scepter instead
    of Helm of the Dominator: off the build, not a part of it nor of any other item, at least
    REPLACES_SHARE of its cost).
    Returns (the next item, what was passed and why)."""
    skipped = skipped or set()
    have = set(owned)
    passed: list[dict] = []
    plan = []
    for t in targets:
        if t in skipped and t not in have:
            passed.append({"key": t, "why": "skipped"})
        else:
            plan.append(t)
    last = max((i for i, t in enumerate(plan) if t in have), default=-1)
    rest = []
    for i, t in enumerate(plan):
        if t in have:
            continue
        if i < last:
            passed.append({"key": t, "why": "later"})
        else:
            rest.append(t)
    in_build = set(targets) | {p for t in targets for p in _parts(t, items)}
    # only finished items stand for a choice: an Ultimate Orb on its way to a Skadi is not one
    parts_of_anything = {c for it in items.values() for c in (it.get("components") or [])}
    cost = lambda k: int((items.get(k) or {}).get("cost") or 0)  # noqa: E731
    off = sorted((k for k in have if k not in in_build and k not in NOT_A_CHOICE and k not in parts_of_anything
                  and not (items.get(k) or {}).get("tier")
                  and cost(k) >= OFFPLAN_MIN_COST and "consumable" not in str((items.get(k) or {}).get("qual") or "")),
                 key=lambda k: -cost(k))
    while rest and off:
        t = rest[0]
        by = next((k for k in off if cost(k) >= REPLACES_SHARE * cost(t)), None)
        if not by:
            break
        off.remove(by)
        passed.append({"key": t, "why": "replaced", "by": by})
        rest.pop(0)
    return (rest[0] if rest else None), passed


def mark_skip(key: str, live: dict | None, undo: bool = False) -> list[str]:
    """The player skips the shown next item by hand (or takes the skip back), for this match."""
    with _marks_lock:
        match = (live or {}).get("match_id")
        if _marks.get("match") != match:
            _marks.clear()
            _marks["match"] = match
        sk = set(_marks.get("skip") or [])
        sk.discard(key) if undo else sk.add(key)
        _marks["skip"] = sorted(sk)
        return _marks["skip"]


def hints(live: dict | None, targets: list[str], skills: list[str] | None = None) -> dict:
    """Everything the overlay shows in a match; `targets` is the build's item order, `skills` its
    skill order by level."""
    if not live:
        return {"live": None, "timers": [], "next": None, "buyback": None, "skill": None, "neutral_tier": None,
                "objectives": None}
    items = constants._load("items")
    owned = live.get("items") or []
    nxt = None
    passed: list[dict] = []
    if live.get("has_items"):
        skipped = set(_marked(live).get("skip") or [])
        known = [t for t in targets if t in items]
        key, passed = next_target(known, owned, items, skipped)
        nxt = item_progress(key, owned, live.get("gold"), items) if key else None
        names = lambda k: (items.get(k) or {}).get("dname") or k  # noqa: E731
        passed = [{**p, "name": names(p["key"]), **({"by_name": names(p["by"])} if p.get("by") else {})} for p in passed]
    bb = None
    if live.get("buyback_cost"):
        cost, gold = int(live["buyback_cost"]), int(live.get("gold") or 0)
        bb = {"cost": cost, "enough": gold >= cost, "missing": max(0, cost - gold), "cooldown": int(live.get("buyback_cooldown") or 0)}
    return {"live": live, "timers": timers(live.get("clock"), live.get("daytime")), "next": nxt, "passed": passed, "buyback": bb,
            "skill": next_skill(live, skills or []), "neutral_tier": neutral_tier(live.get("clock")),
            "objectives": objectives(live)}
