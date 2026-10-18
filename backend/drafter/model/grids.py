"""Hero grids for Dota built from our own data: roles, the meta tier list at the user's rank, the
user's hero pool and counters. Each grid is a list of named hero lists (categories) that are laid out
on the grid canvas; hero_grid.py writes them into the game's file.

Layout. The grid canvas is a plain coordinate space; the user's own file uses x up to ~1190. A hero
cell in the game is ~59x33, the constants below leave a few pixels around each so no category is
ever shorter than its heroes need (a too short category hides heroes in the game). Nothing goes
below MAX_BOTTOM: the lowest category in the user's file ends at ~470, so that much is surely visible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .. import hero_grid
from ..data import constants, me
from . import meta

CANVAS_W = 1190.0
MARGIN = 16.0
GAP = 8.0
CELL_W = 62.0
CELL_H = 36.0
HEAD_H = 26.0
PAD = 6.0
MAX_BOTTOM = 470.0
MIN_CELLS = 4          # an auto-sized category is never narrower than this: its name must fit

GRIDS = {
    "roles": ("Роли", "По пять позиций: самые сильные герои на каждой роли на твоём ранге."),
    "meta": ("Мета", "Тир-лист S–D на твоём ранге по всем героям."),
    "pool": ("Мой пул", "Твои герои по ролям и герои меты, на которых ты ещё мало играл."),
    "counters": ("Контрпики", "«Против X»: кто лучше всего играет против самых частых героев."),
}
ROLE_NAMES = {1: "Керри", 2: "Мид", 3: "Оффлейн", 4: "Роумер", 5: "Саппорт"}
ROLE_TOP = 18          # heroes per role: one full-width row
POOL_ROLE_TOP = 18     # the pool's roles too, so the pool always fits under MAX_BOTTOM
POOL_MIN_GAMES = 5     # fewer games on a hero: it is not in "my pool" yet
POOL_ROLE_SHARE = 0.25  # a hero is in a role of the pool from this share of its games
TRY_COUNT = 12
COUNTER_HEROES = 18
COUNTER_PER = 5
COUNTER_MIN_GAMES = 500


FULL_W = CANVAS_W - 2 * MARGIN


@dataclass
class Category:
    name: str
    heroes: list[int]
    width: float | None = FULL_W  # None: as wide as its heroes need in one row (full width if more)


def per_row(width: float) -> int:
    return max(1, int((width - 2 * PAD) // CELL_W))


def cells_width(cells: int) -> float:
    return cells * CELL_W + 2 * PAD


def auto_width(n: int) -> float:
    return min(FULL_W, cells_width(max(n, MIN_CELLS)))


def split_row(a: int, b: int) -> tuple[float, float]:
    """Widths for two categories of a and b heroes sharing one full-width row, with the columns split
    so the taller of the two is as short as possible (ties: the first one gets the extra columns)."""
    cols = per_row(FULL_W - GAP - 2 * PAD)  # columns left for both after the gap and the second padding
    best = min(range(1, cols), key=lambda k: (max(math.ceil(max(a, 1) / k), math.ceil(max(b, 1) / (cols - k))), -k))
    wa = cells_width(best)
    return wa, FULL_W - GAP - wa


def category_height(n: int, width: float) -> float:
    rows = max(1, math.ceil(n / per_row(width)))
    return HEAD_H + rows * CELL_H + PAD


def layout(categories: list[Category]) -> list[dict]:
    """Place categories left to right, wrapping to a new row when the next one does not fit.
    Returns the game's category dicts (names, position, size, hero ids)."""
    out: list[dict] = []
    x, y, row_h = MARGIN, MARGIN, 0.0
    for c in categories:
        w = auto_width(len(c.heroes)) if c.width is None else c.width
        h = category_height(len(c.heroes), w)
        if x > MARGIN and x + w > CANVAS_W - MARGIN + 0.001:
            x, y, row_h = MARGIN, y + row_h + GAP, 0.0
        out.append({"category_name": c.name, "x_position": round(x, 6), "y_position": round(y, 6),
                    "width": round(w, 6), "height": round(h, 6), "hero_ids": [int(i) for i in c.heroes]})
        x += w + GAP
        row_h = max(row_h, h)
    return out


def bottom(placed: list[dict]) -> float:
    return max((c["y_position"] + c["height"] for c in placed), default=0.0)


def config(grid_id: str, categories: list[Category]) -> dict:
    placed = layout(categories)
    if bottom(placed) > MAX_BOTTOM + 0.001:  # never write a grid whose bottom may be off screen in the game
        raise hero_grid.GridError(f"сетка «{GRIDS[grid_id][0]}» не влезает по высоте: {bottom(placed):.0f} > {MAX_BOTTOM:.0f}")
    return {"config_name": hero_grid.PREFIX + GRIDS[grid_id][0], "categories": placed}


