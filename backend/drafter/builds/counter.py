"""Situational items against a concrete enemy draft, each with a reason."""

from __future__ import annotations

import yaml

from .. import config
from ..data import constants
from . import tags as hero_tags

RULES = config.SHARED / "build_rules.yaml"


def _rules() -> list[dict]:
    return yaml.safe_load(RULES.read_text(encoding="utf-8"))


def _core_share(hero_id: int, pos_mat) -> float:
    if pos_mat is None:
        return 0.6
    return float(pos_mat[hero_id, :3].sum())


RARE_ON_HERO = 0.01  # bought in <1% of this hero's games on this position: probably a poor fit


def against(enemies: list[int], pos: int, pos_mat=None, hero_items: dict[str, float] | None = None,
            top: int = 6) -> list[dict]:
    """Item recommendations for position `pos` vs `enemies`, most urgent first.
    pos_mat (hero x position shares) makes 'core' rules weigh enemy cores more.
    hero_items (item -> purchase share on our hero, from Stratz) pushes down items the hero
    almost never builds, so another answer to the same threat comes first."""
    by_id = constants.hero_by_id()
    items = constants._load("items")
    tag_table = hero_tags.load()
    found: dict[str, dict] = {}
    for rule in _rules():
        total, who = 0.0, []
        for e in enemies:
            s = tag_table.get(by_id[e]["key"], {}).get(rule["tag"], 0.0)
            if not s:
                continue
            w = _core_share(e, pos_mat) if rule["weight"] == "core" else 1.0
            total += s * w
            who.append((s * w, by_id[e]["name"]))
        if total < rule["min"]:
            continue
        heroes = ", ".join(n for _, n in sorted(who, reverse=True))
        urgency = total / rule["min"]
        for rank, key in enumerate(rule["items"].get(pos, [])):
            if key not in items or key in constants.RETIRED_ITEMS:
                continue
            score = urgency / (1 + 0.5 * rank)
            share = None if hero_items is None else hero_items.get(key, 0.0)
            if share is not None and share < RARE_ON_HERO and key not in ("dust", "ward_sentry", "gem"):
                score *= 0.25
            rec = found.get(key)
            reason = {"tag": rule["tag"], "text": rule["why"].format(heroes=heroes), "score": round(score, 2)}
            if rec is None:
                found[key] = {"item": key, "name": items[key]["dname"], "cost": items[key].get("cost"),
                              "score": score, "hero_share": share, "reasons": [reason]}
            else:
                rec["score"] += 0.5 * score   # several threats answered by one item
                rec["reasons"].append(reason)
    out = sorted(found.values(), key=lambda r: -r["score"])
    for r in out:
        r["score"] = round(r["score"], 2)
    return out[:top]
