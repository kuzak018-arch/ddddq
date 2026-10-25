"""«Кто заруинил»: ratings from an OpenDota match (with and without Stratz), the verdict."""

import pytest

from drafter import ruin
from drafter.data import constants

pytestmark = pytest.mark.skipif(not (constants.DIR / "heroes.json").exists(), reason="нужны константы героев")

HEROES = [1, 2, 5, 8, 14, 18, 22, 26, 30, 35]


def od_player(slot, hero, *, k=5, d=5, a=10, gpm=500, pct=0.5, lane=1, wards=0, dead=120):
    b = {key: {"raw": 0, "pct": pct} for key in ("gold_per_min", "xp_per_min", "kills_per_min", "last_hits_per_min",
                                                   "hero_damage_per_min", "hero_healing_per_min", "tower_damage")}
    return {"player_slot": slot, "hero_id": hero, "isRadiant": slot < 128, "kills": k, "deaths": d, "assists": a,
            "last_hits": gpm // 3, "denies": 5, "gold_per_min": gpm, "xp_per_min": gpm, "net_worth": gpm * 40,
            "hero_damage": gpm * 40, "tower_damage": gpm * 3, "hero_healing": 0, "obs_placed": wards, "sen_placed": wards,
            "life_state_dead": dead, "lane": lane, "benchmarks": b, "personaname": f"p{slot}", "kills_log": []}


def match(radiant_win=False, bad=None):
    """Radiant: 0 mid, 1-2 cores, 3-4 supports; Dire the same. `bad`: the index made to play terribly."""
    ps = []
    for i, hero in enumerate(HEROES):
        slot = i if i < 5 else 128 + i - 5
        j = i % 5
        gpm = [650, 600, 550, 300, 250][j]
        lane = [2, 1, 3, 3, 1][j] if i < 5 else [2, 3, 1, 1, 3][j]
        p = od_player(slot, hero, gpm=gpm, lane=lane, wards=8 if j >= 3 else 0)
        if i == bad:
            p.update(deaths=16, kills=1, assists=2, life_state_dead=900)
            p["benchmarks"] = {k: {"raw": 0, "pct": 0.08} for k in p["benchmarks"]}
        ps.append(p)
    return {"opendota": {"match_id": 1, "version": 21, "duration": 2400, "radiant_win": radiant_win, "players": ps,
                         "radiant_gold_adv": [0, 500, 4200, 1000, -6000]}, "id": 1}


def test_the_clear_ruiner_of_the_losing_team_is_named_with_reasons():
    out = ruin.analyze(match(radiant_win=False, bad=1))
    v = out["verdict"]
    assert v["ruiner"] == HEROES[1] and v["kind"] == "sure" and v["mvp"] in HEROES[5:]
    bad = next(p for p in out["players"] if p["hero"] == HEROES[1])
    assert bad["tag"] == "ruiner" and bad["rating"] < 30 and any("смерт" in r for r in bad["worst"])
    assert v["turn"] == {"lead": 4200, "minute": 2}      # the losing radiant had +4.2k at minute 2


def test_an_even_loss_names_nobody():
    out = ruin.analyze(match(radiant_win=True))
    assert out["verdict"]["kind"] == "together"
    assert not any(p.get("tag") == "ruiner" for p in out["players"])


def test_positions_are_inferred_without_stratz():
    out = ruin.analyze(match())
    radiant = {p["hero"]: p["pos"] for p in out["players"] if p["radiant"]}
    assert radiant[HEROES[0]] == 2 and sorted(radiant.values()) == [1, 2, 3, 4, 5]


def test_a_support_is_not_judged_by_farm():
    out = ruin.analyze(match())
    sup = next(p for p in out["players"] if p["radiant"] and p["pos"] == 5)
    assert "farm" in sup["parts"] and "support" in sup["parts"] and "objectives" not in sup["parts"]


def test_stratz_alone_is_enough():
    sz = {"didRadiantWin": True, "durationSeconds": 1800, "topLaneOutcome": "RADIANT_STOMP",
          "players": [{"heroId": h, "isRadiant": i < 5, "position": f"POSITION_{i % 5 + 1}", "lane": "SAFE_LANE",
                       "kills": 3, "deaths": 12 if i == 7 else 4, "assists": 5, "numLastHits": 100, "goldPerMinute": 400,
                       "experiencePerMinute": 400, "networth": 9000, "heroDamage": 9000, "towerDamage": 500,
                       "imp": -40 if i == 7 else 0} for i, h in enumerate(HEROES)]}
    out = ruin.analyze({"id": 2, "stratz": sz})
    assert out["verdict"]["ruiner"] == HEROES[7] and out["sources"] == ["Stratz"]
