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
