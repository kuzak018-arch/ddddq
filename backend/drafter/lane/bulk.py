"""Download lane data for many pairs in the background ("скачать данные линий").

Stratz has ready lane outcomes per pair (outcome.py, one request per hero and position), but no
minute-by-minute numbers per pair, so those come from matches, one request each. This job walks
the pairs that matter most and collects BULK_TARGET matches of each:

1. the user's pool heroes (their usual position) against their most frequent lane opponents;
2. then the frequent core matchups (mid against mid, carry against offlaner): the most frequent
   pairs that together make up COVER of all such lane meetings (about 450 pairs, 3-4 days of the
   token's daily limit; all ~20 000 possible pairs would take years).

How often a pair meets: matches of our base (Legend+) with the two heroes on opposite teams,
times the share of games each plays that position (expected matches of that lane). Pairs expected
to have fewer than RARE matches are skipped: there is nothing to download for them.

The hourly budget is shared with everything else: the job keeps BACKGROUND_FLOOR requests per
hour free, and when it reaches that floor it waits and tries again. A pair whose matches run out
is remembered for a week, so a restart does not ask for it again.
"""

from __future__ import annotations

import json
import threading
import time

import numpy as np
import polars as pl

from .. import config
from ..data import matches, me, stratz
from ..data import stratz_matches as sm
from . import pairs, service

BULK_TARGET = 60            # matches per pair (the lane view tops a pair it shows up to service.TARGET)
POOL_MAIN = 12              # pool hero: this many opponents in the main facing position ...
POOL_SECOND = 5             # ... and this many in the second one
POOL_SIZE = 8
RARE = 30                   # expected matches of the lane in our base below this: not worth a download
COVER = 0.5                 # frequent core pairs: the top ones that make up this share of lane meetings
WAIT_S = 600                # budget floor reached: wait this long, then try again
EXHAUSTED_DAYS = 7

STATE_FILE = pairs.CACHE / "bulk.json"
COUNTS_FILE = pairs.CACHE / "pair_counts.npz"

_state: dict = {"status": "idle"}
_stop = threading.Event()
_thread: threading.Thread | None = None
_guard = threading.Lock()


# ---------- how often pairs meet ---------------------------------------------------------------

def pair_counts() -> np.ndarray:
    """[a, b] = Legend+ matches of our base with heroes a and b on opposite teams (symmetric).
    Cached until the match pages change."""
    files = sorted(matches.PAGES.glob("*.parquet"))
    sig = f"{len(files)}:{max((f.stat().st_mtime for f in files), default=0):.0f}"
    if COUNTS_FILE.exists():
        z = np.load(COUNTS_FILE)
        if str(z["sig"]) == sig:
            return z["counts"]
    k = 160
    total = np.zeros(k * k, dtype=np.int64)
    radiant = [f"r{i}" for i in range(5)]
    dire = [f"d{i}" for i in range(5)]
    for f in files:
        df = pl.read_parquet(f, columns=radiant + dire + ["avg_rank_tier"]).filter(
            pl.col("avg_rank_tier") >= sm.MIN_RANK_TIER)
        if not df.height:
            continue
        r = df.select(radiant).to_numpy().astype(np.int64)
        d = df.select(dire).to_numpy().astype(np.int64)
        idx = (r[:, :, None] * k + d[:, None, :]).ravel()
        total += np.bincount(idx[(idx >= 0) & (idx < k * k)], minlength=k * k)
    counts = total.reshape(k, k)
    counts = counts + counts.T
    COUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(COUNTS_FILE, counts=counts, sig=np.array(sig))
    return counts


def expected(counts: np.ndarray, pos_mat, a: int, pa: int, b: int, pb: int) -> float:
    """Matches of our base where a at pa stood against b at pb, roughly."""
    return float(counts[a, b] * pos_mat[a, pa - 1] * pos_mat[b, pb - 1])


