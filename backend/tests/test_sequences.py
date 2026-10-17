import pytest

from drafter.builds import sequences as sq
from drafter.data import constants

pytestmark = pytest.mark.skipif(not (constants.DIR / "items.json").exists(), reason="нужны константы")

BS = 4


def rec(win, items, pos=1, skills=None):
    return {"m": hash((win, tuple(map(tuple, items)))) & 0xFFFFFFF, "pos": pos, "w": win, "acc": 1,
            "items": items, "skills": skills or ["bloodseeker_blood_bath", "bloodseeker_thirst"] * 6}


START = [[-89, "quelling_blade"], [-89, "tango"], [-89, "branches"], [-89, "circlet"], [-89, "magic_stick"]]


def game_a(win, boots="phase_boots", third="basher"):
    # Maelstrom is later turned into Mjollnir -> intermediate, must not be a core item
    return rec(win, START + [[150, "wraith_band"], [300, "boots"], [380, boots], [700, "maelstrom"], [1100, "mjollnir"],
                             [1450, "black_king_bar"], [1800, third], [2500, "travel_boots"], [900, "tpscroll"]])


def test_parse_one_boots_no_consumables_no_intermediates():
    g = sq.parse(game_a(True))
    assert g.boots[0] == "phase_boots" and g.upgrade[0] == "travel_boots"
    keys = [k for k, _ in g.core]
    assert keys == ["mjollnir", "black_king_bar", "basher"]
    assert "maelstrom" not in keys and "tpscroll" not in keys and "boots" not in keys
    assert "wraith_band" in g.early and g.starting.count("tango") == 1


def test_builds_alternatives_order_and_winrate():
    records = ([game_a(True) for _ in range(14)] + [game_a(False) for _ in range(6)]
               + [game_a(True, boots="power_treads", third="butterfly") for _ in range(6)]
               + [game_a(False, third="butterfly") for _ in range(4)])
    res = sq.builds(records, BS, 1)
    assert res["games"] == 30 and len(res["builds"]) == 1
    b = res["builds"][0]
    assert b["games"] == 30 and b["wr"] == round(20 / 30, 3)           # wins AND losses count
    assert not b["reliable"]                                           # < 100 games
    assert b["boots"]["key"] == "phase_boots"
    assert [a["key"] for a in b["boots"]["alternatives"]] == ["power_treads"] and b["boots"]["alternatives"][0]["share"] == 0.2
    assert b["boots_upgrade"]["key"] == "travel_boots"
    core = [c["key"] for c in b["core"]]
    assert core[:2] == ["mjollnir", "black_king_bar"]
    third = b["core"][2]
    assert {third["key"]} | {a["key"] for a in third["alternatives"]} == {"basher", "butterfly"}
    minutes = [c["minute"] for c in b["core"]]
    assert minutes == sorted(minutes)
    assert not {"maelstrom", "phase_boots", "power_treads", "travel_boots", "tpscroll"} & set(core)
    assert all(not s["key"].startswith("recipe_") for s in b["situational"])


def test_other_positions_and_unparsed_are_ignored():
    records = [game_a(True) for _ in range(20)] + [game_a(True) | {"pos": 3}] * 5 + [{"m": 1, "unparsed": True}]
    assert sq.builds(records, BS, 1)["games"] == 20


def test_dominant_opening_split_by_third_item():
    records = [game_a(i % 2 == 0) for i in range(20)] + [game_a(i % 3 == 0, third="butterfly") for i in range(18)]
    res = sq.builds(records, BS, 1)
    assert [b["games"] for b in res["builds"]] == [20, 18]
    assert [e["key"] for e in res["builds"][1]["core"]][:3] == ["mjollnir", "black_king_bar", "butterfly"]
    assert all(e["share"] == 1.0 for e in res["builds"][1]["core"][:3])


def test_skill_levels_keep_talent_gaps():
    skills = (["bloodseeker_blood_bath", "bloodseeker_thirst"] * 5
              + ["special_bonus_unique_bloodseeker_5"] + ["bloodseeker_bloodrage"] * 5
              + ["dota_base_ability", "bloodseeker_rupture"])
    records = [rec(True, game_a(True)["items"], skills=skills) for _ in range(20)]
    lv = {s["level"]: s["key"] for s in sq.builds(records, BS, 1)["builds"][0]["skills"]}
    assert lv[11] == "talent" and lv[12] == "bloodseeker_bloodrage"
    assert lv[16] == "bloodseeker_bloodrage" and 17 not in lv and 19 not in lv  # no skill point there
    assert lv[18] == "talent" and lv[20] == "bloodseeker_rupture"
