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

TARGET = 25                 # matches per pair loaded when it is opened (curves from analysis.MIN_GAMES)
RETRY_AFTER = 3600          # a load that stopped short is tried again after this long
OFFROLE_SHARE = 0.10        # a hero plays a position in fewer games than this -> not its position

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
        info: dict = {}
        have = pairs.collect(a, pa, b, pb, target, stop=job["stop"], info=info,
                             progress=lambda have, tgt, n: job.update(have=have, requests=n))
        job.update(have=have, status="done", note=_note(have, target, info), requests=info.get("requests", job["requests"]),
                   rare=have == 0 and info["reason"] == "exhausted")
    except Exception as e:  # network trouble etc.: show it, keep what is cached
        job.update(status="failed", error=f"{type(e).__name__}: {e}")


def _note(have: int, target: int, info: dict) -> str | None:
    if have >= target:
        return None
    if info.get("reason") == "budget":
        return "Лимит запросов Stratz на этот час исчерпан — догружу позже."
    if info.get("reason") == "cap":
        return "На этих позициях пара встречается редко: остальные матчи из базы — на других линиях. Догружу при следующем открытии."
    if info.get("reason") == "exhausted":
        return ("Матчей этой пары в нашей базе нет: пара слишком редкая." if have == 0
                else "Больше матчей этой пары в нашей базе нет.")
    return None


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
               progress={"have": res["games"], "target": TARGET, "requests": job["requests"] if job else 0,
                         "batch": pairs.batch_state()["size"]},
               error=job.get("error") if job else None,
               note=job.get("note") if job and res["games"] < TARGET else None,
               rare=bool(job and job.get("rare")), analysis=res)
    return out


def effective_pos(hero: int, pos: int, pos_mat) -> int:
    """My position for the lane: the chosen one, unless the hero almost never plays it (Axe with
    "carry" selected in the draft) — then the hero's usual position."""
    if pos_mat[hero, pos - 1] >= OFFROLE_SHARE:
        return pos
    return int(pos_mat[hero].argmax()) + 1


def lane_position(enemy: int, pos: int, pos_mat) -> int | None:
    """Where the enemy would stand on my lane: its likeliest position among those facing `pos`,
    or None if it plays none of them in OFFROLE_SHARE of its games (it does not lane against me)."""
    best = max(LANE_OPPONENTS[pos], key=lambda p: pos_mat[enemy, p - 1])
    return best if pos_mat[enemy, best - 1] >= OFFROLE_SHARE else None


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
    """Every enemy with its likely position in this draft (`pos`), whether it stands on my lane
    (`on_lane`: that position faces mine and the hero really plays it), and where it would stand
    if it did come to my lane (`lane_pos`, None if it never plays there). On-lane enemies first,
    the main opponent (the one in the first facing position) marked."""
    where = assign_positions(enemies, pos_mat)
    lane = LANE_OPPONENTS[pos]
    out = []
    for h in enemies:
        p = where[h]
        on = bool(p in lane and pos_mat[h, p - 1] >= OFFROLE_SHARE)
        out.append({"hero": h, "pos": p, "on_lane": on, "lane_pos": p if on else lane_position(h, pos, pos_mat),
                    "main": False})
    out.sort(key=lambda o: (not o["on_lane"], lane.index(o["pos"]) if o["on_lane"] else 9, o["lane_pos"] is None))
    if out and out[0]["on_lane"]:
        out[0]["main"] = True
    return out


def stop_all() -> None:
    for job in _jobs.values():
        job["stop"].set()
