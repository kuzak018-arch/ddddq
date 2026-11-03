"""Neutral items for a build: what drops at each tier, what every one does, and which ones the
hero's players end the game with.

The catalog is OpenDota's item constants: artifacts carry their tier (1–5), enchantments are the
`enhancement_*` items. What the hero's players hold is counted from every source the app already
has, without new requests:
  - Stratz `itemNeutral` per hero and position (bracket data, when Stratz fills it);
  - Stratz match timelines (`neutral0Id`, stratz_matches) for the hero on the position;
  - top players' games of the hero (`neutral` of each game, topgames).
The neutral slot at the end of a game is mostly the last tier the game reached, so the share is
taken within the tier: of the games that ended with a tier-3 artifact, how many had this one.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from functools import cache

from .. import config
from ..data import constants, stratz, stratz_matches

TIERS = (1, 2, 3, 4, 5)
# minute the tier opens (current patch: a Madstone tier every ten minutes, the last one late)
TIER_MINUTE = {1: 5, 2: 15, 3: 25, 4: 35, 5: 60}
TOP_PER_TIER = 3
MIN_TIER_GAMES = 5         # below this a tier's shares are not shown as data


def _fill(display: str, value: str) -> str:
    return re.sub(r"\s+", " ", display.replace("{value}", str(value))).replace("+ ", "+").strip()


def _entry(key: str, it: dict) -> dict:
    abilities = [{"title": a.get("title") or "", "type": a.get("type") or "",
                  "desc": re.sub(r"\s+", " ", a.get("description") or "").strip()} for a in it.get("abilities") or []]
    stats = [_fill(a["display"], a.get("value", "")) for a in it.get("attrib") or []
             if a.get("display") and str(a.get("value", "")).strip() not in ("", "0", "0 / 0 / 0 / 0")]
    return {"key": key, "name": it.get("dname") or key, "tier": it.get("tier"), "abilities": abilities,
            "stats": stats, "cooldown": it["cd"] if isinstance(it.get("cd"), (int, float)) and it["cd"] else None,
            "notes": (it.get("notes") or "").strip() or None}


@cache
def catalog() -> dict:
    """{"tiers": {tier: [artifact]}, "enchantments": [enchantment]} from the item constants."""
    items = constants._load("items")
    tiers: dict[int, list[dict]] = {t: [] for t in TIERS}
    enchant = []
    for key, it in items.items():
        if key in constants.RETIRED_ITEMS:
            continue
        if key.startswith("enhancement_"):
            enchant.append(_entry(key, it))
        elif it.get("tier") in TIERS and not it.get("cost"):
            tiers[it["tier"]].append(_entry(key, it))
    for t in tiers.values():
        t.sort(key=lambda e: e["name"])
    enchant.sort(key=lambda e: e["name"])
    return {"tiers": tiers, "enchantments": enchant}


def _topgames(hero_id: int) -> list[dict]:
    out = []
    root = config.DATA / "topgames"
    if not root.exists():
        return out
    for src in root.iterdir():
        p = src / f"{hero_id}.json"
        if not p.exists():
            continue
        try:
            out += json.loads(p.read_text(encoding="utf-8")).get("matches") or []
        except (OSError, ValueError):
            continue
    return out


def counts(hero_id: int, pos: int | None, bracket: str | None) -> tuple[dict[str, list[int]], list[str]]:
    """{item key: [games, wins]} of the neutral the hero's players held, and the sources used."""
    item_ids = {int(k): v for k, v in constants._load("item_ids").items() if k.isdigit()}
    acc: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    sources = []
    raw = stratz.hero(bracket, hero_id) if bracket else None
    if raw:
        positions = [stratz.POSITIONS[pos - 1]] if pos else list(raw["positions"])
        n = 0
        for p in positions:
            for r in (raw["positions"].get(p) or {}).get("neutral") or []:
                key = item_ids.get(r.get("itemId") or 0)
                g = r.get("equippedMatchCount") or r.get("matchCount") or 0
                if key and g:
                    acc[key][0] += g
                    acc[key][1] += r.get("equippedMatchWinCount") or r.get("winCount") or 0
                    n += g
        if n:
            sources.append("stratz")
    games = [r for r in stratz_matches.load(hero_id) if not r.get("unparsed") and (pos is None or r.get("pos") in (pos, None))]
    games += [m for m in _topgames(hero_id) if pos is None or m.get("pos") in (pos, None)]
    seen = set()
    for g in games:
        key = g.get("neutral")
        if not key or g.get("m") in seen:
            continue
        seen.add(g.get("m"))
        acc[key][0] += 1
        acc[key][1] += bool(g.get("w"))
    if seen:
        sources.append("matches")
    return dict(acc), sources


def for_hero(hero_id: int, pos: int | None = None, bracket: str | None = None) -> dict:
    """Every tier with its artifacts, the hero's popular ones first (share within the tier, win
    rate), and the enchantments the same way."""
    cat = catalog()
    have, sources = counts(hero_id, pos, bracket)

    def rank(entries: list[dict]) -> tuple[list[dict], int]:
        total = sum(have.get(e["key"], [0])[0] for e in entries)
        rows = []
        for e in entries:
            g, w = have.get(e["key"], [0, 0])
            rows.append({**e, "games": g, "share": round(g / total, 4) if total else None,
                         "wr": round(w / g, 4) if g >= MIN_TIER_GAMES else None})
        rows.sort(key=lambda r: (-r["games"], r["name"]))
        enough = total >= MIN_TIER_GAMES
        for i, r in enumerate(rows):
            r["popular"] = enough and i < TOP_PER_TIER and r["games"] > 0
        return rows, total

    tiers = []
    for t in TIERS:
        rows, total = rank(cat["tiers"][t])
        if rows:
            tiers.append({"tier": t, "minute": TIER_MINUTE[t], "games": total, "items": rows})
    ench, ench_total = rank(cat["enchantments"])
    return {"hero": hero_id, "pos": pos, "tiers": tiers, "enchantments": ench, "enchantment_games": ench_total,
            "sources": sources}
