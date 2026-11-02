"""The second half of «Кто заруинил»: what happened in the match, minute by minute. Everything here
needs OpenDota's parsed replay (a match without one gets only the ratings of ruin.py):

  - lanes: each lane's players at 10 minutes — last hits, denies, net worth and experience — and
    which side came out ahead;
  - fights: OpenDota's teamfights with the deaths of each side, the gold that changed hands, and
    the players of the side that lost it who were not there (no damage, no death, no kill);
  - items: every player's big items (cost >= MAJOR_COST) with the minute bought, against the median
    minute of top players on the hero this patch (the «Игры топов» cache, when it holds the hero);
  - mistakes: per player, the moments with a minute that cost the most — deaths before 10 minutes,
    big items far later than the top players, a lost lane by last hits, fights missed, a fight lost
    with a death in it — sorted by time;
  - map: where heroes died (from the fights) and where wards were placed.

OpenDota's coordinates are its map cells (about 64..192 each way, y up); they are passed on as
they are and the page scales them.
"""

from __future__ import annotations

import statistics

from .data import constants

MAJOR_COST = 1800
LATE_ITEM_MIN = 5          # minutes later than the top players' median that counts as a mistake
EARLY = 600                # «early» deaths: before 10:00
ABSENT_SHARE = 0.5         # missing at least this share of the fights the team lost
LOST_FIGHT_GOLD = 1500     # a fight is lost when the team's gold changed by at least this against it


def _items_const() -> dict:
    try:
        return constants._load("items")
    except Exception:  # noqa: BLE001
        return {}


def _item_name(key: str, items: dict) -> str:
    return (items.get(key) or {}).get("dname") or key.replace("_", " ").title()


def _top_norms(hero: int) -> dict[str, float]:
    """Median minute top players buy each big item on the hero (cached «Игры топов», no download)."""
    try:
        from . import topgames
        pool, _, _ = topgames._pool(hero, load=False)
    except Exception:  # noqa: BLE001
        return {}
    firsts: dict[str, list[int]] = {}
    for rec, _source in pool.values():
        seen: set[str] = set()
        for t, key in rec.get("items") or []:
            if key in seen or not isinstance(t, (int, float)) or t < 0:
                continue
            seen.add(key)
            firsts.setdefault(key, []).append(int(t))
    return {k: round(statistics.median(ts) / 60, 1) for k, ts in firsts.items() if len(ts) >= 3}


def _at(arr, minute: int):
    return arr[minute] if isinstance(arr, list) and len(arr) > minute else None


def lanes(od: dict, players: list[dict]) -> list[dict]:
    """Each lane at 10 minutes, its players by side."""
    out = []
    by_hero = {p.get("hero_id"): p for p in od.get("players") or []}
    for lane in ("top", "mid", "bot"):
        sides = {"radiant": [], "dire": []}
        for p in players:
            if p.get("lane") != lane:
                continue
            o = by_hero.get(p["hero"]) or {}
            sides["radiant" if p["radiant"] else "dire"].append({
                "hero": p["hero"], "pos": p.get("pos"),
                "lh": _at(o.get("lh_t"), 10), "dn": _at(o.get("dn_t"), 10),
                "nw": _at(o.get("gold_t"), 10), "xp": _at(o.get("xp_t"), 10),
            })
        if not sides["radiant"] and not sides["dire"]:
            continue
        nw = {k: sum(x["nw"] or 0 for x in v) for k, v in sides.items()}
        known = all(x["nw"] is not None for v in sides.values() for x in v)
        lead = (nw["radiant"] - nw["dire"]) if known else None
        out.append({"lane": lane, **sides, "nw_lead": lead,
                    "ahead": None if lead is None or abs(lead) < 500 else ("radiant" if lead > 0 else "dire")})
    return out


def fights(od: dict, players: list[dict]) -> list[dict]:
    """OpenDota's teamfights: deaths per side, the gold swing, who of the losing side was not there."""
    order = [p.get("hero_id") for p in od.get("players") or []]
    side = {p["hero"]: p["radiant"] for p in players}
    out = []
    for f in od.get("teamfights") or []:
        fp = f.get("players") or []
        if len(fp) != len(order):
            continue
        died = {"radiant": [], "dire": []}
        swing = 0.0       # radiant's gold gained minus dire's
        present = set()
        for hero, x in zip(order, fp):
            if hero not in side:
                continue
            key = "radiant" if side[hero] else "dire"
            if x.get("deaths"):
                died[key].append(hero)
            gold = x.get("gold_delta") or 0
            swing += gold if side[hero] else -gold
            if x.get("damage") or x.get("deaths") or x.get("killed") or x.get("healing"):
                present.add(hero)
        lost = "dire" if swing >= LOST_FIGHT_GOLD else "radiant" if swing <= -LOST_FIGHT_GOLD else None
        absent = [h for h in order if h in side and h not in present and lost is not None
                  and (side[h] if lost == "radiant" else not side[h])]
        out.append({"start": f.get("start"), "end": f.get("end"), "died": died, "swing": round(swing),
                    "lost": lost, "absent": absent})
    return out


