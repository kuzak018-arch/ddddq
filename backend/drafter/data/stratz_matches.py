"""Per-match purchase and skill timelines from Stratz, cached per hero.

Candidates are our own OpenDota ranked matches with the hero, average rank Legend+ and at least
3 days old (Stratz parses most matches within days: ~8/12 at 4-5 days, ~11/12 at 2-3 weeks).
Each match is one request (`matches(ids)` is admin-only on Stratz); `stats.itemPurchases` and
`abilities` are cheap, unlike `playbackData` which Stratz rebuilds from the replay.

Every fetched match is appended to data/stratz/match_players/<hero>.jsonl, unparsed ones too, so
nothing is requested twice. Specialists come from Stratz's hero leaderboard: players with at least
SPECIALIST_MIN_GAMES games on the hero this season; their recent matches on it go to the same cache.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from functools import cache
from pathlib import Path

import polars as pl

from .. import config
from . import matches, stratz
from .constants import _load as load_const

CACHE = config.DATA / "stratz" / "match_players"
SPECIALISTS = config.DATA / "stratz" / "specialists"
MIN_RANK_TIER = 50                 # Legend and above (average rank of the match)
MIN_AGE_DAYS = 3                   # younger matches are rarely parsed yet
SPECIALIST_MIN_GAMES = 30          # wins + losses on the hero this season (Stratz leaderboard)
SPECIALIST_MATCHES_EACH = 25
FOREGROUND_FLOOR = 40              # keep this many requests per hour for anything else
BACKGROUND_FLOOR = 400             # background prefetch stops earlier: on-demand loading has priority

_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(hero_id: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(hero_id, threading.Lock())


def _path(hero_id: int) -> Path:
    return CACHE / f"{hero_id}.jsonl"


def load(hero_id: int) -> list[dict]:
    p = _path(hero_id)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # a half-written last line after a crash
    return out


def _append(hero_id: int, rec: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    with _lock(hero_id), _path(hero_id).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")


def candidates(hero_id: int, exclude: set[int]) -> list[int]:
    """Our ranked matches with the hero, Legend+, old enough to be parsed; newest first."""
    files = sorted(matches.PAGES.glob("*.parquet"))
    if not files:
        return []
    cutoff = int(time.time()) - MIN_AGE_DAYS * 86400
    cols = [f"r{i}" for i in range(5)] + [f"d{i}" for i in range(5)]
    df = (pl.scan_parquet(files)
          .filter((pl.col("avg_rank_tier") >= MIN_RANK_TIER) & (pl.col("start_time") <= cutoff)
                  & (pl.col("duration") >= matches.MIN_DURATION)
                  & pl.any_horizontal([pl.col(c) == hero_id for c in cols]))
          .select("match_id").unique().sort("match_id", descending=True).collect())
    return [m for m in df["match_id"].to_list() if m not in exclude]


_Q = """{ match(id: %d) { id startDateTime durationSeconds rank players { heroId steamAccountId isVictory position
  stats { itemPurchases { time itemId } } abilities { abilityId time level } } } }"""


@cache
def _id_maps() -> tuple[dict[int, str], dict[int, str]]:
    item_ids = {int(k): v for k, v in load_const("item_ids").items() if k.isdigit()}
    ability_ids = {int(i): v for k, v in load_const("ability_ids").items() for i in k.split(",") if i.isdigit()}
    return item_ids, ability_ids


def fetch_match(sz: stratz.Stratz, match_id: int, hero_id: int) -> dict:
    """One cache record for the hero's player in this match."""
    item_ids, ability_ids = _id_maps()
    m = sz.q(_Q % match_id)["match"] or {}
    p = next((p for p in m.get("players") or [] if p["heroId"] == hero_id), None)
    purchases = ((p or {}).get("stats") or {}).get("itemPurchases")
    if not p or not purchases:
        return {"m": match_id, "unparsed": True}
    pos = p.get("position")
    return {
        "m": match_id, "t": m.get("startDateTime"), "dur": m.get("durationSeconds"), "rank": m.get("rank"),
        "acc": p.get("steamAccountId"), "w": bool(p.get("isVictory")),
        "pos": int(pos[-1]) if pos and pos.startswith("POSITION_") else None,
        "items": [[x["time"], item_ids.get(x["itemId"], str(x["itemId"]))] for x in purchases],
        "skills": [ability_ids.get(a["abilityId"], str(a["abilityId"])) for a in sorted(p.get("abilities") or [], key=lambda a: a["time"])],
    }


