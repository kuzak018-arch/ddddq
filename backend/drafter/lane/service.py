"""Lane matchup for the API: the outcome right away, the minute-by-minute picture loaded on demand.

Opening a pair starts loading its matches in the background if fewer than TARGET are cached; the
UI polls while status == "loading" and the curves appear from analysis.MIN_GAMES matches.
"""

from __future__ import annotations

import os
import threading
import time
from itertools import permutations

from .. import config
from ..data import stratz_matches as sm
from . import analysis, outcome, pairs

TARGET = 100
RETRY_AFTER = 3600          # a load that stopped short is tried again after this long

# who stands against whom: my position -> enemy positions on my lane, the main opponent first
LANE_OPPONENTS = {1: (3, 4), 2: (2,), 3: (1, 5), 4: (5, 1), 5: (4, 3)}

_jobs: dict[tuple, dict] = {}
_guard = threading.Lock()


def _no_network() -> bool:
    return os.environ.get("DRAFTER_NO_BUILD_LOAD") == "1"   # tests: never hit the network


def _run(key: tuple, target: int) -> None:
    a, pa, b, pb = key
    job = _jobs[key]
    try:
        have = pairs.collect(a, pa, b, pb, target, stop=job["stop"],
                             progress=lambda have, tgt, n: job.update(have=have, requests=n))
        note = None
        if have < target and not job["stop"].is_set():
            note = ("Лимит запросов Stratz на этот час исчерпан — догружу позже."
                    if not sm._budget_ok(sm.FOREGROUND_FLOOR) else "Больше матчей этой пары в базе нет.")
        job.update(have=have, status="done", note=note)
    except Exception as e:  # network trouble etc.: show it, keep what is cached
        job.update(status="failed", error=f"{type(e).__name__}: {e}")


def ensure_loading(key: tuple, target: int = TARGET) -> dict:
    with _guard:
        job = _jobs.get(key)
        if job and (job["status"] == "loading" or time.time() - job["started"] < RETRY_AFTER):
            return job
        job = {"status": "loading", "have": 0, "target": target, "requests": 0, "error": None, "note": None,
               "stop": threading.Event(), "started": time.time()}
        _jobs[key] = job
    threading.Thread(target=_run, args=(key, target), name=f"lane-{'-'.join(map(str, key))}", daemon=True).start()
    return job


def get(a: int, pa: int, b: int, pb: int, bracket: str, load: bool = True) -> dict:
    load = load and not _no_network() and bool(config.settings().stratz_token)
    out: dict = {"hero": a, "pos": pa, "enemy": b, "enemy_pos": pb, "target": TARGET}
    try:
        out["outcome"], out["outcome_error"] = outcome.get(a, pa, b, bracket, load=load), None
    except RuntimeError as e:
        out["outcome"], out["outcome_error"] = None, str(e)
    key = (a, pa, b, pb)
    res = analysis.analyze(pairs.load(a, b), a, pa, b, pb)
    job = _jobs.get(key)
    if load and res["games"] < TARGET:
        job = ensure_loading(key)
    out.update(status="loading" if job and job["status"] == "loading" else "ready", games=res["games"],
               progress={"have": res["games"], "target": TARGET, "requests": job["requests"] if job else 0},
               error=job.get("error") if job else None,
               note=job.get("note") if job and res["games"] < TARGET else None,
               analysis=res)
    return out


def assign_positions(enemies: list[int], pos_mat) -> dict[int, int]:
    """Most likely position of each enemy hero (distinct positions, by the heroes' position shares)."""
    enemies = enemies[:5]
    best, best_p = {}, -1.0
    for perm in permutations(range(5), len(enemies)):
        p = 1.0
        for h, pos in zip(enemies, perm):
            p *= float(pos_mat[h, pos]) + 1e-6
        if p > best_p:
            best, best_p = {h: pos + 1 for h, pos in zip(enemies, perm)}, p
    return best


def opponents(pos: int, enemies: list[int], pos_mat) -> list[dict]:
    """Enemies on my lane (main opponent first), then the rest, each with its likely position."""
    where = assign_positions(enemies, pos_mat)
    lane = LANE_OPPONENTS[pos]
    order = sorted(enemies, key=lambda h: lane.index(where[h]) if where[h] in lane else 9)
    out = [{"hero": h, "pos": where[h], "on_lane": where[h] in lane, "main": False} for h in order]
    if out and out[0]["on_lane"]:
        out[0]["main"] = True
    return out


def stop_all() -> None:
    for job in _jobs.values():
        job["stop"].set()