def plan(pos_mat, pool: list[tuple[int, int]]) -> list[dict]:
    """Pairs to download, most useful first: pool heroes first, then frequent core matchups."""
    counts = pair_counts()
    n = min(counts.shape[0], pos_mat.shape[0])
    heroes = [h for h in range(1, n) if pos_mat[h].sum() > 0]
    out, seen = [], set()

    def add(a: int, pa: int, b: int, pb: int, why: str) -> None:
        key = (a, pa, b, pb)
        # mid against mid is the same lane from either side: one download serves both
        if pa == pb == 2:
            key = (min(a, b), 2, max(a, b), 2)
        e = expected(counts, pos_mat, a, pa, b, pb)
        if key in seen or a == b or e < RARE:
            return
        seen.add(key)
        out.append({"a": key[0], "pa": key[1], "b": key[2], "pb": key[3], "why": why, "expected": round(e)})

    for h, ph in pool:
        for k, pb in enumerate(service.LANE_OPPONENTS[ph]):
            ranked = sorted(heroes, key=lambda b: -expected(counts, pos_mat, h, ph, b, pb))
            for b in ranked[:POOL_MAIN if k == 0 else POOL_SECOND]:
                add(h, ph, b, pb, "pool")
    core = [(expected(counts, pos_mat, a, pa, b, pb), a, pa, b, pb)
            for pa, pb in ((2, 2), (1, 3), (3, 1)) for a in heroes for b in heroes
            if a != b and not (pa == pb == 2 and a > b)]
    total = sum(x[0] for x in core) or 1.0
    covered = 0.0
    for e, a, pa, b, pb in sorted(core, reverse=True):
        if covered >= COVER * total or e < RARE:
            break
        covered += e
        add(a, pa, b, pb, "all")
    return out


# ---------- the job ----------------------------------------------------------------------------

def _exhausted() -> dict[str, float]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8")).get("exhausted", {})
        except ValueError:
            return {}
    return {}


def _save_exhausted(ex: dict[str, float]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"exhausted": ex}), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _have(p: dict) -> int:
    return sum(pairs.usable(r, p["a"], p["pa"], p["b"], p["pb"]) for r in pairs.load(p["a"], p["b"]))


def _pool(pos_mat) -> list[tuple[int, int]]:
    top = sorted(me.hero_pool().get("heroes", {}).items(), key=lambda kv: -kv[1]["games"])[:POOL_SIZE]
    return [(h, int(pos_mat[h].argmax()) + 1) for h, _ in top]


def _run(pos_mat) -> None:
    st = _state
    try:
        st.update(status="planning")
        todo = plan(pos_mat, _pool(pos_mat))
        ex = _exhausted()
        week = time.time() - EXHAUSTED_DAYS * 86400
        st.update(status="running", total=len(todo), done=0, skipped=0, pool_total=sum(p["why"] == "pool" for p in todo))
        for i, p in enumerate(todo):
            if _stop.is_set():
                break
            key = f"{p['a']}_{p['pa']}_{p['b']}_{p['pb']}"
            if ex.get(key, 0) > week or _have(p) >= BULK_TARGET:
                st["done"] += 1
                st["skipped"] += 1
                continue
            st.update(current=p, index=i, have=_have(p))
            info: dict = {}
            while not _stop.is_set():
                info = {}
                pairs.collect(p["a"], p["pa"], p["b"], p["pb"], BULK_TARGET, stop=_stop, info=info,
                              floor=sm.BACKGROUND_FLOOR, progress=lambda have, tgt, n: st.update(have=have),
                              max_requests=BULK_TARGET * 3)
                if info["reason"] != "budget":
                    break
                # the hour's budget is down to the floor: wait, then let the next request read fresh limits
                st.update(status="waiting", resume_at=time.time() + WAIT_S)
                _stop.wait(WAIT_S)
                stratz.limits.pop("hour", None)
                st.update(status="running", resume_at=None)
            if info.get("reason") == "exhausted":
                ex[key] = time.time()
                _save_exhausted(ex)
            st["done"] += 1
        st.update(status="stopped" if _stop.is_set() else "done", current=None)
    except Exception as e:  # keep the app alive, show what went wrong
        st.update(status="failed", error=f"{type(e).__name__}: {e}")


def start(pos_mat) -> dict:
    global _thread
    with _guard:
        if _thread and _thread.is_alive():
            return status()
        if not config.settings().stratz_token:
            raise RuntimeError("нет токена Stratz")
        _stop.clear()
        _state.clear()
        _state.update(status="planning", started=time.time(), error=None)
        _thread = threading.Thread(target=_run, args=(pos_mat,), name="lane-bulk", daemon=True)
        _thread.start()
    return status()


def stop() -> dict:
    _stop.set()
    return status()


def status() -> dict:
    out = {k: v for k, v in _state.items()}
    out["limits"] = dict(stratz.limits)
    out["target"] = BULK_TARGET
    return out
