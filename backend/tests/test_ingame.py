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


def _live(clock=600, level=4, abilities=(("am_a", 2), ("am_b", 1), ("am_c", 0), ("am_ult", 0)), talents=None, **extra):
    p = payload(clock=clock)
    p["hero"]["level"] = level
    p["abilities"] = {f"ability{i}": {"name": n, "level": lv} for i, (n, lv) in enumerate(abilities)}
    if talents is not None:
        p["hero"].update({f"talent_{i}": i <= talents for i in range(1, 9)})
    p["map"].update(extra)
    return ingame.live_from_payload(p)


ORDER = ["am_a", "am_b", "am_a", "am_c", "am_a", "am_ult", "am_a", "am_b", "am_b", "talent", "am_b"]


def test_next_skill_follows_the_order_and_sees_a_free_point():
    s = ingame.next_skill(_live(level=4), ORDER)
    assert s == {"key": "am_c", "at": 4, "points": 1, "now": True}
    assert ingame.next_skill(_live(level=3), ORDER)["now"] is False          # all 3 points spent
    # the user took am_b instead of am_a at 3: the order's missing am_a comes first
    s = ingame.next_skill(_live(level=4, abilities=(("am_a", 1), ("am_b", 2))), ORDER)
    assert s["key"] == "am_a" and s["at"] == 3 and s["now"]
    # level 10 with every point up to 9 spent: the talent next, known from the talent flags
    full = (("am_a", 4), ("am_b", 3), ("am_c", 1), ("am_ult", 1))
    assert ingame.next_skill(_live(level=10, abilities=full, talents=0), ORDER)["key"] == "talent"
    assert ingame.next_skill(_live(level=10, abilities=full, talents=1), ORDER)["key"] == "am_b"
    # no talent flags: a point over the abilities' levels at a talent level counts as the talent
    assert ingame.next_skill(_live(level=10, abilities=full), ORDER)["key"] == "am_b"
    no_block = ingame.live_from_payload(payload())
    assert ingame.next_skill(no_block, ORDER) is None


def test_neutral_tiers():
    assert ingame.neutral_tier(120) == {"tier": None, "ago": None, "next": 1, "in": 180}
    assert ingame.neutral_tier(16 * 60) == {"tier": 2, "ago": 60, "next": 3, "in": 540}
    assert ingame.neutral_tier(61 * 60)["next"] is None


def test_roshan_and_tormentor_marks():
    ingame._marks.clear()
    ingame._marks["match"] = None
    early = ingame.objectives(_live(clock=600))
    assert early["tormentor"] == {"source": "none", "state": "dead", "in": 300, "side": "dire"}  # 10:00 by day
    assert early["roshan"]["state"] == "alive" and early["roshan"]["pit"] is None
    ingame.mark("roshan", _live(clock=1200))
    o = ingame.objectives(_live(clock=1200 + 100))
    assert o["roshan"]["state"] == "dead" and o["roshan"]["aegis"] == 200 and o["roshan"]["in"] == 380
    o = ingame.objectives(_live(clock=1200 + 9 * 60))
    assert o["roshan"]["state"] == "maybe" and o["roshan"]["in"] == 120 and o["roshan"]["aegis"] is None
    assert ingame.objectives(_live(clock=1200 + 12 * 60))["roshan"]["state"] == "alive"
    # night (25:00–30:00): the Tormentor on the Radiant side, Roshan in the top pit
    night = ingame.objectives(_live(clock=26 * 60, daytime=False))
    assert night["night"] and night["tormentor"]["side"] == "radiant" and night["roshan"]["pit"] == "top"
    ingame.mark("tormentor", _live(clock=1500))
    assert ingame.objectives(_live(clock=1560))["tormentor"]["in"] == 540
    ingame.mark("tormentor", _live(clock=1560), undo=True)
    assert ingame.objectives(_live(clock=1560))["tormentor"]["source"] == "none"
    # another match: the marks are gone
    other = _live(clock=1300)
    other["match_id"] = "2"
    assert ingame.objectives(other)["roshan"]["source"] == "none"


def test_roshan_state_from_dota_wins_over_nothing():
    ingame._marks.clear()
    ingame._marks["match"] = None
    o = ingame.objectives(_live(clock=1500, roshan_state="respawn_variable", roshan_state_end_seconds=90))
    assert o["roshan"] == {"source": "dota", "state": "maybe", "in": 90, "pit": "bottom"}


def test_no_skill_point_levels():
    # level 18 earns 17 points (none at 17): with 17 spent there is nothing to take now
    order = ["am_a"] * 4 + ["am_b"] * 4 + ["am_c"] * 4 + ["am_ult"] * 3 + ["talent"] * 2 + ["am_d"]
    lv = (("am_a", 4), ("am_b", 4), ("am_c", 4), ("am_ult", 3))
    s = ingame.next_skill(_live(level=18, abilities=lv, talents=2), order)
    assert s["key"] == "am_d" and not s["now"]
    assert ingame.next_skill(_live(level=18, abilities=lv, talents=1), order) == {"key": "talent", "at": 17, "points": 1, "now": True}
