"""Who wins the lane: Stratz `heroStats.laneOutcome`, aggregated over its current week.

One request returns the hero (at one position) against every hero it met on its lane, so a file
per hero and position is cached for a few days. `positionIds` filters the first hero's position;
the `position` field of the rows is the same for all of them and is ignored. Wins, draws and
losses don't add up to `matchCount` (some lanes are not rated), so shares are of rated lanes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .. import config
from ..data import stratz

DIR = config.DATA / "stratz" / "lane"
MAX_AGE = 3 * 86400
ALL = "ALL"                 # every bracket: used when the user's bracket has too few lanes of the pair
MIN_RATED = 60              # fewer rated lanes in the user's bracket -> also look at all brackets
RELIABLE = 150
MIN_VERDICT = 50            # fewer rated lanes: no verdict, "not enough data" (a 3-0 record is not "100%")


def _path(bracket: str, hero: int, pos: int) -> Path:
    return DIR / bracket / f"{hero}_{pos}.json"


def fetch(hero: int, pos: int, bracket: str) -> dict:
    flt = f"heroId: {hero}, isWith: false, positionIds: [POSITION_{pos}]"
    if bracket != ALL:
        flt += f", bracketBasicIds: [{bracket}]"
    sz = stratz.Stratz()
    try:
        rows = sz.q("""{ heroStats { laneOutcome(%s) { heroId2 week matchCount winCount drawCount lossCount
                    stompWinCount stompLossCount } } }""" % flt)["heroStats"]["laneOutcome"] or []
    finally:
        sz.close()
    data = {"fetched": time.time(), "week": max((r["week"] for r in rows), default=None),
            "rows": {str(r["heroId2"]): r for r in rows}}
    p = _path(bracket, hero, pos)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(p)
    return data


def _data(hero: int, pos: int, bracket: str, load: bool) -> dict | None:
    p = _path(bracket, hero, pos)
    cached = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    if load and (cached is None or time.time() - cached["fetched"] > MAX_AGE):
        try:
            return fetch(hero, pos, bracket)
        except RuntimeError:
            if cached is None:
                raise
    return cached


def summarize(row: dict | None, bracket: str, week: int | None) -> dict | None:
    if not row:
        return None
    w, d, l = row["winCount"], row["drawCount"], row["lossCount"]
    rated = w + d + l
    if not rated:
        return None
    return {"bracket": bracket, "week": week, "matches": row["matchCount"], "rated": rated,
            "win": w, "draw": d, "loss": l, "stomp_win": row["stompWinCount"], "stomp_loss": row["stompLossCount"],
            "win_share": round(w / rated, 3), "draw_share": round(d / rated, 3), "loss_share": round(l / rated, 3),
            "edge": round((w - l) / rated, 3), "enough": rated >= MIN_VERDICT, "reliable": rated >= RELIABLE,
            "min_verdict": MIN_VERDICT}


def get(hero: int, pos: int, enemy: int, bracket: str, load: bool = True) -> dict | None:
    """Lane outcome of `hero` at `pos` against `enemy` (from the hero's side), or None if Stratz has none.
    Raises RuntimeError if it had to ask Stratz and that failed."""
    data = _data(hero, pos, bracket, load)
    res = summarize((data or {}).get("rows", {}).get(str(enemy)), bracket, (data or {}).get("week"))
    if bracket != ALL and (res is None or res["rated"] < MIN_RATED):
        try:
            wide = _data(hero, pos, ALL, load)
        except RuntimeError:
            return res
        alt = summarize((wide or {}).get("rows", {}).get(str(enemy)), ALL, (wide or {}).get("week"))
        if alt and (res is None or alt["rated"] > res["rated"]):
            return alt
    return res
