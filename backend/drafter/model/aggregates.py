"""Daily per-hero games/wins by rank tier, for the tier list and trends (DuckDB over the Parquet pages)."""

from __future__ import annotations

import time

import duckdb
import polars as pl

from .. import config
from ..data import matches

OUT = config.DATA / "model" / "daily.parquet"


def build(log=print) -> pl.DataFrame:
    """One row per (day, rank tier 1..8, hero): games, wins. Also total matches per (day, tier)."""
    t0 = time.monotonic()
    pages = str(matches.PAGES / "*.parquet").replace("\\", "/")
    side = lambda s, col, win: (f"SELECT start_time, avg_rank_tier, {col} AS hero, "
                                f"CAST({win} AS INT) AS won FROM m")
    union = " UNION ALL ".join(
        [side("r", f"r{i}", "radiant_win") for i in range(5)]
        + [side("d", f"d{i}", "NOT radiant_win") for i in range(5)])
    q = f"""
        WITH m AS (
            SELECT DISTINCT ON (match_id) * FROM read_parquet('{pages}')
            WHERE duration >= {matches.MIN_DURATION}
        ), x AS ({union})
        SELECT CAST(to_timestamp(start_time) AS DATE) AS day, CAST(avg_rank_tier // 10 AS SMALLINT) AS tier,
               CAST(hero AS SMALLINT) AS hero, COUNT(*) AS games, CAST(SUM(won) AS BIGINT) AS wins
        FROM x GROUP BY ALL ORDER BY ALL
    """
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    df = con.sql(q).pl()
    con.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(OUT)
    log(f"дневные агрегаты: {df.height:,} строк за {time.monotonic() - t0:.0f} с")
    return df


def load() -> pl.DataFrame:
    if not OUT.exists():
        return build()
    return pl.read_parquet(OUT).with_columns(pl.col("games").cast(pl.Int64), pl.col("wins").cast(pl.Int64))
