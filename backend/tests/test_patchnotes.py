"""«Патчи»: the localisation file of patch notes becomes patches grouped by hero, item and general."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from drafter.data import patchnotes as P

FIX = Path(__file__).parent / "fixtures" / "patchnotes_small.txt"
HEROES = [{"id": 1, "key": "antimage", "name": "Anti-Mage"}, {"id": 3, "key": "bane", "name": "Bane"},
          {"id": 62, "key": "bounty_hunter", "name": "Bounty Hunter"}]
ITEMS = {"bfury": {"dname": "Battle Fury"}, "bfury_recipe": {"dname": "Recipe"}}


@pytest.fixture()
def notes(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "DIR", tmp_path)
    monkeypatch.setattr(P, "FILE", tmp_path / "patchnotes_russian.txt")
    P.FILE.write_bytes(FIX.read_bytes())
    P._parsed.cache_clear()
    monkeypatch.setattr(P.constants, "hero_index", lambda: HEROES)
    monkeypatch.setattr(P.constants, "_load", lambda name: {"items": ITEMS, "abilities": {"antimage_mana_break": {"dname": "Mana Break"}},
                                                             "patches": [{"name": "7.41f", "ts": 1789455600}]}[name])
    monkeypatch.setattr(P.abilities, "hero_abilities", lambda hid, keys, download=False: {})
    monkeypatch.setattr(P, "_download", lambda: pytest.fail("fresh file: no download"))
    return P


def test_versions_newest_first(notes):
    assert [p["version"] for p in notes.patch_list()["patches"]] == ["7.41f", "7.41", "7.40"]
    assert notes.version_key("7.41f") > notes.version_key("7.41") > notes.version_key("7.40c")
    first = notes.patch_list({62})["patches"][0]
    assert first["heroes"] == 3 and first["items"] == 1 and first["mine"] == [62] and first["date"] == 1789455600


def test_a_patch_grouped_and_cleaned(notes):
    d = notes.patch("7.41f", mine={62})
    assert d["items"] == [{"key": "bfury", "name": "Battle Fury", "icon": "/icons/items/bfury.png",
                           "notes": ["Chop Tree: перезарядка уменьшена с 4 до 3 секунд"]}]
    assert [h["key"] for h in d["heroes"]] == ["bounty_hunter", "antimage", "bane"]       # mine first
    bh = d["heroes"][0]
    assert bh["notes"] == ["Скорость передвижения увеличена"] and bh["talents"] == ["Талант 20 уровня: заменён"]
    assert bh["abilities"][0]["key"] == "bounty_hunter_track" and bh["abilities"][0]["notes"] == ["Золото уменьшено"]
    assert d["heroes"][1]["abilities"][0]["name"] == "Mana Break"
    general = notes.patch("7.41")["general"]
    assert general == [{"title": "Цели на карте", "notes": ["Рошан сильнее"]}]                # html gone, <br> line dropped
    with pytest.raises(notes.PatchNotesError):
        notes.patch("6.88")


def test_offline_uses_the_last_copy(notes, monkeypatch):
    import os
    os.utime(notes.FILE, (0, 0))

    def down():
        raise notes.PatchNotesError("нет сети")

    monkeypatch.setattr(notes, "_download", down)
    assert notes.patch_list()["stale"]
    notes.FILE.unlink()
    with pytest.raises(notes.PatchNotesError):
        notes.patch_list()


def test_api(notes, monkeypatch):
    from drafter.api import app as api
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    monkeypatch.setattr(api, "_my_heroes", lambda: {1})
    with TestClient(api.app) as c:
        assert c.get("/patches").json()["patches"][0]["mine"] == [1]
        assert c.get("/patches/7.41f").json()["mine"] == [1]
        assert c.get("/patches/6.88").status_code == 404
        assert c.get("/patches/abc").status_code == 422
