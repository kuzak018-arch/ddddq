"""How each hero's win rate changes with the length of the game: early heroes win short games, late
carries win long ones. From the ranked match base (data/matches: duration, both teams, the result),
per hero and duration bucket, smoothed towards 50% so that a rare hero doesn't swing on a few games.

Built in the background when missing or older than MAX_AGE (a few seconds on the full base) and
kept in data/model/timing.json; without a match base (a fresh install) there is no curve and the
game plan works from the heroes' roles alone.
"""

from __future__ import annotations

import json
import threading
import time

from .. import config

PATH = config.DATA / "model" / "timing.json"
BUCKETS = [(0, 25), (25, 35), (35, 45), (45, 999)]     # minutes
LABELS = ["до 25 мин", "25–35 мин", "35–45 мин", "после 45 мин"]
EDGES = [25, 35, 45]
SMOOTH = 40           # games of 50% added to every hero and bucket
MAX_AGE = 7 * 86400
_lock = threading.Lock()
_building = False


def build(df=None) -> dict:
    """{buckets, heroes: {id: {games: [...], wr: [...]}}, base: [...]} from the match frame (polars:
    duration in seconds, radiant_team / dire_team lists, radiant_win)."""
    import polars as pl

    if df is None:
        from ..data import matches
        df = matches.load()
    if df.is_empty():
        return {"built": time.time(), "buckets": LABELS, "heroes": {}, "base": [0.5] * len(BUCKETS)}
    bucket = pl.lit(len(BUCKETS) - 1)
    for i, edge in reversed(list(enumerate(EDGES))):
        bucket = pl.when(pl.col("duration") < edge * 60).then(pl.lit(i)).otherwise(bucket)
    df = df.with_columns(bucket.alias("b"))
    sides = pl.concat([
        df.select(pl.col("radiant_team").alias("hero"), pl.col("radiant_win").alias("win"), "b"),
        df.select(pl.col("dire_team").alias("hero"), (~pl.col("radiant_win")).alias("win"), "b"),
    ]).explode("hero").drop_nulls("hero")
    agg = sides.group_by("hero", "b").agg(pl.len().alias("games"), pl.col("win").sum().alias("wins"))
    heroes: dict[str, dict] = {}
    for row in agg.iter_rows(named=True):
        h = heroes.setdefault(str(int(row["hero"])), {"games": [0] * len(BUCKETS), "wins": [0] * len(BUCKETS)})
        h["games"][row["b"]] = int(row["games"])
        h["wins"][row["b"]] = int(row["wins"])
    out = {}
    for hid, h in heroes.items():
        out[hid] = {"games": h["games"], "wr": [round((w + SMOOTH / 2) / (g + SMOOTH), 4) for w, g in zip(h["wins"], h["games"])]}
    base = []
    for b in range(len(BUCKETS)):
        g = sum(h["games"][b] for h in heroes.values())
        w = sum(h["wins"][b] for h in heroes.values())
        base.append(round(w / g, 4) if g else 0.5)
    return {"built": time.time(), "buckets": LABELS, "heroes": out, "base": base}


def _build_in_background() -> None:
    global _building
    try:
        data = build()
        if data["heroes"]:
            PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(PATH)
    except Exception:   # no match base yet, a broken page: the plan works without curves
        pass
    finally:
        with _lock:
            _building = False


def load(start: bool = True) -> dict | None:
    """The curves (None until built); a stale or missing file starts a rebuild in the background."""
    global _building
    try:
        data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else None
    except (OSError, ValueError):
        data = None
    if start and (data is None or time.time() - data.get("built", 0) > MAX_AGE):
        with _lock:
            if not _building:
                _building = True
                threading.Thread(target=_build_in_background, daemon=True, name="timing").start()
    return data


def bucket_of(minute: float) -> int:
    return next((i for i, e in enumerate(EDGES) if minute < e), len(EDGES))
