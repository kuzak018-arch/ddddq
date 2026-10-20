"""Is my game going well? Net worth and last hits now against what top players had on this hero.

From what Dota sends over GSI (gold, GPM, last hits, the clock; `net_worth` when the cfg carries
it, else an estimate from GPM) — enemies' numbers are not sent to a player and are not guessed.
- net worth: the median of the hero's Divine+/Immortal matches of this patch at the same minute
  (the per-minute curves of «Игры топов», position by position); needs a few cached matches;
- last hits per minute: OpenDota's per-hero benchmark percentiles (data/benchmarks, kept a day),
  only for positions 1-3 and from minute 4 (earlier the numbers say nothing).
Nothing here touches the network on the request path: the benchmark loads in the background.
"""

from __future__ import annotations

import json
import statistics
import threading
import time

from . import config, topgames
from .data.http import OpenDota

DIR = config.DATA / "benchmarks"
TTL = 24 * 3600
MIN_MINUTE = 4            # earlier, last hits and gold per minute are noise
MIN_CURVES = 5            # top matches needed for a net worth comparison
BAD = 0.85                # below 85% of the top median is «behind»
GOOD = 1.10               # above 110% is «ahead»
LH_LOW = 0.30             # last hits per minute under the 30th percentile of the hero: «few»
FARMING = (1, 2, 3)       # positions whose last hits matter
_lock = threading.Lock()
_loading: set[int] = set()


# ---------- net worth against the top curves ---------------------------------------------------

def curve_median(hero_id: int, pos: int, minute: int) -> tuple[float | None, int]:
    """(median net worth at `minute`, matches it is taken from) for the hero on the position."""
    since = topgames.patch_start()
    values = []
    for source in ("immortal", "divine"):
        for r in topgames._read(source, hero_id)["matches"]:
            curve = r.get("curve")
            if (r.get("t") or 0) >= since and r.get("pos") == pos and r.get("curve_kind") == "networth" \
                    and isinstance(curve, list) and len(curve) > minute and curve[minute]:
                values.append((r["m"], curve[minute]))
    unique = list({m: v for m, v in values}.values())
    return (statistics.median(unique), len(unique)) if unique else (None, 0)


def networth_pace(live: dict, hero_id: int, pos: int) -> dict | None:
    minute = int((live.get("clock") or 0) // 60)
    if minute < MIN_MINUTE:
        return None
    now = live.get("net_worth")
    estimated = now is None
    if estimated:
        if not live.get("gpm"):
            return None
        now = 625 + live["gpm"] * (live["clock"] / 60)   # starting gold + the average earned
    top, n = curve_median(hero_id, pos, minute)
    if top is None or n < MIN_CURVES:
        return None
    ratio = now / top
    return {"minute": minute, "now": round(now), "top": round(top), "diff": round(now - top), "ratio": round(ratio, 2),
            "games": n, "estimated": estimated,
            "verdict": "bad" if ratio < BAD else "good" if ratio >= GOOD else "ok"}


# ---------- last hits per minute against OpenDota's benchmarks ---------------------------------

def _file(hero_id: int):
    return DIR / f"{hero_id}.json"


def _load(hero_id: int) -> dict | None:
    try:
        data = json.loads(_file(hero_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data


def _fetch(hero_id: int) -> None:
    try:
        od = OpenDota()
        try:
            res = (od.get("/benchmarks", {"hero_id": hero_id}) or {}).get("result") or {}
        finally:
            od.close()
        DIR.mkdir(parents=True, exist_ok=True)
        _file(hero_id).write_text(json.dumps({"fetched": time.time(), "lh": res.get("last_hits_per_min") or [],
                                              "gpm": res.get("gold_per_min") or []}), encoding="utf-8")
    except Exception:  # noqa: BLE001 - no benchmark is no hint, never an error in a match
        pass
    finally:
        with _lock:
            _loading.discard(hero_id)


def benchmark(hero_id: int) -> dict | None:
    """The cached benchmark; starts a background download when there is none or it is a day old."""
    data = _load(hero_id)
    if (not data or time.time() - data.get("fetched", 0) > TTL):
        with _lock:
            if hero_id not in _loading:
                _loading.add(hero_id)
                threading.Thread(target=_fetch, args=(hero_id,), daemon=True, name=f"benchmark-{hero_id}").start()
    return data


def _value_at(rows: list[dict], percentile: float) -> float | None:
    best = min(rows, key=lambda r: abs(r.get("percentile", 0) - percentile), default=None)
    return best["value"] if best else None


def percentile_of(rows: list[dict], value: float) -> int | None:
    """Roughly which percentile of the hero's players this value is (by the benchmark's steps)."""
    rows = sorted(rows, key=lambda r: r["percentile"])
    if not rows:
        return None
    below = [r["percentile"] for r in rows if r["value"] <= value]
    return round(100 * max(below)) if below else 0


def last_hits_pace(live: dict, hero_id: int, pos: int) -> dict | None:
    if pos not in FARMING or live.get("last_hits") is None:
        return None
    minutes = (live.get("clock") or 0) / 60
    if minutes < MIN_MINUTE:
        return None
    data = benchmark(hero_id)
    rows = (data or {}).get("lh") or []
    low = _value_at(rows, LH_LOW)
    if not low:
        return None
    per_min = live["last_hits"] / minutes
    median = _value_at(rows, 0.5)
    return {"minute": int(minutes), "last_hits": live["last_hits"], "per_min": round(per_min, 1),
            "median": round(median, 1) if median else None, "percentile": percentile_of(rows, per_min),
            "expected": round(median * minutes) if median else None, "few": per_min < low}


def pace(live: dict | None, hero_id: int | None, pos: int | None) -> dict | None:
    """{networth, last_hits} for the overlay; None parts when there is nothing to compare with."""
    if not live or not hero_id or not pos:
        return None
    nw = networth_pace(live, hero_id, pos)
    lh = last_hits_pace(live, hero_id, pos)
    return {"networth": nw, "last_hits": lh} if nw or lh else None
