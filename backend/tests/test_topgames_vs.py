"""The build of top players against a draft: matches sharing most enemy heroes, or nothing."""

import pytest

from drafter import topgames as T
from drafter.builds import sequences as sq

ITEMS = {k: {"dname": k, "cost": 3000} for k in ("power_treads", "phase_boots", "black_king_bar", "desolator", "butterfly", "monkey_king_bar", "skadi")}
HERO = 1


def match(mid, enemies, win=True, pos=1, buys=None, src_extra=None):
    buys = buys or [(300, "power_treads"), (900, "desolator"), (1500, "black_king_bar"), (2100, "butterfly")]
    return {"m": mid, "t": 1_800_000_000 + mid, "w": win, "pos": pos, "acc": 1, "rank": 80, "enemies": enemies, "allies": [11, 12, 13, 14],
            "items": [[t, k] for t, k in buys], "skills": [], **(src_extra or {})}


@pytest.fixture
def cache(monkeypatch):
    store = {"immortal": [], "divine": [], "pro": []}
    monkeypatch.setattr(T, "patch_start", lambda: 1_700_000_000)
    monkeypatch.setattr(T, "_read", lambda source, hero: {"fetched": 9e12, "matches": store[source]})
    monkeypatch.setattr(T, "load_const", lambda name: ITEMS)
    monkeypatch.setattr(T, "_ru_items", lambda: {})
    monkeypatch.setattr(sq, "_parents", lambda: {})
    monkeypatch.setattr(sq, "_is_finished_item", lambda k: k not in ("power_treads", "phase_boots"))
    monkeypatch.setattr(sq, "_cost", lambda k: 3000)
    monkeypatch.setattr(sq, "_abilities", lambda: {})
    monkeypatch.setattr(T, "_states", {})
    monkeypatch.setenv("DRAFTER_NO_BUILD_LOAD", "1")
    return store


def test_need_is_sixty_percent_and_at_least_two():
    assert [T._need(n) for n in (3, 4, 5)] == [2, 3, 3]


def test_a_draft_needs_three_known_enemies(cache):
    out = T.vs_draft(HERO, [21, 22], 1)
    assert out["found"] is False and out["reason"] == "few_enemies"


def test_matches_with_most_enemies_give_the_build(cache):
    cache["divine"] = [match(1, [21, 22, 23, 24, 25]), match(2, [21, 22, 23, 90, 91], win=False),
                       match(3, [21, 80, 81, 82, 83]), match(4, [21, 22, 23, 24, 25], buys=[(400, "phase_boots"), (950, "skadi"), (1400, "black_king_bar")])]
    cache["pro"] = [match(5, [21, 22, 25, 70, 71], src_extra={"name": "Miracle-", "team": "Team X"})]
    out = T.vs_draft(HERO, [21, 22, 23, 24, 25], 1)
    assert out["found"] and out["games"] == 4 and out["wins"] == 3 and out["full"] == 2     # match 3 shares one hero: not it
    assert out["need"] == 3 and out["checked"] == 5
    assert [m["m"] for m in out["matches"]][:2] == [4, 1]                                  # the closest draft first, the newer one first
    assert out["boots"]["key"] == "power_treads" and out["boots"]["share"] == 0.75
    keys = [c["key"] for c in out["core"]]
    assert "black_king_bar" in keys and out["core"][0]["minute"] <= out["core"][-1]["minute"]
    assert out["sources"] == {"Divine+": 3, "Про-матчи": 1}


def test_nothing_similar_is_an_answer_not_an_error(cache):
    cache["divine"] = [match(1, [31, 32, 33, 34, 35]), match(2, [21, 41, 42, 43, 44])]
    out = T.vs_draft(HERO, [21, 22, 23, 24, 25], 1)
    assert out["found"] is False and out["reason"] == "none" and out["checked"] == 2 and out["error"] is None


def test_position_patch_and_dedupe(cache):
    cache["divine"] = [match(1, [21, 22, 23], pos=3), match(2, [21, 22, 23], pos=1)]
    cache["immortal"] = [match(2, [21, 22, 23], pos=1)]                                    # the same match in two caches
    out = T.vs_draft(HERO, [21, 22, 23], 1)
    assert out["games"] == 1 and out["matches"][0]["m"] == 2
    old = match(9, [21, 22, 23])
    old["t"] = 1_000_000_000                                                               # an older patch
    cache["divine"] = [old]
    cache["immortal"] = []
    assert T.vs_draft(HERO, [21, 22, 23], 1)["found"] is False


def test_loading_and_errors_are_reported(cache, monkeypatch):
    monkeypatch.setattr(T, "_states", {(HERO, "divine"): {"loading": True}, (HERO, "pro"): {"error": "нет токена"}})
    out = T.vs_draft(HERO, [21, 22, 23], 1)
    assert out["found"] is False and out["loading"] is True and out["error"] == "нет токена"
