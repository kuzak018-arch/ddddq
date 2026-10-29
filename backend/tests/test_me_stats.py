"""The profile's statistics from the user's own history."""

import time

from drafter.data import me_stats

DAY = 86400


def match(i, hero, win, t, kills=5, deaths=5, party=1, duration=2400):
    return {"match_id": i, "hero_id": hero, "player_slot": 0, "radiant_win": win, "start_time": t, "duration": duration,
            "kills": kills, "deaths": deaths, "assists": 10, "party_size": party}


def history():
    now = 1_800_000_000
    ms = []
    t = now - 200 * DAY
    for i in range(120):
        hero = 1 if i % 3 else 14
        # every 4th session: three losses then a fourth loss (tilt), otherwise alternating
        win = (i % 8) not in (4, 5, 6, 7)
        ms.append(match(i, hero, win, t, kills=20 if i == 50 else 5, party=2 if i % 5 == 0 else 1))
        t += DAY // 2 if i % 4 == 3 else 3000  # sessions of four games: i = 4k .. 4k+3
    peers = [{"account_id": 7, "personaname": "друг", "with_games": 24, "with_win": 15, "against_games": 0, "against_win": 0}]
    heroes_vs = [{"hero_id": 2, "against_games": 20, "against_win": 5, "with_games": 3, "with_win": 3},
                 {"hero_id": 5, "against_games": 12, "against_win": 9, "with_games": 10, "with_win": 8}]
    return {"matches": ms, "peers": peers, "heroes_vs": heroes_vs}, now


def test_heroes_table_and_records():
    data, now = history()
    out = me_stats.stats(data, now)
    assert out["games"] == 120 and out["heroes"][0]["hero"] == 1 and out["heroes"][0]["games"] == 80
    am = out["heroes"][0]
    assert am["kda"] == round((am["k"] * am["games"] + am["a"] * am["games"]) / (am["d"] * am["games"]), 2)
    assert out["records"]["kills"]["value"] == 20 and out["records"]["loss_streak"] == 4


def test_tilt_after_losses_and_sessions():
    data, now = history()
    tilt = me_stats.stats(data, now)["tilt"]
    after3 = tilt["after_loss"][2]
    assert after3["games"] > 0 and after3["wr"] == 0.0       # the fourth game after three losses was lost every time
    assert [s["game"] for s in tilt["session"]] == [1, 2, 3, 4]


def test_party_peers_and_matchups():
    data, now = history()
    out = me_stats.stats(data, now)
    assert out["party"]["party"]["games"] == 24 and out["party"]["peers"][0]["name"] == "друг"
    assert out["matchups"]["hard"][0]["hero"] == 2 and out["matchups"]["hard"][0]["wr"] == 0.25


def test_empty_history():
    assert me_stats.stats({"matches": []}) == {"games": 0}


def test_hours_are_local_time():
    t = int(time.mktime((2026, 10, 1, 21, 30, 0, 0, 0, -1)))
    out = me_stats.stats({"matches": [match(1, 1, True, t)]}, t)
    assert out["when"]["hours"][21]["games"] == 1 and out["when"]["blocks"][3]["games"] == 1
