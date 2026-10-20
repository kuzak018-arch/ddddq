"""In-game hints: timers by the map rules, the next item with its parts owned, buyback, GSI cfg upgrade."""

import pytest

from drafter import gsi, ingame

ITEMS = {"black_king_bar": {"dname": "Black King Bar", "cost": 4050, "components": ["mithril_hammer", "ogre_axe"]},
         "mithril_hammer": {"cost": 1600}, "ogre_axe": {"cost": 1000}, "blink": {"dname": "Blink Dagger", "cost": 2250}}


def payload(clock=600, gold=1500, items=("ogre_axe", "blink"), daytime=True):
    return {"map": {"game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS", "clock_time": clock, "daytime": daytime, "matchid": "1"},
            "player": {"gold": gold, "gpm": 450, "team_name": "radiant"},
            "hero": {"level": 12, "alive": True, "buyback_cost": 1200, "buyback_cooldown": 0},
            "items": {**{f"slot{i}": {"name": f"item_{k}"} for i, k in enumerate(items)}, "slot5": {"name": "empty"}}}


@pytest.mark.parametrize("clock,first,period,until,expect", [
    (-60, 0, 180, None, 60), (0, 0, 180, None, 0), (170, 0, 180, None, 10), (181, 0, 180, None, 179),
    (100, 120, 120, 240, 20), (130, 120, 120, 240, 110), (250, 120, 120, 240, None),
    (30, 360, 120, None, 330), (365, 360, 120, None, 115),
])
def test_next_spawn(clock, first, period, until, expect):
    assert ingame.next_spawn(clock, first, period, until) == expect


def test_timers_sorted_and_day_night():
    t = ingame.timers(400, False)
    assert [x["in"] for x in t] == sorted(x["in"] for x in t)
    names = {x["key"]: x for x in t}
    assert names["power"]["in"] == 80 and names["bounty"]["in"] == 140 and names["wisdom"]["in"] == 20
    assert "water" not in names and names["night"]["name"] == "День" and names["night"]["in"] == 200  # 6:40: night now, day at 10:00
    assert ingame.timers(100, True)[0]["key"] == "water"


def test_next_item_counts_owned_parts(monkeypatch):
    monkeypatch.setattr(ingame.constants, "_load", lambda name: ITEMS)
    h = ingame.hints(ingame.live_from_payload(payload()), ["blink", "black_king_bar"])
    assert h["next"]["key"] == "black_king_bar" and h["next"]["left"] == 3050 and h["next"]["missing"] == 1550
    assert h["next"]["have"] == ["ogre_axe"] and not h["next"]["ready"]
    assert h["buyback"] == {"cost": 1200, "enough": True, "missing": 0, "cooldown": 0}
    rich = ingame.hints(ingame.live_from_payload(payload(gold=5000)), ["black_king_bar"])
    assert rich["next"]["ready"]
    no_items = ingame.live_from_payload({k: v for k, v in payload().items() if k != "items"})
    assert ingame.hints(no_items, ["blink"])["next"] is None     # an old cfg without items: no item hint


def test_tracker_keeps_live_only_in_a_match():
    t = gsi.Tracker(lambda **c: None)
    t.handle(payload(), {"phase": "idle", "allies": [None] * 5, "enemies": [None] * 5, "bans": []})
    assert t.live["clock"] == 600 and t.live["items"] == ["ogre_axe", "blink"]
    t.handle({"map": {"game_state": "DOTA_GAMERULES_STATE_POST_GAME"}}, {"phase": "game"})
    assert t.live is None


def test_old_cfg_is_upgraded(tmp_path, monkeypatch):
    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    monkeypatch.setattr(gsi.dota_paths, "dota_path", lambda: dota)
    gsi.install()
    cfg = gsi.dota_paths.gsi_dir(dota) / gsi.CFG_NAME
    cfg.write_text(cfg.read_text(encoding="utf-8").replace('"items"\t\t"1"', "").replace('"items" "1"', ""), encoding="utf-8")
    assert '"items"' not in cfg.read_text(encoding="utf-8") and gsi.installed()["outdated"]
    assert gsi.upgrade() and '"items"' in cfg.read_text(encoding="utf-8") and not gsi.installed()["outdated"]
    assert not gsi.upgrade()
