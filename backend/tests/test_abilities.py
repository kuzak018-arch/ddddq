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
