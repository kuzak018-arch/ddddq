"""Stratz GraphQL: hero positions, item purchases, skill order and talents by rank bracket.

Stratz aggregates parsed public matches per week (the latest full week by default) and,
unlike OpenDota, knows each player's position 1-5. Limits on a default token (from the
response headers): 8/s, 150/min, 1500/h, 15000/day — one request per hero stays far below.
"""

from __future__ import annotations

import json
import threading
import time

import httpx

from .. import config
from . import constants

DIR = config.DATA / "stratz"
POSITIONS = ["POSITION_1", "POSITION_2", "POSITION_3", "POSITION_4", "POSITION_5"]
BRACKETS = ["HERALD_GUARDIAN", "CRUSADER_ARCHON", "LEGEND_ANCIENT", "DIVINE_IMMORTAL"]
MIN_POS_SHARE = 0.08  # fetch builds only for positions the hero is really played on


def bracket_for(rank_tier: int | None) -> str:
    tier = (rank_tier or 50) // 10
    return BRACKETS[min(max((tier - 1) // 2, 0), 3)]


# Requests left on the token, from the last response's headers (shared by all clients in the process).
# Background prefetch looks at it and steps aside, so on-demand loading never runs out.
limits: dict[str, int] = {}
_pace = threading.Lock()
_last_call = [0.0]


class Stratz:
    def __init__(self, min_interval: float = 0.6):
        token = config.settings().stratz_token
        if not token:
            raise RuntimeError("нет STRATZ_TOKEN в .env")
        self.http = httpx.Client(timeout=90, headers={"Authorization": f"Bearer {token}", "User-Agent": "STRATZ_API"})
        self.min_interval = min_interval

    def close(self):
        self.http.close()

    def q(self, query: str, retries: int = 5) -> dict:
        for attempt in range(retries):
            with _pace:  # one global pace across threads: the token's per-second/minute limits are shared
                wait = self.min_interval - (time.monotonic() - _last_call[0])
                if wait > 0:
                    time.sleep(wait)
                _last_call[0] = time.monotonic()
            try:
                r = self.http.post(config.STRATZ, json={"query": query})
            except httpx.TransportError:
                time.sleep(2 ** attempt)
                continue
            for key in ("minute", "hour", "day"):
                v = r.headers.get(f"x-ratelimit-remaining-{key}")
                if v is not None and v.lstrip("-").isdigit():
                    limits[key] = int(v)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(min(60, 5 * (attempt + 1) ** 2))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Stratz HTTP {r.status_code}: {r.text[:500]}")
            body = r.json()
            if body.get("errors"):
                raise RuntimeError(f"Stratz: {json.dumps(body['errors'], ensure_ascii=False)[:500]}")
            return body["data"]
        raise RuntimeError("Stratz не ответил после повторов")


def _save(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


def fetch(bracket: str, log=print) -> None:
    """Positions and bans for all heroes, then builds per hero and position.
    banDay demands a heroId but returns every hero regardless, so any id works there."""
    sz = Stratz()
    out = DIR / bracket
    try:
        d = sz.q(f"""{{ heroStats {{
            pos: stats(bracketBasicIds: [{bracket}], groupByPosition: true) {{ heroId position matchCount winCount week }}
            ban: banDay(heroId: 1, bracketBasicIds: [{bracket}]) {{ heroId matchCount }}
        }} }}""")["heroStats"]
        _save(out / "positions.json", d["pos"])
        _save(out / "bans.json", d["ban"])
        week = max(r["week"] for r in d["pos"])
        totals: dict[int, dict[str, int]] = {}
        for r in d["pos"]:
            totals.setdefault(r["heroId"], {})[r["position"]] = r["matchCount"]
        log(f"Stratz {bracket}, неделя {week}: позиции и баны для {len(totals)} героев")

        for i, h in enumerate(constants.hero_index(), 1):
            per_pos = totals.get(h["id"], {})
            n = sum(per_pos.values()) or 1
            parts = []
            # itemFullPurchase rows are per (item, minute); without matchLimit Stratz drops rows under its
            # default threshold, which erased most items for supports (Bane pos 4: 3 items instead of 10+).
            for p in POSITIONS:
                if per_pos.get(p, 0) / n < MIN_POS_SHARE:
                    continue
                a = f"heroId: {h['id']}, bracketBasicIds: [{bracket}], positionIds: [{p}]"
                parts.append(f"""
                    {p}_start: itemStartingPurchase({a}) {{ itemId instance matchCount winCount wasGiven }}
                    {p}_full: itemFullPurchase({a}, matchLimit: 10) {{ itemId instance time matchCount winCount }}
                    {p}_boots: itemBootPurchase({a}) {{ itemId time matchCount winCount }}
                    {p}_neutral: itemNeutral({a}) {{ itemId matchCount winCount equippedMatchCount equippedMatchWinCount }}
                    {p}_talent: talent({a}) {{ abilityId matchCount winCount }}
                    {p}_amax: abilityMaxLevel({a}) {{ abilityId level matchCount winCount }}
                    {p}_amin: abilityMinLevel({a}) {{ abilityId level matchCount winCount }}""")
            if not parts:
                continue
            data = sz.q("{ heroStats {" + "".join(parts) + "} }")["heroStats"]
            by_pos: dict[str, dict] = {}
            for key, rows in data.items():
                p, kind = key.rsplit("_", 1)
                by_pos.setdefault(p, {})[kind] = rows
            for p in by_pos:
                by_pos[p]["matches"] = per_pos.get(p, 0)
            _save(out / "heroes" / f"{h['id']}.json", {"week": week, "positions": by_pos})
            if i % 20 == 0:
                log(f"  билды: {i}/{len(constants.hero_index())}")
        _save(out / "meta.json", {"week": week, "fetched": int(time.time())})
        log("готово")
    finally:
        sz.close()


def positions(bracket: str) -> dict[int, list[float]] | None:
    p = DIR / bracket / "positions.json"
    if not p.exists():
        return None
    acc: dict[int, list[int]] = {}
    for r in json.loads(p.read_text(encoding="utf-8")):
        if r["position"] in POSITIONS:
            acc.setdefault(r["heroId"], [0] * 5)[POSITIONS.index(r["position"])] += r["matchCount"]
    return {h: [c / sum(v) for c in v] for h, v in acc.items() if sum(v)}


def hero(bracket: str, hero_id: int) -> dict | None:
    p = DIR / bracket / "heroes" / f"{hero_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
