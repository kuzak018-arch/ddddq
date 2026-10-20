"""Hints during a match for the overlay, from Game State Integration only (what Dota itself sends:
the clock, gold, the hero's items, buyback; no memory reading).

- Timers of the map objects, by the map rules since 7.33 (checked against the patch notes up to
  7.41f): power runes from 6:00 every 2 minutes (water runes at 2:00 and 4:00), bounty runes every
  3 minutes, wisdom runes from 7:00 every 7 minutes, lotuses from 3:00 every 3 minutes, day and
  night switching every 5 minutes.
- The next item of the build the overlay shows (the top players' order): its cost minus the parts
  already in the inventory, and whether there is enough gold now.
- Buyback: the cost against the gold, and whether it is on cooldown.
"""

from __future__ import annotations

import time

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


def live_from_payload(payload: dict) -> dict:
    """The part of a GSI message the hints use."""
    m = payload.get("map") or {}
    p = payload.get("player") or {}
    h = payload.get("hero") or {}
    items = payload.get("items")
    owned = []
    if isinstance(items, dict):
        for slot in INVENTORY:
            name = str((items.get(slot) or {}).get("name") or "")
            if name.startswith("item_"):
                owned.append(name.removeprefix("item_"))
    return {
        "clock": m.get("clock_time"), "daytime": m.get("daytime"), "paused": bool(m.get("paused")),
        "gold": p.get("gold"), "gpm": p.get("gpm"), "xpm": p.get("xpm"), "last_hits": p.get("last_hits"),
        "level": h.get("level"), "alive": h.get("alive"), "respawn": h.get("respawn_seconds"),
        "buyback_cost": h.get("buyback_cost"), "buyback_cooldown": h.get("buyback_cooldown"),
        "has_items": isinstance(items, dict), "items": owned, "ts": time.time(),
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
            out.append({"key": key, "name": TIMER_NAMES[key], "in": s})
    if clock >= 0:
        flip = int(DAY_NIGHT - clock % DAY_NIGHT)
        night_now = (clock // DAY_NIGHT) % 2 == 1 if daytime is None else not daytime
        out.append({"key": "night", "name": "День" if night_now else "Ночь", "in": flip})
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


def hints(live: dict | None, targets: list[str]) -> dict:
    """Everything the overlay shows in a match; `targets` is the build's item order."""
    if not live:
        return {"live": None, "timers": [], "next": None, "buyback": None}
    items = constants._load("items")
    owned = live.get("items") or []
    nxt = None
    if live.get("has_items"):
        for t in targets:
            if t not in owned:
                nxt = item_progress(t, owned, live.get("gold"), items)
                if nxt:
                    break
    bb = None
    if live.get("buyback_cost"):
        cost, gold = int(live["buyback_cost"]), int(live.get("gold") or 0)
        bb = {"cost": cost, "enough": gold >= cost, "missing": max(0, cost - gold), "cooldown": int(live.get("buyback_cooldown") or 0)}
    return {"live": live, "timers": timers(live.get("clock"), live.get("daytime")), "next": nxt, "buyback": bb}
