"""Tier list and hero matchup tables."""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import polars as pl

from ..data import constants, stratz
from . import aggregates

PRIOR_GAMES = 300      # winrate shrinkage toward 50% for the tier score
TIERS = [("S", 0.10), ("A", 0.30), ("B", 0.70), ("C", 0.90), ("D", 1.0)]  # cumulative quantiles
POS_SHARE = 0.40       # hero belongs to a position in the tier list from this share of its games


def _ban_share(bracket: str) -> dict[int, float]:
    p = stratz.DIR / bracket / "bans.json"
    if not p.exists():
        return {}
    rows = json.loads(p.read_text(encoding="utf-8"))
    total = sum(r["matchCount"] for r in rows) or 1
    return {r["heroId"]: r["matchCount"] / total for r in rows}


def _stratz_pos_wr(bracket: str) -> dict[tuple[int, int], tuple[int, int]]:
    p = stratz.DIR / bracket / "positions.json"
    if not p.exists():
        return {}
    out = {}
    for r in json.loads(p.read_text(encoding="utf-8")):
        if r["position"] in stratz.POSITIONS:
            out[(r["heroId"], stratz.POSITIONS.index(r["position"]) + 1)] = (r["matchCount"], r["winCount"])
    return out


def tierlist(tiers: list[int], pos: int | None, pos_mat: np.ndarray, bracket: str | None,
             days: int = 14, trend_days: int = 7) -> dict:
    """Heroes for rank tiers (1=Herald..8=Immortal) and optionally a position, with tier letters.
    Winrate/pick rate from our matches (last `days` days); trend = daily winrate for `trend_days`;
    position winrate and ban share from Stratz for the bracket, when downloaded."""
    df = aggregates.load().filter(pl.col("tier").is_in(tiers))
    last = df["day"].max()
    period = df.filter(pl.col("day") > last - dt.timedelta(days=days))
    matches_total = period["games"].sum() / 10
    per_hero = period.group_by("hero").agg(pl.col("games").sum(), pl.col("wins").sum())
    trend = (df.filter(pl.col("day") > last - dt.timedelta(days=trend_days))
             .group_by("hero", "day").agg(pl.col("games").sum(), pl.col("wins").sum()).sort("day"))
    trend_by = {}
    for (h,), g in trend.group_by("hero"):
        trend_by[h] = [{"day": str(d), "wr": w / n if n else None, "games": n}
                       for d, n, w in zip(g["day"], g["games"], g["wins"])]
    bans = _ban_share(bracket) if bracket else {}
    pos_wr = _stratz_pos_wr(bracket) if bracket else {}
    heroes = constants.hero_by_id()
    rows = []
    for h, games, wins in per_hero.iter_rows():
        if h not in heroes:
            continue
        share = float(pos_mat[h, pos - 1]) if pos else 1.0
        if pos and share < POS_SHARE:
            continue
        t = trend_by.get(h, [])
        half = len(t) // 2
        def wr_of(xs):
            n = sum(x["games"] for x in xs)
            return sum(x["wr"] * x["games"] for x in xs) / n if n else None
        recent, before = wr_of(t[half:]), wr_of(t[:half])
        pw = pos_wr.get((h, pos)) if pos else None
        rows.append({
            "hero": h, "games": int(games), "wr": wins / games, "pick_rate": games / matches_total,
            "score": (wins + PRIOR_GAMES / 2) / (games + PRIOR_GAMES),
            "ban_share": bans.get(h), "pos_share": share,
            "pos_wr": pw[1] / pw[0] if pw and pw[0] else None, "pos_games": pw[0] if pw else None,
            "trend": t, "trend_delta": (recent - before) if recent is not None and before is not None else None,
        })
    rows.sort(key=lambda r: -r["score"])
    for i, r in enumerate(rows):
        q = (i + 0.5) / len(rows)
        r["tier"] = next(letter for letter, cut in TIERS if q <= cut)
    return {"tiers": tiers, "pos": pos, "days": days, "until": str(last), "matches": int(matches_total),
            "bracket": bracket, "heroes": rows}


def matchups(hero: int, S: np.ndarray, C: np.ndarray, pair_games: tuple[np.ndarray, np.ndarray],
             cal_a: float, min_games: int = 500, top: int = 8) -> dict:
    """Best/worst opponents and allies for a hero, in percentage points near 50%."""
    heroes = constants.hero_by_id()
    g_syn, g_cnt = pair_games
    pp = lambda z: float((1 / (1 + np.exp(-cal_a * z)) - 0.5) * 100)

    def table(M, G):
        rows = [{"hero": int(o), "delta": pp(M[hero, o]), "games": int(G[hero, o])}
                for o in heroes if o != hero and G[hero, o] >= min_games]
        rows.sort(key=lambda r: -r["delta"])
        return rows[:top], rows[::-1][:top]

    good_vs, bad_vs = table(C, g_cnt)
    good_with, bad_with = table(S, g_syn)
    return {"counters": good_vs, "countered_by": bad_vs, "synergy": good_with, "anti_synergy": bad_with}
