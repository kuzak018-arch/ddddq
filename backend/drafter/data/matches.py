"""Ranked All Pick matches from the OpenDota explorer (`public_matches`), stored as Parquet pages.

Paging is by match_id (indexed): a 50k page takes ~1 s, while any scan by start_time times out.
Pages are written atomically, so the collector can be stopped and resumed at any time, and
readers can load whatever is already on disk.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import polars as pl

from .. import config
from .http import OpenDota

DIR = config.DATA / "matches"
PAGES = DIR / "pages"
STATE = DIR / "state.json"
PAGE = 50_000
FRESH_LAG = 2 * 3600  # newest matches have empty hero arrays for a while
RANKED, ALL_PICK = 7, 22
MIN_DURATION = 15 * 60

_COLS = "match_id, start_time, duration, avg_rank_tier, num_rank_tier, radiant_win, radiant_team, dire_team"
_WHERE = f"lobby_type = {RANKED} AND game_mode = {ALL_PICK}"


def _state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def _save_state(s: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1))


def _to_frame(rows: list[dict], since_ts: int) -> pl.DataFrame:
    keep = []
    for r in rows:
        teams = (r["radiant_team"] or []) + (r["dire_team"] or [])
        if len(teams) != 10 or 0 in teams or r["start_time"] < since_ts or r["avg_rank_tier"] is None:
            continue
        keep.append((r["match_id"], r["start_time"], r["duration"], round(r["avg_rank_tier"]),
                     r["num_rank_tier"], r["radiant_win"], *teams))
    schema = {"match_id": pl.Int64, "start_time": pl.Int64, "duration": pl.Int32, "avg_rank_tier": pl.Int16,
              "num_rank_tier": pl.Int16, "radiant_win": pl.Boolean}
    schema |= {f"r{i}": pl.Int16 for i in range(5)} | {f"d{i}": pl.Int16 for i in range(5)}
    return pl.DataFrame(keep, schema=schema, orient="row")


def _write(df: pl.DataFrame) -> Path | None:
    if df.is_empty():
        return None
    PAGES.mkdir(parents=True, exist_ok=True)
    path = PAGES / f"{df['match_id'].min()}_{df['match_id'].max()}.parquet"
    tmp = path.with_suffix(".tmp")
    df.write_parquet(tmp, compression="zstd")
    tmp.replace(path)
    return path


def collect(since_ts: int, log=print) -> None:
    """Backfill from now down to `since_ts`, then pull anything newer than what we have."""
    od = OpenDota(min_interval=2.0)
    s = _state()
    if s.get("since_ts") != since_ts:
        if s:
            log(f"граница сбора сменилась ({s.get('since_ts')} → {since_ts}), начинаю заново")
            for p in PAGES.glob("*.parquet"):
                p.unlink()
        s = {"since_ts": since_ts}
    started, total = time.monotonic(), 0
    try:
        if not s.get("backfill_done"):
            if "oldest_id" not in s:
                cutoff = int(time.time()) - FRESH_LAG
                top = od.sql(f"SELECT match_id FROM public_matches WHERE start_time < {cutoff} "
                             f"ORDER BY match_id DESC LIMIT 1")
                s["oldest_id"] = s["newest_id"] = top[0]["match_id"] + 1
            while True:
                rows = od.sql(f"SELECT {_COLS} FROM public_matches WHERE match_id < {s['oldest_id']} "
                              f"AND {_WHERE} ORDER BY match_id DESC LIMIT {PAGE}")
                if not rows:
                    break
                df = _to_frame(rows, since_ts)
                _write(df)
                total += df.height
                s["oldest_id"] = min(r["match_id"] for r in rows)
                s["newest_id"] = max(s["newest_id"], max(r["match_id"] for r in rows))
                _save_state(s)
                oldest_ts = min(r["start_time"] for r in rows)
                log(f"назад: +{df.height:>6} (всего {total:,}), дошёл до "
                    f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(oldest_ts))}, "
                    f"запросов на сегодня осталось {od.remaining_day}")
                if oldest_ts < since_ts:
                    break
            s["backfill_done"] = True
            _save_state(s)

        cutoff = int(time.time()) - FRESH_LAG
        while True:
            rows = od.sql(f"SELECT {_COLS} FROM public_matches WHERE match_id >= {s['newest_id']} "
                          f"AND start_time < {cutoff} AND {_WHERE} ORDER BY match_id ASC LIMIT {PAGE}")
            if not rows:
                break
            df = _to_frame(rows, since_ts)
            _write(df)
            total += df.height
            s["newest_id"] = max(r["match_id"] for r in rows) + 1
            _save_state(s)
            log(f"вперёд: +{df.height:>6} (всего {total:,})")
            if len(rows) < PAGE:
                break
    finally:
        od.close()
    log(f"готово: новых матчей {total:,} за {time.monotonic() - started:.0f} с")


def load(min_duration: int = MIN_DURATION) -> pl.DataFrame:
    """All collected matches, deduplicated, without short (abandoned / early-surrender) games."""
    files = sorted(PAGES.glob("*.parquet"))
    if not files:
        raise FileNotFoundError("матчей нет: запусти `drafter.cli collect`")
    return (
        pl.scan_parquet(files)
        .filter(pl.col("duration") >= min_duration)
        .unique("match_id")
        .sort("match_id")
        .collect()
    )


def summary() -> dict:
    files = sorted(PAGES.glob("*.parquet"))
    if not files:
        return {"matches": 0}
    df = pl.scan_parquet(files).select(
        pl.len().alias("n"), pl.col("start_time").min().alias("t0"), pl.col("start_time").max().alias("t1"),
        (pl.col("duration") >= MIN_DURATION).sum().alias("n_ok"),
    ).collect().row(0, named=True)
    fmt = lambda t: time.strftime("%Y-%m-%d %H:%M", time.localtime(t))
    return {"matches": df["n"], "after_filters": df["n_ok"], "from": fmt(df["t0"]), "to": fmt(df["t1"]),
            "pages": len(files), **{k: v for k, v in _state().items() if k == "backfill_done"}}