# ---------- the four grids ------------------------------------------------------------------

def _tier(pred, rank: int, bracket: str | None, days: int, pos: int | None) -> list[dict]:
    return meta.tierlist([rank // 10], pos, pred.pos_mat, bracket, days)["heroes"]


def roles(pred, rank: int, bracket: str | None, days: int) -> list[Category]:
    cats = []
    for pos in range(1, 6):
        rows = sorted(_tier(pred, rank, bracket, days, pos), key=lambda r: -r["score"])[:ROLE_TOP]
        cats.append(Category(f"{pos} · {ROLE_NAMES[pos]}", [r["hero"] for r in rows]))
    return cats


def meta_tiers(pred, rank: int, bracket: str | None, days: int) -> list[Category]:
    rows = sorted(_tier(pred, rank, bracket, days, None), key=lambda r: -r["score"])
    return tier_categories({t: [r["hero"] for r in rows if r["tier"] == t] for t in "SABCD"})


def tier_categories(by_tier: dict[str, list[int]]) -> list[Category]:
    """Three rows: S beside A, B alone, C beside D, each pair split so neither is needlessly tall.
    For ~127 heroes (13/25/51/25/13) that is 3 hero rows per row of tiers, bottom at 452."""
    s, a, b, c, d = (by_tier.get(t, []) for t in "SABCD")
    ws, wa = split_row(len(s), len(a))
    wc, wd = split_row(len(c), len(d))
    return [Category("Тир S", s, ws), Category("Тир A", a, wa), Category("Тир B", b),
            Category("Тир C", c, wc), Category("Тир D", d, wd)]


def pool(pred, rank: int, bracket: str | None, days: int) -> list[Category]:
    heroes = me.hero_pool().get("heroes", {})
    mine = {h: v for h, v in heroes.items() if v["games"] >= POOL_MIN_GAMES}
    cats = []
    for pos in range(1, 6):
        ids = [h for h, v in sorted(mine.items(), key=lambda kv: -kv[1]["games"]) if pred.pos_mat[h, pos - 1] >= POOL_ROLE_SHARE]
        if ids:  # short roles sit side by side; a role is one row at most (the most played heroes)
            cats.append(Category(f"{pos} · {ROLE_NAMES[pos]}", ids[:POOL_ROLE_TOP], None))
    # the role the user plays most (by games, spread over the heroes' roles): meta heroes to try there
    weight = [sum(v["games"] * float(pred.pos_mat[h, p]) for h, v in heroes.items()) for p in range(5)]
    if sum(weight) > 0:
        main = max(range(5), key=lambda p: weight[p]) + 1
        rows = sorted(_tier(pred, rank, bracket, days, main), key=lambda r: -r["score"])
        fresh = [r["hero"] for r in rows if heroes.get(r["hero"], {}).get("games", 0) < POOL_MIN_GAMES][:TRY_COUNT]
        if fresh:
            cats.append(Category(f"Стоит попробовать · {ROLE_NAMES[main]}", fresh, None))
    return cats


def counters(pred, rank: int, bracket: str | None, days: int) -> list[Category]:
    names = {h["id"]: h["name"] for h in constants.hero_index()}
    rows = sorted(_tier(pred, rank, bracket, days, None), key=lambda r: -r["pick_rate"])[:COUNTER_HEROES]
    width = (CANVAS_W - 2 * MARGIN - 2 * GAP) / 3
    cats = []
    for r in rows:
        # the opponents with the worst delta for this hero are the ones that beat it
        beat = meta.matchups(r["hero"], pred.S, pred.C, pred.pair_games, pred.cal_a, COUNTER_MIN_GAMES, COUNTER_PER)["countered_by"]
        if beat:
            cats.append(Category(f"Против {names[r['hero']]}", [b["hero"] for b in beat], width))
    return cats


BUILDERS = {"roles": roles, "meta": meta_tiers, "pool": pool, "counters": counters}


def build(pred, grid_ids: list[str], rank: int, bracket: str | None, days: int) -> dict[str, dict]:
    """{id: config} for the requested grids; a grid with no categories is left out."""
    out = {}
    for gid in grid_ids:
        if gid not in BUILDERS:
            raise KeyError(gid)
        cats = [c for c in BUILDERS[gid](pred, rank, bracket, days) if c.heroes]
        if cats:
            out[gid] = config(gid, cats)
    return out
