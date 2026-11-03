import pytest

from drafter.data import abilities, constants

needs_feed = pytest.mark.skipif(not (constants.DIR / "valve_heroes" / "1.json").exists(), reason="нужны константы")


def test_short_desc_fills_numbers_and_cuts_markup():
    vals = {"mana_threshold": [60.0], "damage": [10.0, 20.0, 30.0, 40.0], "slow": [12.0, 12.0]}
    s = abilities.short_desc("<b>Атаки</b> замедляют при %mana_threshold%%% маны, урон %damage%, замедление %slow%.\\nВторой абзац.", vals)
    assert s == "Атаки замедляют при 60% маны, урон 10 / 20 / 30 / 40, замедление 12."
    assert abilities.short_desc("урон %unknown%") == "урон ?"
    long = "Первое предложение довольно длинное и подробное. " * 10
    cut = abilities.short_desc(long)
    assert len(cut) <= abilities.SHORT_DESC and cut.endswith(".")


@needs_feed
def test_hero_abilities_and_talent_targets(monkeypatch):
    monkeypatch.setattr(abilities, "ensure_icons", lambda keys, download=True: {k for k in keys if k != "antimage_persectur"})
    ab = abilities.hero_abilities(1)
    assert ab["antimage_mana_break"]["name"] == "Mana Break"
    assert "ману" in ab["antimage_mana_break"]["desc"]  # Russian description from Valve's feed
    assert ab["antimage_persectur"]["innate"] and ab["antimage_persectur"]["icon"] is None
    assert ab["antimage_blink"]["icon"] == "/icons/abilities/antimage_blink.png"
    assert abilities.talent_ability(1, "special_bonus_unique_antimage_manavoid_aoe") == "antimage_mana_void"
    assert abilities.talent_ability(1, "special_bonus_hp_regen_3") is None  # generic talent: no ability
    assert set(abilities.hero_abilities(1, {"antimage_blink"})) == {"antimage_blink"}


def test_ensure_icons_without_download_does_not_touch_network(tmp_path, monkeypatch):
    monkeypatch.setattr(abilities, "ICONS", tmp_path)
    (tmp_path / "a.png").write_bytes(b"x")

    class Boom:
        def __init__(self, *a, **k):
            raise AssertionError("network")

    monkeypatch.setattr(abilities.httpx, "Client", Boom)
    assert abilities.ensure_icons(["a", "b"], download=False) == {"a"}


@needs_feed
def test_build_response_carries_abilities_and_talent_targets():
    from drafter.builds import service
    b = {"skills": [{"level": 1, "key": "antimage_mana_break"}, {"level": 11, "key": "talent"}],
         "talents": [{"level": 10, "options": [{"key": "special_bonus_hp_regen_3"},
                                               {"key": "special_bonus_unique_antimage_manavoid_aoe"}]}]}
    ab = service._abilities(1, [b], download=False)
    assert set(ab) == {"antimage_mana_break", "antimage_mana_void"}
    assert [o["ability"] for o in b["talents"][0]["options"]] == [None, "antimage_mana_void"]


def test_details_from_a_synthetic_feed(monkeypatch):
    feed = {
        "abilities": [
            {"name": "x_nuke", "name_loc": "Удар", "type": 0, "desc_loc": "Наносит %damage% урона.",
             "notes_loc": ["Оглушение длится %stun%s сек."], "scepter_loc": "Урон %damage%.",
             "cooldowns": [10.5, 9, 7.5, 6], "mana_costs": [0, 0, 0, 0], "cast_ranges": [600, 600, 600, 600],
             "special_values": [
                 {"name": "damage", "values_float": [100, 200], "values_scepter": [300, 400], "heading_loc": "урон:"},
                 {"name": "stun", "values_float": [1.5], "heading_loc": "", "is_percentage": False},
                 {"name": "AbilityCooldown", "values_float": [10], "heading_loc": "Перезарядка:"},
                 {"name": "radius", "values_float": [300], "heading_loc": "Радиус:",
                  "bonuses": [{"name": "special_bonus_unique_x_radius", "value": 150}]},
             ]},
            {"name": "x_ult", "name_loc": "Ульта", "type": 1, "desc_loc": "", "ability_is_innate": "False"},
            {"name": "generic_hidden", "name_loc": "скрытая"},
        ],
        "talents": [{"name": "special_bonus_hp", "name_loc": "+{s:value} к здоровью",
                     "special_values": [{"name": "value", "values_float": [-200]}]},
                    {"name": "special_bonus_unique_x_radius", "name_loc": "+{s:bonus_radius} к радиусу Удара"}],
    }
    monkeypatch.setattr(constants, "valve_hero", lambda h: feed)
    monkeypatch.setattr(abilities, "hero_abilities", lambda h, download=True: {"x_nuke": {"icon": "/icons/abilities/x_nuke.png"}})
    d = abilities.details(5, download=False)
    assert d["source"] == "valve"
    nuke, ult = d["abilities"]
    assert [a["key"] for a in d["abilities"]] == ["x_nuke", "x_ult"]
    assert nuke["desc"] == "Наносит 100 / 200 урона."
    assert nuke["notes"] == ["Оглушение длится 1,5 сек."]
    assert nuke["scepter"] == "Урон 300 / 400."
    assert nuke["cooldown"] == "10,5 / 9 / 7,5 / 6"
    assert nuke["mana"] is None and nuke["range"] == "600"
    assert {"label": "Урон", "value": "100 / 200"} in nuke["values"]
    assert all(v["label"] != "Перезарядка" for v in nuke["values"])  # shown on its own line
    assert ult["ultimate"] and not ult["innate"] and ult["icon"] is None
    assert d["talents"][0]["level"] == 25 and d["talents"][-1] == {
        "level": 10, "left": "+200 к здоровью", "right": "+150 к радиусу Удара"}


