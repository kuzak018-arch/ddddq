import json

import pytest

from drafter.builds import neutrals as N


@pytest.fixture(autouse=True)
def _fresh_catalog():
    N.catalog.cache_clear()
    yield
    N.catalog.cache_clear()  # the real constants again for the other tests

ITEMS = {
    "chipped_vest": {"dname": "Chipped Vest", "tier": 1, "cost": 0, "cd": False,
                     "abilities": [{"type": "passive", "title": "Chipper", "description": "Returns  30 damage."}],
                     "attrib": [{"key": "a", "display": "+ {value} Armor", "value": "3"}, {"key": "b", "display": "+ {value} HP", "value": "0"}]},
    "kobold_cup": {"dname": "Kobold Cup", "tier": 1, "cost": 0, "cd": 30, "abilities": []},
    "spider_legs": {"dname": "Spider Legs", "tier": 5, "cost": 0},
    "medallion_like": {"dname": "Shop item with a tier", "tier": 2, "cost": 1000},
    "enhancement_brawny": {"dname": "Brawny", "cost": 0, "attrib": [{"key": "h", "display": "+ {value} Health", "value": "110 / 150"}]},
    "blink": {"dname": "Blink Dagger", "cost": 2250},
}
IDS = {"1": "chipped_vest", "2": "kobold_cup", "3": "spider_legs"}


def _setup(monkeypatch, tmp_path, stratz_rows=None, games=(), top=()):
    monkeypatch.setattr(N.constants, "_load", lambda name: {"items": ITEMS, "item_ids": IDS}[name])
    N.catalog.cache_clear()
    monkeypatch.setattr(N.stratz, "hero", lambda b, h: {"positions": {"POSITION_1": {"neutral": stratz_rows or []}}} if stratz_rows is not None else None)
    monkeypatch.setattr(N.stratz_matches, "load", lambda h: list(games))
    monkeypatch.setattr(N.config, "DATA", tmp_path)
    if top:
        (tmp_path / "topgames" / "immortal").mkdir(parents=True)
        (tmp_path / "topgames" / "immortal" / "1.json").write_text(json.dumps({"matches": list(top)}))


def test_catalog_by_tier_with_readable_text(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    cat = N.catalog()
    assert [e["key"] for e in cat["tiers"][1]] == ["chipped_vest", "kobold_cup"]
    assert cat["tiers"][2] == []  # a shop item with a tier field is not a neutral
    vest = cat["tiers"][1][0]
    assert vest["abilities"] == [{"title": "Chipper", "type": "passive", "desc": "Returns 30 damage."}]
    assert vest["stats"] == ["+3 Armor"] and vest["cooldown"] is None
    assert cat["tiers"][1][1]["cooldown"] == 30
    assert [e["key"] for e in cat["enchantments"]] == ["enhancement_brawny"]
    assert cat["enchantments"][0]["stats"] == ["+110 / 150 Health"]
    out = N.for_hero(1, 1, "LEGEND_ANCIENT")
    assert out["sources"] == [] and not any(i["popular"] for t in out["tiers"] for i in t["items"])
    assert [t["tier"] for t in out["tiers"]] == [1, 5]


def test_popular_from_stratz_and_matches(monkeypatch, tmp_path):
    games = [{"m": i, "pos": 1, "w": i % 2 == 0, "neutral": "kobold_cup"} for i in range(6)]
    games += [{"m": 99, "pos": 2, "w": True, "neutral": "chipped_vest"}, {"m": 98, "unparsed": True}]
    top = [{"m": 0, "pos": 1, "w": True, "neutral": "kobold_cup"},  # the same match as a timeline: counted once
           {"m": 50, "pos": 1, "w": True, "neutral": "spider_legs"}]
    _setup(monkeypatch, tmp_path, stratz_rows=[{"itemId": 1, "equippedMatchCount": 4, "equippedMatchWinCount": 3}],
           games=games, top=top)
    out = N.for_hero(1, 1, "LEGEND_ANCIENT")
    assert out["sources"] == ["stratz", "matches"]
    t1 = out["tiers"][0]
    assert t1["games"] == 10
    cup, vest = t1["items"]
    assert (cup["key"], cup["games"], cup["share"], cup["wr"], cup["popular"]) == ("kobold_cup", 6, 0.6, 0.5, True)
    assert (vest["games"], vest["wr"], vest["popular"]) == (4, None, True)  # 4 games: share shown, win rate not
    t5 = out["tiers"][1]
    assert t5["games"] == 1 and not t5["items"][0]["popular"]  # one game in the tier is not data
