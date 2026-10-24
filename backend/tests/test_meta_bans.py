"""Ban share and the place by bans for the hero page; needs no data (a bracket file is written here)."""

import json

from drafter.data import stratz
from drafter.model import meta


def test_ban_place(monkeypatch, tmp_path):
    monkeypatch.setattr(stratz, "DIR", tmp_path)
    assert meta.ban_place(1, "LEGEND_ANCIENT") is None          # not downloaded
    assert meta.ban_place(1, None) is None
    (tmp_path / "LEGEND_ANCIENT").mkdir()
    rows = [{"heroId": 1, "matchCount": 50}, {"heroId": 2, "matchCount": 30}, {"heroId": 3, "matchCount": 20}]
    (tmp_path / "LEGEND_ANCIENT" / "bans.json").write_text(json.dumps(rows), encoding="utf-8")
    assert meta.ban_place(1, "LEGEND_ANCIENT") == {"share": 0.5, "place": 1, "of": 3}
    assert meta.ban_place(3, "LEGEND_ANCIENT") == {"share": 0.2, "place": 3, "of": 3}
    assert meta.ban_place(99, "LEGEND_ANCIENT") == {"share": 0.0, "place": None, "of": 3}  # never banned


def test_tierlist_for_immortal_and_empty_tiers(monkeypatch):
    import datetime as dt

    import numpy as np
    import polars as pl

    from drafter.model import aggregates
    day = dt.date(2026, 10, 1)
    daily = pl.DataFrame({"day": [day, day], "tier": [7, 7], "hero": [1, 2], "games": [100, 50], "wins": [60, 20]},
                         schema={"day": pl.Date, "tier": pl.Int16, "hero": pl.Int16, "games": pl.Int64, "wins": pl.Int64})
    monkeypatch.setattr(aggregates, "load", lambda: daily)
    monkeypatch.setattr(meta.constants, "hero_by_id", lambda: {1: {}, 2: {}})
    pos_mat = np.full((3, 5), 0.2)
    out = meta.tierlist([8], None, pos_mat, None)   # no tier-8 rows: Immortal reads the Divine tier
    assert out["tiers"] == [8] and {r["hero"] for r in out["heroes"]} == {1, 2}
    assert meta.tierlist([1], None, pos_mat, None)["heroes"] == []   # no data at all: empty, not an error