def test_threats_from_a_synthetic_feed(monkeypatch):
    feed = {"abilities": [
        {"name": "x_stun", "name_loc": "Удар", "type": 0, "behavior": 8, "target_team": 2, "immunity": 4, "dispellable": 2,
         "desc_loc": "Оглушает врага на %stun% сек.", "cooldowns": [12, 10],
         "special_values": [{"name": "stun", "values_float": [1.5, 2]}]},
        {"name": "x_buff", "name_loc": "Щит", "type": 0, "behavior": 4, "target_team": 0, "dispellable": 3,
         "desc_loc": "Даёт щит.", "cooldowns": [20]},
        {"name": "x_passive", "name_loc": "Ночной охотник", "type": 0, "behavior": 2, "desc_loc": "Ночью быстрее."},
        {"name": "x_ult", "name_loc": "Дыра", "type": 1, "behavior": 4, "target_team": 0, "immunity": 3,
         "desc_loc": "Враги не могут двигаться и применять способности.", "cooldowns": [180, 160]},
    ]}
    monkeypatch.setattr(constants, "valve_hero", lambda h: feed)
    monkeypatch.setattr(abilities, "hero_abilities", lambda h, download=True: {})
    t = abilities.threats(7, download=False)
    assert t["night"] is True                                  # from the passive's text
    assert [a["key"] for a in t["abilities"]] == ["x_ult", "x_stun", "x_buff"]  # ultimate first, passive left out
    ult, stun, buff = t["abilities"]
    assert ult["pierces"] and ult["tags"] == ["безмолвие", "обездвиживание"] and ult["cooldown"] == "180 / 160"
    assert not stun["pierces"] and stun["dispel"] == "развеивается" and stun["tags"] == ["оглушение"]
    assert stun["desc"] == "Оглушает врага на 1,5 / 2 сек."
    assert buff["dispel"] is None and buff["tags"] == []       # a self-buff: dispel says nothing here


def test_synthetic_skill_order_follows_dota_rules(monkeypatch):
    from drafter.builds import standard
    feed = {"abilities": [
        {"name": "x_a", "name_loc": "A", "type": 0, "max_level": 4, "behavior": 8},
        {"name": "x_b", "name_loc": "B", "type": 0, "max_level": 4, "behavior": 8},
        {"name": "x_c", "name_loc": "C", "type": 0, "max_level": 4, "behavior": 8},
        {"name": "x_inn", "name_loc": "I", "type": 0, "max_level": 1, "ability_is_innate": "True"},
        {"name": "x_ult", "name_loc": "U", "type": 1, "max_level": 3, "behavior": 4},
    ]}
    monkeypatch.setattr(standard.constants, "valve_hero", lambda h: feed)
    out = standard.synth_skills(7, [{"key": "x_b", "first_level": 1}, {"key": "x_a", "first_level": 2}])
    by = {s["level"]: s["key"] for s in out}
    assert by[1] == "x_b" and by[2] == "x_a" and by[6] == by[12] == by[18] == "x_ult" and by[10] == "talent"
    counts = {}
    for s in out:
        counts[s["key"]] = counts.get(s["key"], 0) + 1
        if s["key"].startswith("x_") and s["key"] != "x_ult":     # level k of a basic ability from hero level 2k-1
            assert counts[s["key"]] <= (s["level"] + 1) // 2
    assert counts["x_b"] == counts["x_a"] == counts["x_c"] == 4 and counts["x_ult"] == 3 and "x_inn" not in counts
    assert [s["key"] for s in out if s["level"] <= 7].count("x_b") == 4     # the one maxed first