def _budget_ok(floor: int) -> bool:
    left = stratz.limits.get("hour")
    return left is None or left > floor and stratz.limits.get("day", 10**6) > floor


def collect(hero_id: int, pos: int, target: int, *, specialists: bool = False, background: bool = False,
            stop: threading.Event | None = None, progress: Callable[[int, int, int], None] | None = None,
            max_requests: int | None = None) -> int:
    """Fetch matches until `target` usable games of the hero on `pos` are cached (or candidates,
    the request cap or the token's budget run out). Returns how many usable games there are."""
    floor = BACKGROUND_FLOOR if background else FOREGROUND_FLOOR
    have = load(hero_id)
    seen = {r["m"] for r in have}
    accounts = specialist_accounts(hero_id, pos) if specialists else None
    usable = lambda r: not r.get("unparsed") and r.get("pos") == pos and (accounts is None or r.get("acc") in accounts)
    count = sum(1 for r in have if usable(r))
    if count >= target:
        return count
    if specialists:
        ids = [m for m in specialist_match_ids(hero_id, pos) if m not in seen]
    else:
        ids = candidates(hero_id, seen)
    max_requests = max_requests or target * 4
    sz = stratz.Stratz(min_interval=0.45)
    try:
        for n, mid in enumerate(ids[:max_requests], 1):
            if (stop and stop.is_set()) or not _budget_ok(floor):
                break
            try:
                rec = fetch_match(sz, mid, hero_id)
            except RuntimeError:
                continue  # one broken match must not stop the whole load
            _append(hero_id, rec)
            if usable(rec):
                count += 1
            if progress:
                progress(count, target, n)
            if count >= target:
                break
    finally:
        sz.close()
    return count


# ---------- specialists ----------------------------------------------------------------------

def _spec_path(hero_id: int) -> Path:
    return SPECIALISTS / f"{hero_id}.json"


def specialist_accounts(hero_id: int, pos: int) -> set[int]:
    data = _specialists(hero_id)
    return {p["acc"] for p in data["players"] if p["pos"] in (pos, None)}


def specialist_match_ids(hero_id: int, pos: int) -> list[int]:
    data = _specialists(hero_id)
    return [m for p in data["players"] if p["pos"] in (pos, None) for m in p["matches"]]


def _specialists(hero_id: int) -> dict:
    """Leaderboard players with >= SPECIALIST_MIN_GAMES games on the hero and their recent match ids
    (cached for a week)."""
    p = _spec_path(hero_id)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - data["fetched"] < 7 * 86400:
            return data
    sz = stratz.Stratz(min_interval=0.45)
    try:
        lb = sz.q("""{ leaderboard { hero(request: {heroIds: [%d], bracketIds: [LEGEND, ANCIENT, DIVINE, IMMORTAL], take: 100})
                   { steamAccountId position wins losses } } }""" % hero_id)["leaderboard"]["hero"] or []
        players = []
        for row in lb:
            if (row.get("wins") or 0) + (row.get("losses") or 0) < SPECIALIST_MIN_GAMES:
                continue
            acc = row["steamAccountId"]
            try:
                ms = sz.q("""{ player(steamAccountId: %d) { matches(request: {heroIds: [%d], take: %d}) { id } } }"""
                          % (acc, hero_id, SPECIALIST_MATCHES_EACH))["player"]["matches"] or []
            except RuntimeError:
                continue  # private profile
            pos = row.get("position")
            players.append({"acc": acc, "pos": int(pos[-1]) if pos and pos.startswith("POSITION_") else None,
                            "games": row["wins"] + row["losses"], "matches": [m["id"] for m in ms]})
    finally:
        sz.close()
    data = {"fetched": time.time(), "players": players}
    SPECIALISTS.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return data
