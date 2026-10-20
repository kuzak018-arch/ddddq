"""«Игры топов»: Stratz and OpenDota matches normalized, unknown fields dropped, the cache."""

import time

import pytest

from drafter import topgames as T
from drafter.data import constants

pytestmark = pytest.mark.skipif(not (constants.DIR / "item_ids.json").exists(), reason="нужны константы")

HERO = 1  # Anti-Mage


def _player(hero, radiant, win, **extra):
    return {"heroId": hero, "steamAccountId": 100 + hero, "isVictory": win, "position": "POSITION_1", "isRadiant": radiant,
            "stats": {"itemPurchases": [{"time": -60, "itemId": 44}, {"time": 600, "itemId": 63}], "networthPerMinute": [600, 900]},
            "abilities": [{"abilityId": 5003, "time": 30, "level": 1}], "kills": 7, "deaths": 2, "assists": 5,
            "numLastHits": 300, "numDenies": 12, "goldPerMinute": 700, "experiencePerMinute": 800, "networth": 25000,
            "heroDamage": 30000, "item0Id": 63, "item1Id": 0, "neutral0Id": None, **extra}


def _match(mid=1, t=None, rank=80, heroes=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)):
    t = t if t is not None else T.patch_start() + 100
    return {"id": mid, "startDateTime": t, "durationSeconds": 2400, "rank": rank, "didRadiantWin": True,
            "players": [_player(h, i < 5, i < 5) for i, h in enumerate(heroes)]}


def test_stratz_match_normalized():
    item_ids, ability_ids = T._maps()
    rec = T._normalize_stratz(_match(), HERO, item_ids, ability_ids)
    assert rec["w"] and rec["pos"] == 1 and rec["radiant"]
    assert (rec["k"], rec["d"], rec["a"], rec["lh"], rec["gpm"], rec["nw"]) == (7, 2, 5, 300, 700, 25000)
    assert rec["items"][0][0] == -60 and isinstance(rec["items"][0][1], str)
    assert rec["allies"] == [2, 3, 4, 5] and rec["enemies"] == [6, 7, 8, 9, 10]
    assert rec["curve"] == [600, 900] and rec["final"][1] is None
    # not parsed: no purchases
    m = _match()
    m["players"][0]["stats"]["itemPurchases"] = None
    assert T._normalize_stratz(m, HERO, item_ids, ability_ids) is None


def test_unknown_stratz_fields_are_dropped_and_retried(monkeypatch):
    monkeypatch.setattr(T, "_working", {g: True for g in T._GROUPS})
    sent = []

    class Fake:
        def q(self, query):
            sent.append(query)
            if "networthPerMinute" in query:
                raise RuntimeError('Stratz: [{"message": "Cannot query field \\"networthPerMinute\\" on type \\"MatchPlayerStatsType\\"."}]')
            return {"player": {"matches": [_match()]}}

    ms = T._query_player(Fake(), 5, HERO)
    assert len(ms) == 1 and len(sent) == 2
    assert T._working["curve"] is False and T._working["score"] is True
    assert "networthPerMinute" not in sent[1] and "kills" in sent[1]


def test_other_errors_are_not_swallowed(monkeypatch):
    monkeypatch.setattr(T, "_working", {g: True for g in T._GROUPS})

    class Fake:
        def q(self, query):
            raise RuntimeError("Stratz HTTP 401: unauthorized")

    with pytest.raises(RuntimeError):
        T._query_player(Fake(), 5, HERO)


def test_pro_match_from_opendota():
    _, ability_ids = T._maps()
    players = []
    for i, h in enumerate((1, 2, 3, 4, 5, 6, 7, 8, 9, 10)):
        players.append({"hero_id": h, "player_slot": i if i < 5 else 128 + i, "isRadiant": i < 5, "lane_role": [1, 2, 3, 1, 3, 1, 2, 3, 1, 3][i],
                        "net_worth": 30000 - i * 1000, "kills": 5, "deaths": 1, "assists": 3, "last_hits": 400, "denies": 10,
                        "gold_per_min": 750, "xp_per_min": 820, "hero_damage": 20000, "item_0": 63, "item_neutral": None,
                        "purchase_log": [{"time": 500, "key": "power_treads"}], "ability_upgrades_arr": [5003], "gold_t": [0, 300, 700],
                        "name": "Yatoro" if h == 1 else None})
    m = {"match_id": 77, "start_time": T.patch_start() + 10, "duration": 2000, "radiant_win": False, "players": players,
         "radiant_team": {"name": "Spirit"}, "league": {"name": "TI"}}
    rec = T._normalize_pro(m, HERO, ability_ids)
    assert rec["name"] == "Yatoro" and rec["team"] == "Spirit" and rec["league"] == "TI"
    assert not rec["w"] and rec["pos"] == 1 and rec["curve_kind"] == "gold"
    sup = T._normalize_pro(m, 4, ability_ids)  # the poorer of the safe lane
    assert sup["pos"] == 5


def test_get_serves_the_cache_and_loads_in_the_background(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ROOT", tmp_path)
    monkeypatch.setattr(T, "_states", {})
    item_ids, ability_ids = T._maps()
    rec = T._normalize_stratz(_match(), HERO, item_ids, ability_ids)
    old = dict(rec, m=2, t=T.patch_start() - 10)  # last patch: not shown
    T._write("immortal", HERO, {"fetched": time.time(), "matches": [rec, old]})
    started = []
    monkeypatch.setattr(T.threading, "Thread", lambda **kw: type("X", (), {"start": lambda self: started.append(kw)})())
    out = T.get(HERO, "immortal")
    assert [m["m"] for m in out["matches"]] == [1] and not out["loading"] and not started
    assert out["item_cost"] and "abilities" in out
    T.get(HERO, "immortal", refresh=True)
    assert started  # a refresh loads again
    with pytest.raises(ValueError):
        T.get(HERO, "turbo")


def test_errors_become_messages(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ROOT", tmp_path)

    def no_token(*a):
        raise RuntimeError("нет STRATZ_TOKEN в .env")

    monkeypatch.setattr(T, "_fill_stratz", no_token)
    state = {"loading": True}
    T._run(HERO, "divine", state)
    assert "токена" in state["error"] and not state["loading"]
