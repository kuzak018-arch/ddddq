"""Builds for the API: match-based builds with on-demand loading, pool prefetch and the fallback.

Opening a hero starts loading its matches in the background (if the cache is short), the UI polls
and shows progress; builds appear from MIN_GAMES games and fill in as more arrive. Heroes from the
user's pool are prefetched to POOL_TARGET games, slowly, leaving the token's budget to on-demand
loading. Below MIN_GAMES the old aggregated build is shown, marked approximate.
"""

from __future__ import annotations

import os
import threading
import time
from collections import Counter

from .. import config
from ..data import abilities, constants, me, stratz, stratz_matches as sm
from . import sequences, standard

TARGET = 200
POOL_TARGET = 500
POOL_SIZE = 8
MIN_GAMES = 40
OFFROLE_SHARE = 0.10      # with fallback: a position the hero plays in <10% of games -> its main position

_jobs: dict[tuple, dict] = {}
_guard = threading.Lock()
publish = lambda **data: None   # set by the API to push progress over WebSocket


def pool_heroes(pos_mat=None) -> list[tuple[int, int]]:
    """(hero, position) for the user's most played heroes; position = where the hero is mostly played."""
    pool = me.hero_pool()
    top = sorted(pool.get("heroes", {}).items(), key=lambda kv: -kv[1]["games"])[:POOL_SIZE]
    out = []
    for hid, _ in top:
        pos = int(pos_mat[hid].argmax()) + 1 if pos_mat is not None else 1
        out.append((hid, pos))
    return out


def _target(hero: int, pos: int, pos_mat) -> int:
    return POOL_TARGET if (hero, pos) in pool_heroes(pos_mat) else TARGET


def _run(key: tuple, target: int, background: bool) -> None:
    hero, pos, mode = key
    job = _jobs[key]

    def progress(have, tgt, requests):
        job.update(have=have, requests=requests)
        if requests % 10 == 0:
            publish(hero=hero, pos=pos, mode=mode, have=have, target=tgt, status="loading")

    try:
        have = sm.collect(hero, pos, target, specialists=mode == "specialists", background=background,
                          stop=job["stop"], progress=progress)
        note = None
        if have < target and not job["stop"].is_set():
            note = ("Лимит запросов Stratz на этот час исчерпан — догружу позже сам."
                    if not sm._budget_ok(sm.BACKGROUND_FLOOR if background else sm.FOREGROUND_FLOOR)
                    else "Больше подходящих матчей не нашлось.")
        job.update(have=have, status="done", note=note)
    except Exception as e:  # network trouble etc.: show it, keep what is cached
        job.update(status="failed", error=f"{type(e).__name__}: {e}")
    publish(hero=hero, pos=pos, mode=mode, have=job.get("have"), target=target, status=job["status"])


def ensure_loading(hero: int, pos: int, mode: str, target: int, background: bool = False) -> dict:
    key = (hero, pos, mode)
    with _guard:
        job = _jobs.get(key)
        if job and job["status"] == "loading":
            return job
        if job and job["status"] == "done" and time.time() - job["finished_check"] < 3600:
            return job   # already tried recently: candidates or budget ran out
        job = {"status": "loading", "have": 0, "target": target, "requests": 0, "error": None,
               "stop": threading.Event(), "finished_check": time.time()}
        _jobs[key] = job
    threading.Thread(target=_run, args=(key, target, background), name=f"builds-{hero}-{pos}", daemon=True).start()
    return job


def item_share(games: list[sequences.Game]) -> dict[str, float]:
    """Share of games in which each item was bought (for 'against this draft' advice)."""
    c: Counter = Counter()
    for g in games:
        c.update(set(g.later) | ({g.boots[0]} if g.boots else set()) | ({g.upgrade[0]} if g.upgrade else set()))
    n = len(games) or 1
    return {k: v / n for k, v in c.items()}


def get(hero: int, pos: int, mode: str, bracket: str, pos_mat=None, fallback: bool = False, load: bool = True) -> dict:
    requested = pos
    if fallback and pos_mat is not None and pos_mat[hero, pos - 1] < OFFROLE_SHARE:
        pos = int(pos_mat[hero].argmax()) + 1
    target = _target(hero, pos, pos_mat)
    accounts = None
    if mode == "specialists":
        spec_file = sm._spec_path(hero)
        accounts = sm.specialist_accounts(hero, pos) if spec_file.exists() else set()
    records = sm.load(hero)
    res = sequences.builds(records, hero, pos, accounts)
    games = [g for r in records if not r.get("unparsed") and r.get("pos") == pos
             and (accounts is None or r.get("acc") in accounts) and (g := sequences.parse(r))]
    job = _jobs.get((hero, pos, mode))
    load = load and os.environ.get("DRAFTER_NO_BUILD_LOAD") != "1"  # tests: never hit the network
    if load and res["games"] < target and config.settings().stratz_token:
        job = ensure_loading(hero, pos, mode, target)
    status = "loading" if job and job["status"] == "loading" else "ready"
    approx = None
    if res["games"] < MIN_GAMES or not res["builds"]:
        old = standard.build(hero, pos, bracket)
        approx = standard.approximate(old) if old else None
    shown = res["builds"] if res["games"] >= MIN_GAMES else []
    return {
        "hero": hero, "pos": pos, "requested_pos": requested if requested != pos else None, "mode": mode,
        "abilities": _abilities(hero, shown + ([approx] if approx else []), download=load),
        "status": status, "games": res["games"], "target": target,
        "progress": {"have": res["games"], "target": target, "requests": job["requests"] if job else 0},
        "error": job.get("error") if job else None,
        "note": job.get("note") if job and res["games"] < target else None,
        "builds": shown,
        "approximate": approx,
        "item_share": item_share(games) if games else (standard.build(hero, pos, bracket) or {}).get("item_share", {}),
        "min_games": MIN_GAMES, "reliable_games": sequences.RELIABLE_GAMES,
    }


def _abilities(hero: int, builds: list[dict], download: bool = True) -> dict[str, dict]:
    """Icons, Russian names and short descriptions of the abilities these builds show; every
    talent option also gets the ability it upgrades (its icon in the talent tree)."""
    keys: set[str] = set()
    for b in builds:
        keys |= {s["key"] for s in b.get("skills", []) if s["key"] != "talent"}
        keys |= {s["key"] for s in b.get("skill_order") or []}
        for t in b.get("talents", []):
            for o in t["options"]:
                o["ability"] = abilities.talent_ability(hero, o["key"])
                if o["ability"]:
                    keys.add(o["ability"])
    try:
        return abilities.hero_abilities(hero, keys, download=download)
    except Exception:  # missing constants must not break the build itself
        return {}


# ---------- background prefetch of the user's pool ---------------------------------------------

_prefetch_stop = threading.Event()


def start_prefetch(pos_mat, log=print) -> None:
    def loop():
        time.sleep(30)  # let the app start first
        while not _prefetch_stop.is_set():
            if not config.settings().stratz_token:
                return
            for hero, pos in pool_heroes(pos_mat):
                if _prefetch_stop.is_set():
                    return
                job = ensure_loading(hero, pos, "all", POOL_TARGET, background=True)
                while job["status"] == "loading" and not _prefetch_stop.is_set():
                    _prefetch_stop.wait(5)
            # budget floor reached or everything cached: look again in 15 minutes
            _prefetch_stop.wait(900)

    threading.Thread(target=loop, name="builds-prefetch", daemon=True).start()


def stop_all() -> None:
    _prefetch_stop.set()
    for job in _jobs.values():
        job["stop"].set()
