"""Matches of one pair of heroes on opposite teams, with both heroes' first minutes from Stratz.

Candidates are our OpenDota ranked matches (current patch, Legend+, 15+ minutes) with the two
heroes on opposite teams. Stratz parses older matches more often, so matches older than a week go
first. Several matches go in one request: Stratz's `matches(ids)` is for its admins only, so the
batch is one GraphQL query with an aliased `match(id)` per match (m0: match(id: …) m1: …), which
the token's limits count as one request. How many fit in one request Stratz does not document: the
batch starts at BATCH_START, grows while Stratz answers, halves when it refuses one as too big,
and what worked is kept in BATCH_FILE. Both heroes' networth, experience, last hits, level-up
times and purchases for the first STORE_MINUTES minutes are cached per pair (unordered) in
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
BATCH_FILE = CACHE / "batch.json"
BATCH_START = 10             # matches per request at first
BATCH_MAX = 30
USABLE_GUESS = 0.4           # share of a pair's matches where both stood on one lane at those positions
# a refusal that means "the query is too big", not a bad token or the rate limit
_TOO_BIG = ("complex", "cost", "too many", "exceed", "maximum", "depth", "HTTP 400", "HTTP 413", "timeout",
            "не ответил")

_locks: dict[tuple[int, int], threading.Lock] = {}
_guard = threading.Lock()

_FIELDS = """{ id startDateTime durationSeconds players { heroId isRadiant position lane isVictory
  stats { networthPerMinute experiencePerMinute lastHitsPerMinute level itemPurchases { time itemId } } } }"""
_Q = "{ match(id: %d) " + _FIELDS + " }"


def batch_query(ids: list[int]) -> str:
    return "{ " + " ".join(f"m{i}: match(id: {mid}) {_FIELDS}" for i, mid in enumerate(ids)) + " }"


def batch_state() -> dict:
    try:
        st = json.loads(BATCH_FILE.read_text(encoding="utf-8")) if BATCH_FILE.exists() else {}
    except ValueError:
        st = {}
    return {"size": BATCH_START, "max_ok": 0, "refused": None, **st}


def _save_batch(st: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    BATCH_FILE.write_text(json.dumps(st), encoding="utf-8")


def _too_big(e: Exception) -> bool:
    text = str(e)
    return any(w.lower() in text.lower() for w in _TOO_BIG)


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


def _record(m: dict | None, match_id: int, a: int, b: int, item_ids: dict) -> dict:
    m = m or {}
    ps = {p["heroId"]: p for p in m.get("players") or [] if p["heroId"] in (a, b)}
    if len(ps) < 2 or not all(((p.get("stats") or {}).get("networthPerMinute")) for p in ps.values()):
        return {"m": match_id, "unparsed": True}
    return {"m": match_id, "t": m.get("startDateTime"), "dur": m.get("durationSeconds"),
            "p": {str(h): _player(p, item_ids) for h, p in ps.items()}}


def fetch_match(sz: stratz.Stratz, match_id: int, a: int, b: int) -> dict:
    item_ids, _ = sm._id_maps()
    return _record(sz.q(_Q % match_id)["match"], match_id, a, b, item_ids)


def fetch_batch(sz: stratz.Stratz, ids: list[int], a: int, b: int, state: dict | None = None) -> tuple[list[dict], int]:
    """These matches in as few requests as Stratz takes. Returns the records (a match Stratz has
    not got comes back unparsed, as with one request) and the number of requests spent. The batch
    size learnt is written back to BATCH_FILE."""
    item_ids, _ = sm._id_maps()
    st = state if state is not None else batch_state()
    out: list[dict] = []
    spent = 0
    rest = list(ids)
    while rest:
        n = max(1, min(st["size"], len(rest)))
        chunk = rest[:n]
        spent += 1
        try:
            data, _errors = sz.q_all(batch_query(chunk), retries=2)
        except RuntimeError as e:
            if n > 1 and _too_big(e):
                st.update(refused=n, size=max(1, n // 2))
                _save_batch(st)
                continue
            raise
        out += [_record(data.get(f"m{i}"), mid, a, b, item_ids) for i, mid in enumerate(chunk)]
        rest = rest[n:]
        if n > st.get("max_ok", 0):
            st["max_ok"] = n
        # grow carefully up to just below the size Stratz refused
        ceiling = min(BATCH_MAX, (st["refused"] - 1) if st.get("refused") else BATCH_MAX)
        if n == st["size"] and st["size"] < ceiling:
            st["size"] = min(ceiling, st["size"] + 5)
        _save_batch(st)
    return out, spent


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
    cap = max_requests or 12             # requests, not matches
    info.update(candidates=len(ids), requests=0)
    if not ids:
        info["reason"] = "exhausted"
        return count
    st = batch_state()
    sz = stratz.Stratz(min_interval=0.45)
    asked = 0
    fetched = good = 0
    try:
        while True:
            if asked >= len(ids):
                info["reason"] = "exhausted"
                break
            if info["requests"] >= cap:
                info["reason"] = "cap"
                break
            if stop and stop.is_set():
                info["reason"] = "stopped"
                break
            if not sm._budget_ok(floor):
                info["reason"] = "budget"
                break
            # as many as should bring the rest of the target, judged by this pair's hit rate so far
            rate = max(0.15, good / fetched) if fetched >= 10 else USABLE_GUESS
            want = max(1, min(st["size"], round((target - count) / rate)))
            chunk = ids[asked:asked + want]
            asked += len(chunk)
            try:
                recs, spent = fetch_batch(sz, chunk, a, b, st)
            except RuntimeError as e:
                if "429" in str(e) or "401" in str(e) or "403" in str(e):
                    raise
                info["requests"] += 1
                continue                  # one bad chunk: skip it, go on with the next
            info["requests"] += spent
            for rec in recs:
                _append(a, b, rec)
                ok = usable(rec, a, pa, b, pb)
                count += ok
                good += ok
                fetched += 1
            if progress:
                progress(count, target, info["requests"])
            if count >= target:
                info["reason"] = "target"
                break
    finally:
        sz.close()
    info["batch"] = st["size"]
    return count
