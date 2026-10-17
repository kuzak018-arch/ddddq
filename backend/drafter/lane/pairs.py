"""Matches of one pair of heroes on opposite teams, with both heroes' first minutes from Stratz.

Candidates are our OpenDota ranked matches (current patch, Legend+, 15+ minutes) with the two
heroes on opposite teams. Stratz parses older matches more often, so matches older than a week go
first. One request per match; both heroes' networth, experience, last hits, level-up times and
purchases for the first STORE_MINUTES minutes are cached per pair (unordered) in
data/stratz/lane_pairs/<lo>_<hi>.jsonl, unparsed matches too, so nothing is asked twice.

A match counts for "A at position pa against B at position pb" only if both played those
positions and stood on the same physical lane (Radiant safe lane is Dire's off lane).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from itertools import accumulate
from pathlib import Path

import polars as pl

from .. import config
from ..data import matches, stratz
from ..data import stratz_matches as sm

CACHE = config.DATA / "stratz" / "lane_pairs"
STORE_MINUTES = 20
PREFER_AGE_DAYS = 7

_locks: dict[tuple[int, int], threading.Lock] = {}
_guard = threading.Lock()

_Q = """{ match(id: %d) { id startDateTime durationSeconds players { heroId isRadiant position lane isVictory
  stats { networthPerMinute experiencePerMinute lastHitsPerMinute level itemPurchases { time itemId } } } } }"""


def _key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _path(a: int, b: int) -> Path:
    lo, hi = _key(a, b)
    return CACHE / f"{lo}_{hi}.jsonl"


def _lock(a: int, b: int) -> threading.Lock:
    with _guard:
        return _locks.setdefault(_key(a, b), threading.Lock())


def load(a: int, b: int) -> list[dict]:
    p = _path(a, b)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # half-written last line after a crash
    return out


def _append(a: int, b: int, rec: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    with _lock(a, b), _path(a, b).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")


def candidates(a: int, b: int, exclude: set[int]) -> list[int]:
    files = sorted(matches.PAGES.glob("*.parquet"))
    if not files:
        return []
    now = int(time.time())
    radiant = [f"r{i}" for i in range(5)]
    dire = [f"d{i}" for i in range(5)]
    has = lambda h, cols: pl.any_horizontal([pl.col(c) == h for c in cols])
    df = (pl.scan_parquet(files)
          .filter((pl.col("avg_rank_tier") >= sm.MIN_RANK_TIER) & (pl.col("duration") >= matches.MIN_DURATION)
                  & (pl.col("start_time") <= now - sm.MIN_AGE_DAYS * 86400)
                  & ((has(a, radiant) & has(b, dire)) | (has(a, dire) & has(b, radiant))))
          .select("match_id", "start_time").unique("match_id").collect())
    rows = sorted(df.iter_rows(), key=lambda r: (r[1] > now - PREFER_AGE_DAYS * 86400, -r[1]))
    return [m for m, _ in rows if m not in exclude]


def _player(p: dict, item_ids: dict[int, str]) -> dict:
    s = p.get("stats") or {}
    pos = p.get("position") or ""
    return {
        "r": bool(p.get("isRadiant")), "pos": int(pos[-1]) if pos.startswith("POSITION_") else None,
        "lane": p.get("lane"), "w": bool(p.get("isVictory")),
        "nw": (s.get("networthPerMinute") or [])[:STORE_MINUTES + 1],
        # experience and last hits come per minute: stored as running totals
        "xp": list(accumulate(s.get("experiencePerMinute") or []))[:STORE_MINUTES + 1],
        "lh": list(accumulate(s.get("lastHitsPerMinute") or []))[:STORE_MINUTES + 1],
        "lvl": (s.get("level") or [])[:12],    # time each level was reached, level 1 first
        "items": [[x["time"], item_ids.get(x["itemId"], str(x["itemId"]))]
                  for x in s.get("itemPurchases") or [] if x["time"] <= STORE_MINUTES * 60],
    }


def fetch_match(sz: stratz.Stratz, match_id: int, a: int, b: int) -> dict:
    item_ids, _ = sm._id_maps()
    m = sz.q(_Q % match_id)["match"] or {}
    ps = {p["heroId"]: p for p in m.get("players") or [] if p["heroId"] in (a, b)}
    if len(ps) < 2 or not all(((p.get("stats") or {}).get("networthPerMinute")) for p in ps.values()):
        return {"m": match_id, "unparsed": True}
    return {"m": match_id, "t": m.get("startDateTime"), "dur": m.get("durationSeconds"),
            "p": {str(h): _player(p, item_ids) for h, p in ps.items()}}


# physical lane: Radiant's safe lane is the bottom one, Dire's safe lane is the top one
_PHYSICAL = {(True, "SAFE_LANE"): "bot", (True, "OFF_LANE"): "top", (False, "SAFE_LANE"): "top",
             (False, "OFF_LANE"): "bot", (True, "MID_LANE"): "mid", (False, "MID_LANE"): "mid"}


def usable(rec: dict, a: int, pa: int, b: int, pb: int) -> bool:
    if rec.get("unparsed"):
        return False
    x, y = rec["p"].get(str(a)), rec["p"].get(str(b))
    if not x or not y or x["r"] == y["r"] or x["pos"] != pa or y["pos"] != pb:
        return False
    lane_x, lane_y = _PHYSICAL.get((x["r"], x["lane"])), _PHYSICAL.get((y["r"], y["lane"]))
    return lane_x is not None and lane_x == lane_y


def collect(a: int, pa: int, b: int, pb: int, target: int, *, stop: threading.Event | None = None,
            progress: Callable[[int, int, int], None] | None = None, max_requests: int | None = None,
            floor: int = sm.FOREGROUND_FLOOR, info: dict | None = None) -> int:
    """Fetch matches of the pair until `target` usable ones are cached (or candidates, the request
    cap or the token's hourly budget down to `floor` run out). Returns how many usable matches
    there are; `info` gets the number of candidates and why it stopped: target, budget, stopped,
    exhausted (no more matches of the pair in our base) or cap."""
    info = {} if info is None else info
    have = load(a, b)
    count = sum(usable(r, a, pa, b, pb) for r in have)
    info.update(candidates=None, reason="target")
    if count >= target:
        return count
    ids = candidates(a, b, {r["m"] for r in have})
    cap = max_requests or target * 3
    info["candidates"] = len(ids)
    if not ids:
        info["reason"] = "exhausted"
        return count
    sz = stratz.Stratz(min_interval=0.45)
    try:
        for n, mid in enumerate(ids[:cap], 1):
            if stop and stop.is_set():
                info["reason"] = "stopped"
                break
            if not sm._budget_ok(floor):
                info["reason"] = "budget"
                break
            try:
                rec = fetch_match(sz, mid, a, b)
            except RuntimeError:
                continue
            _append(a, b, rec)
            count += usable(rec, a, pa, b, pb)
            if progress:
                progress(count, target, n)
            if count >= target:
                info["reason"] = "target"
                break
        else:
            info["reason"] = "exhausted" if len(ids) <= cap else "cap"
    finally:
        sz.close()
    return count