def items(od: dict, players: list[dict]) -> dict[int, list[dict]]:
    """Each player's big items with the minute and the top players' usual minute."""
    consts = _items_const()
    by_hero = {p.get("hero_id"): p for p in od.get("players") or []}
    out = {}
    for p in players:
        o = by_hero.get(p["hero"]) or {}
        log = o.get("purchase_log") or []
        if not log:
            continue
        norms = _top_norms(p["hero"])
        seen, row = set(), []
        for x in log:
            key = x.get("key") or ""
            if key in seen or key.startswith("recipe_") or (consts.get(key) or {}).get("cost", 0) < MAJOR_COST:
                continue
            seen.add(key)
            minute = round((x.get("time") or 0) / 60, 1)
            norm = norms.get(key)
            row.append({"key": key, "name": _item_name(key, consts), "minute": minute, "norm": norm,
                        "late": round(minute - norm, 1) if norm is not None else None})
        out[p["hero"]] = row
    return out


def mistakes(p: dict, ctx: dict) -> list[dict]:
    """The player's costliest moments, each with a minute (seconds `t`), earliest first."""
    out = []
    early = [t for t in p.get("deaths_t") or [] if t < EARLY]
    if len(early) >= 2:
        out.append({"t": early[0], "kind": "early_deaths",
                    "text": f"{len(early)} смерти до 10-й минуты ({', '.join(_mmss(t) for t in early[:4])})"
                    if len(early) < 5 else f"{len(early)} смертей до 10-й минуты"})
    for it in ctx["items"].get(p["hero"], []):
        if it["late"] is not None and it["late"] >= LATE_ITEM_MIN:
            out.append({"t": int(it["minute"] * 60), "kind": "late_item",
                        "text": f"{it['name']} на {it['minute']:.0f}-й минуте — у топов около {it['norm']:.0f}-й"})
    for lane in ctx["lanes"]:
        mine = lane["radiant" if p["radiant"] else "dire"]
        theirs = lane["dire" if p["radiant"] else "radiant"]
        me = next((x for x in mine if x["hero"] == p["hero"]), None)
        if not me or me["lh"] is None or (p.get("pos") or 5) > 3 or not theirs:
            continue
        opp = max(theirs, key=lambda x: x["lh"] or 0)
        if opp["lh"] and me["lh"] < 0.7 * opp["lh"] and opp["lh"] - me["lh"] >= 10:
            out.append({"t": 600, "kind": "lane_cs",
                        "text": f"к 10-й минуте {me['lh']} добиваний против {opp['lh']} у {_hero_name(opp['hero'])}"})
    lost = [f for f in ctx["fights"] if f["lost"] == ("radiant" if p["radiant"] else "dire")]
    missed = [f for f in lost if p["hero"] in f["absent"]]
    if len(lost) >= 3 and len(missed) >= ABSENT_SHARE * len(lost):
        out.append({"t": missed[0]["start"] or 0, "kind": "missed_fights",
                    "text": f"не пришёл на {len(missed)} из {len(lost)} проигранных драк"})
    died_in = [f for f in lost if p["hero"] in f["died"]["radiant" if p["radiant"] else "dire"]]
    for f in died_in[:3]:
        out.append({"t": f["start"] or 0, "kind": "lost_fight",
                    "text": f"умер в проигранной драке на {_mmss(f['start'] or 0)}: разница по золоту в ней {abs(f['swing']) / 1000:.1f}k"})
    out.sort(key=lambda m: m["t"])
    return out


def _mmss(t: float) -> str:
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"


def _hero_name(h: int) -> str:
    return (constants.hero_by_id().get(h) or {}).get("name") or str(h)


def map_points(od: dict, players: list[dict]) -> dict:
    """Deaths (from the fights) and wards on OpenDota's map cells."""
    order = [p.get("hero_id") for p in od.get("players") or []]
    side = {p["hero"]: p["radiant"] for p in players}
    deaths = []
    for f in od.get("teamfights") or []:
        for hero, x in zip(order, f.get("players") or []):
            for xs, ys in (x.get("deaths_pos") or {}).items():
                for y, n in (ys or {}).items():
                    try:
                        deaths.append({"hero": hero, "radiant": side.get(hero), "x": float(xs), "y": float(y),
                                       "n": int(n), "t": f.get("start")})
                    except (TypeError, ValueError):
                        continue
    wards = []
    for o in od.get("players") or []:
        hero = o.get("hero_id")
        for kind, key in (("obs", "obs_log"), ("sen", "sen_log")):
            for w in o.get(key) or []:
                if w.get("x") is None or w.get("y") is None:
                    continue
                wards.append({"hero": hero, "radiant": side.get(hero), "kind": kind, "x": w["x"], "y": w["y"], "t": w.get("time")})
    return {"deaths": deaths, "wards": wards}


def objectives(od: dict) -> list[dict]:
    """Roshan kills and towers for the gold chart."""
    out = []
    for o in od.get("objectives") or []:
        kind = o.get("type") or ""
        if kind == "CHAT_MESSAGE_ROSHAN_KILL":
            out.append({"t": o.get("time"), "kind": "roshan", "radiant": o.get("team") == 2})
        elif kind == "building_kill" and "tower" in (o.get("key") or ""):
            out.append({"t": o.get("time"), "kind": "tower", "radiant": "badguys" in (o.get("key") or "")})
    return out


def detail(raw: dict, players: list[dict]) -> dict | None:
    od = raw.get("opendota") or {}
    if not od.get("version"):
        return None      # not parsed: no minutes, positions or fights
    ctx = {"lanes": lanes(od, players), "fights": fights(od, players), "items": items(od, players)}
    return {
        "lanes": ctx["lanes"], "fights": ctx["fights"],
        "items": {str(h): v for h, v in ctx["items"].items()},
        "mistakes": {str(p["hero"]): mistakes(p, ctx) for p in players},
        "map": map_points(od, players), "objectives": objectives(od),
    }
