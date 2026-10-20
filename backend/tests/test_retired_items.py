"""Items removed from the game (Eternal Shroud) are never recommended, whatever the source."""

from drafter.builds import counter, sequences as sq, standard
from drafter.data import constants

ITEMS = {"black_king_bar": {"dname": "Black King Bar", "cost": 4050}, "pipe": {"dname": "Pipe of Insight", "cost": 3475},
         "eternal_shroud": {"dname": "Eternal Shroud", "cost": 3200}}


def test_shroud_is_retired():
    assert "eternal_shroud" in constants.RETIRED_ITEMS and "black_king_bar" not in constants.RETIRED_ITEMS


def test_counter_never_recommends_a_retired_item(monkeypatch):
    monkeypatch.setattr(constants, "hero_by_id", lambda: {1: {"key": "h1", "name": "H1"}})
    monkeypatch.setattr(constants, "_load", lambda name: ITEMS)
    monkeypatch.setattr(counter.hero_tags, "load", lambda: {"h1": {"magic_burst": 5.0}})
    monkeypatch.setattr(counter, "_rules", lambda: [{"tag": "magic_burst", "min": 1.0, "weight": "any", "why": "магия {heroes}",
                                                    "items": {3: ["eternal_shroud", "pipe", "black_king_bar"]}}])
    keys = [r["item"] for r in counter.against([1], 3)]
    assert keys == ["pipe", "black_king_bar"]


def test_the_shipped_rules_do_not_mention_it():
    assert "eternal_shroud" not in counter.RULES.read_text(encoding="utf-8")


def test_purchases_of_a_retired_item_are_dropped_from_builds(monkeypatch):
    monkeypatch.setattr(sq, "_parents", lambda: {})
    monkeypatch.setattr(sq, "_is_finished_item", lambda k: True)
    monkeypatch.setattr(sq, "_cost", lambda k: 3000)
    monkeypatch.setattr(sq, "_abilities", lambda: {})
    rec = {"w": True, "pos": 3, "items": [[900, "pipe"], [1100, "eternal_shroud"], [1500, "black_king_bar"]], "skills": []}
    g = sq.parse(rec)
    assert [k for k, _ in g.core] == ["pipe", "black_king_bar"] and "eternal_shroud" not in g.later


def test_the_aggregated_build_skips_it(monkeypatch):
    monkeypatch.setattr(standard, "_maps", lambda: ({1: "eternal_shroud", 2: "black_king_bar"}, {}, ITEMS, {}))
    assert standard._item(1) is None
    assert standard._item(2)["key"] == "black_king_bar"
