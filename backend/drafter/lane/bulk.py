"""Download lane data for the user's pool in the background ("скачать данные линий"). An option:
off until the user starts it; the lane view loads any pair on its own when it is opened.

Stratz has ready lane outcomes per pair (outcome.py, one request per hero and position), but no
minute-by-minute numbers per pair, so those come from matches, several per request (pairs.py).
This job collects BULK_TARGET matches (as many as opening the pair would) for the user's pool
heroes (their usual position) against their most frequent lane opponents only.

How often a pair meets: matches of our base (Legend+) with the two heroes on opposite teams,
times the share of games each plays that position (expected matches of that lane). Pairs expected
to have fewer than RARE matches are skipped: there is nothing to download for them.

The hourly budget is shared with everything else: the job keeps BACKGROUND_FLOOR requests per
hour free, and when it reaches that floor it waits and tries again. A pair whose matches run out
is remembered for a week, so a restart does not ask for it again.

The job survives restarts of the app or the PC: whatever is downloaded stays in the pair caches,
and the wish to download is kept in STATE_FILE until the job finishes or the user stops it. On the
next start the backend picks the job up again after RESUME_DELAY_S (on-demand requests go first),
and pairs that already have their matches are passed over without a request.
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

BULK_TARGET = service.TARGET   # matches per pair: the same as opening the pair
POOL_MAIN = 12              # pool hero: this many opponents in the main facing position ...
POOL_SECOND = 5             # ... and this many in the second one
POOL_SIZE = 8
RARE = 30                   # expected matches of the lane in our base below this: not worth a download
WAIT_S = 600                # budget floor reached: wait this long, then try again
EXHAUSTED_DAYS = 7
RESUME_DELAY_S = 90         # after the app starts, wait this long before picking an unfinished job up

STATE_FILE = pairs.CACHE / "bulk.json"
COUNTS_FILE = pairs.CACHE / "pair_counts.npz"

_state: dict = {"status": "idle"}
_stop = threading.Event()
_thread: threading.Thread | None = None
_guard = threading.Lock()
_resume: threading.Timer | None = None


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
    """Pairs to download: each pool hero against its most frequent lane opponents, most frequent first."""
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
    return out


# ---------- the job ----------------------------------------------------------------------------

def _saved() -> dict:
    if STATE_FILE.exists():
        try:
            d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}
    return {}


def _save(**fields) -> None:
    d = _saved() | fields
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _exhausted() -> dict[str, float]:
    return _saved().get("exhausted", {})


def _save_exhausted(ex: dict[str, float]) -> None:
    _save(exhausted=ex)


def wanted() -> bool:
    """The user started the job and it has neither finished nor been stopped by them."""
    return bool(_saved().get("wanted"))


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
                              floor=sm.BACKGROUND_FLOOR,
                              progress=lambda have, tgt, n: st.update(have=have, requests=st.get("requests_before", 0) + n))
                st["requests_before"] = st.get("requests_before", 0) + info.get("requests", 0)
                st["requests"] = st["requests_before"]
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
        if not _stop.is_set():
            _save(wanted=False)  # everything is there: nothing to pick up after a restart
        st.update(status="stopped" if _stop.is_set() else "done", current=None)
    except Exception as e:  # keep the app alive, show what went wrong
        st.update(status="failed", error=f"{type(e).__name__}: {e}")


def start(pos_mat, resumed: bool = False) -> dict:
    global _thread
    with _guard:
        if _thread and _thread.is_alive():
            return status()
        if not config.settings().stratz_token:
            raise RuntimeError("нет токена Stratz")
        _save(wanted=True)
        _stop.clear()
        _state.clear()
        _state.update(status="planning", started=time.time(), error=None, resumed=resumed)
        _thread = threading.Thread(target=_run, args=(pos_mat,), name="lane-bulk", daemon=True)
        _thread.start()
    return status()


def stop() -> dict:
    """The user stops the job: it is not picked up again after a restart."""
    _save(wanted=False)
    _cancel_resume()
    _stop.set()
    return status()


def shutdown() -> None:
    """The app exits: stop the job but keep the wish, so the next start continues it."""
    _cancel_resume()
    _stop.set()


def resume_later(get_pos_mat, delay: float = RESUME_DELAY_S) -> bool:
    """On app start: if the user's job was not finished, start it again after `delay` seconds.
    Returns whether a resume is scheduled. Without a token or a model it quietly waits for the
    next start; the wish stays."""
    global _resume
    if not wanted() or not config.settings().stratz_token:
        return False

    def go() -> None:
        try:
            start(get_pos_mat(), resumed=True)
        except Exception as e:  # no model yet, token gone: try again on the next start
            print(f"данные линий не продолжены: {type(e).__name__}: {e}", flush=True)

    _cancel_resume()
    _resume = threading.Timer(delay, go)
    _resume.daemon = True
    _resume.start()
    _state.update(status="idle", resume_scheduled=time.time() + delay)
    return True


def _cancel_resume() -> None:
    global _resume
    if _resume is not None:
        _resume.cancel()
        _resume = None
        _state.pop("resume_scheduled", None)


def status() -> dict:
    out = {k: v for k, v in _state.items()}
    out["limits"] = dict(stratz.limits)
    out["target"] = BULK_TARGET
    out["batch"] = pairs.batch_state()
    out["wanted"] = wanted()
    return out
