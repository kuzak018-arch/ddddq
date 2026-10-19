import numpy as np
import pytest

from drafter.data import constants
from drafter.lane import analysis, outcome, pairs, service

pytestmark = pytest.mark.skipif(not (constants.DIR / "items.json").exists(), reason="нужны константы")

STORM, PUCK = 17, 13


def player(radiant, pos, lane, nw, xp, lvl, items=(), win=False):
    return {"r": radiant, "pos": pos, "lane": lane, "w": win, "nw": nw, "xp": xp, "lh": [0] * len(nw),
            "lvl": lvl, "items": [list(x) for x in items]}


def match(i, storm_gain, puck_gain, storm_lane="MID_LANE", puck_pos=2, storm_items=(), lvl6_storm=420):
    """Storm earns storm_gain(t) per minute, Puck puck_gain(t); Storm is Radiant."""
    nw_s, nw_p = [600], [600]
    for t in range(1, 21):
        nw_s.append(nw_s[-1] + storm_gain(t))
        nw_p.append(nw_p[-1] + puck_gain(t))
    lv_s = [-89, 40, 100, 170, 240, lvl6_storm, 520, 600, 700]
    lv_p = [-89, 40, 100, 170, 240, 400, 500, 600, 700]
    return {"m": i, "t": 0, "dur": 2400, "p": {
        str(STORM): player(True, 2, storm_lane, nw_s, [x // 2 for x in nw_s], lv_s, storm_items, win=i % 2 == 0),
        str(PUCK): player(False, puck_pos, "MID_LANE", nw_p, [x // 2 for x in nw_p], lv_p),
    }}


def test_usable_needs_positions_and_the_same_physical_lane():
    ok = match(1, lambda t: 300, lambda t: 300)
    assert pairs.usable(ok, STORM, 2, PUCK, 2) and pairs.usable(ok, PUCK, 2, STORM, 2)
    assert not pairs.usable(match(2, lambda t: 300, lambda t: 300, puck_pos=1), STORM, 2, PUCK, 2)
    assert not pairs.usable(match(3, lambda t: 300, lambda t: 300, storm_lane="SAFE_LANE"), STORM, 2, PUCK, 2)
    assert not pairs.usable({"m": 4, "unparsed": True}, STORM, 2, PUCK, 2)
    # Radiant safe lane (bottom) faces Dire's off lane (also bottom)
    side = match(5, lambda t: 300, lambda t: 300)
    side["p"][str(STORM)].update(pos=1, lane="SAFE_LANE")
    side["p"][str(PUCK)].update(pos=3, lane="OFF_LANE")
    assert pairs.usable(side, STORM, 1, PUCK, 3)


def test_curves_windows_and_overspike():
    # even until minute 7, then Storm (level 6 at 7:00, Bottle at 4:00) gains 120 a minute more
    gain = lambda t: 300 + (120 if t > 7 else 0)
    recs = [match(i, gain, lambda t: 300, storm_items=[(-80, "tango"), (240, "bottle")]) for i in range(20)]
    res = analysis.analyze(recs, STORM, 2, PUCK, 2)
    assert res["games"] == 20 and not res["reliable"]
    c = {x["minute"]: x for x in res["curves"]}
    assert c[5]["nw"] == 0 and c[10]["nw"] == 3 * 120 and c[10]["ahead"] == 1.0
    assert res["phases"][0]["leader"] is None and res["phases"][-1]["leader"] == "hero"
    ev = {(e["side"], e["key"]): e for e in res["events"]}
    assert ev[("hero", "level6")]["minute"] == 7.0 and ev[("hero", "level6")]["spike"]
    assert ev[("hero", "bottle")]["minute"] == 4.0 and not ev[("hero", "bottle")]["spike"]
    assert ("hero", "tango") not in ev    # consumables are not spikes
    assert not ev[("enemy", "level6")]["spike"]
    nw = [w for w in res["windows"] if w["metric"] == "nw"]
    assert len(nw) == 1 and nw[0]["leader"] == "hero" and nw[0]["from"] == 6 and nw[0]["spike"] == "6 уровень"
    # the same matches seen from Puck's side mirror the gap
    back = analysis.analyze(recs, PUCK, 2, STORM, 2)
    assert {x["minute"]: x["nw"] for x in back["curves"]}[10] == -360


def test_too_few_matches_give_no_curves():
    res = analysis.analyze([match(i, lambda t: 300, lambda t: 300) for i in range(5)], STORM, 2, PUCK, 2)
    assert res["games"] == 5 and "curves" not in res


def test_outcome_summary():
    row = {"matchCount": 200, "winCount": 40, "drawCount": 60, "lossCount": 80, "stompWinCount": 5, "stompLossCount": 20}
    s = outcome.summarize(row, "LEGEND_ANCIENT", 2963)
    assert s["rated"] == 180 and s["edge"] == round(-40 / 180, 3) and s["reliable"]
    assert outcome.summarize(None, "ALL", None) is None


def test_opponents_from_draft():
    pos_mat = np.full((200, 5), 0.01)
    pos_mat[1] = [0.9, 0.05, 0.03, 0.01, 0.01]    # carry
    pos_mat[2] = [0.02, 0.03, 0.9, 0.03, 0.02]    # offlaner
    pos_mat[3] = [0.01, 0.01, 0.03, 0.15, 0.8]    # hard support
    pos_mat[4] = [0.01, 0.9, 0.05, 0.03, 0.01]    # mid
    opp = service.opponents(1, [3, 4, 1, 2], pos_mat)
    assert opp[0]["hero"] == 2 and opp[0]["main"] and opp[0]["pos"] == 3
    on = {o["hero"]: o["on_lane"] for o in opp}
    assert on == {2: True, 3: False, 4: False, 1: False}
    # the hard support could come to my lane as a 4 (15% of its games); the mid never does
    lane_pos = {o["hero"]: o["lane_pos"] for o in opp}
    assert lane_pos[3] == 4 and lane_pos[4] is None and lane_pos[1] is None
    assert service.opponents(2, [3, 4], pos_mat)[0] == {"hero": 4, "pos": 2, "on_lane": True, "lane_pos": 2, "main": True}
    # only enemy is a carry while I am the carry: it is not on my lane, nobody is forced there
    solo = service.opponents(1, [1], pos_mat)
    assert solo == [{"hero": 1, "pos": 1, "on_lane": False, "lane_pos": None, "main": False}]


def test_effective_position():
    pos_mat = np.full((200, 5), 0.01)
    pos_mat[2] = [0.004, 0.023, 0.929, 0.028, 0.016]   # Axe
    assert service.effective_pos(2, 1, pos_mat) == 3 and service.effective_pos(2, 3, pos_mat) == 3


def test_verdict_needs_enough_lanes():
    few = outcome.summarize({"matchCount": 4, "winCount": 3, "drawCount": 0, "lossCount": 0,
                             "stompWinCount": 0, "stompLossCount": 0}, "LEGEND_ANCIENT", 1)
    assert few["win_share"] == 1.0 and not few["enough"]


def test_bulk_plan(monkeypatch):
    from drafter.lane import bulk
    k = 160
    counts = np.zeros((k, k), dtype=np.int64)
    pos_mat = np.zeros((k, 5))
    pos_mat[10] = [0.9, 0.05, 0.03, 0.01, 0.01]     # my pool carry
    pos_mat[20] = [0.02, 0.03, 0.9, 0.03, 0.02]     # frequent offlaner
    pos_mat[21] = [0.02, 0.03, 0.9, 0.03, 0.02]     # rare offlaner
    pos_mat[30] = [0.01, 0.95, 0.02, 0.01, 0.01]    # two mids
    pos_mat[31] = [0.01, 0.95, 0.02, 0.01, 0.01]
    for a, b, n in ((10, 20, 5000), (10, 21, 20), (30, 31, 8000)):
        counts[a, b] = counts[b, a] = n
    monkeypatch.setattr(bulk, "pair_counts", lambda: counts)
    plan = bulk.plan(pos_mat, [(10, 1)])
    keys = [(p["a"], p["pa"], p["b"], p["pb"], p["why"]) for p in plan]
    assert keys[0] == (10, 1, 20, 3, "pool")                 # the main lane opponent first
    assert all(k[0] == 10 and k[4] == "pool" for k in keys)  # only my pool: no frequent pairs of others
    assert not any(p["b"] == 21 for p in plan)               # expected < RARE: nothing to download
    both = bulk.plan(pos_mat, [(30, 2), (31, 2)])            # two pool mids
    assert [(p["a"], p["b"]) for p in both] == [(30, 31)]    # mid vs mid once, whichever side


# ---------- loading a pair: several matches per request -------------------------------------

def stratz_match(mid, a=STORM, b=PUCK, parsed=True):
    def pl(hero, radiant):
        stats = {"networthPerMinute": [600, 900, 1300], "experiencePerMinute": [0, 300, 320],
                 "lastHitsPerMinute": [0, 4, 5], "level": [0, 60, 130], "itemPurchases": [{"time": 30, "itemId": 1}]}
        return {"heroId": hero, "isRadiant": radiant, "position": "POSITION_2", "lane": "MID_LANE",
                "isVictory": radiant, "stats": stats if parsed else {}}
    return {"id": mid, "startDateTime": 1, "durationSeconds": 2000, "players": [pl(a, True), pl(b, False)]}


class FakeStratz:
    """Answers aliased match queries; refuses any query of more than `limit` matches as too big."""

    def __init__(self, limit=8, missing=()):
        self.limit, self.missing, self.sizes = limit, set(missing), []

    def q_all(self, query, retries=5):
        import re
        ids = [int(x) for x in re.findall(r"match\(id: (\d+)\)", query)]
        self.sizes.append(len(ids))
        if len(ids) > self.limit:
            raise RuntimeError('Stratz: [{"message": "The maximum allowed operation complexity was exceeded."}]')
        data = {f"m{i}": (None if mid in self.missing else stratz_match(mid)) for i, mid in enumerate(ids)}
        return data, [{"message": "match not found"}] if self.missing & set(ids) else []

    def close(self):
        pass


@pytest.fixture()
def pair_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(pairs, "CACHE", tmp_path)
    monkeypatch.setattr(pairs, "BATCH_FILE", tmp_path / "batch.json")
    monkeypatch.setattr(pairs.sm, "_budget_ok", lambda floor: True)
    return tmp_path


def test_batch_shrinks_when_refused_and_remembers(pair_cache):
    sz = FakeStratz(limit=8, missing={105})
    recs, spent = pairs.fetch_batch(sz, list(range(100, 125)), STORM, PUCK)
    assert [r["m"] for r in recs] == list(range(100, 125))            # every match, in order
    assert next(r for r in recs if r["m"] == 105).get("unparsed")     # one Stratz hasn't got: the rest kept
    assert sz.sizes[0] == pairs.BATCH_START and sz.sizes[1] == pairs.BATCH_START // 2
    st = pairs.batch_state()
    assert st["refused"] in (9, 10) and st["size"] <= 8 and st["max_ok"] >= 5   # grew back up to the edge once
    assert spent == len(sz.sizes)                                     # the refusal costs a request too
    # next time: no refusal, never above what Stratz refused
    sz2 = FakeStratz(limit=8)
    pairs.fetch_batch(sz2, list(range(200, 240)), STORM, PUCK)
    assert max(sz2.sizes) <= 8 and len(sz2.sizes) == 5                  # 40 matches in 5 requests, none refused


def test_collect_loads_the_target_in_a_few_requests(pair_cache, monkeypatch):
    sz = FakeStratz(limit=30)
    monkeypatch.setattr(pairs.stratz, "Stratz", lambda **kw: sz)
    monkeypatch.setattr(pairs, "candidates", lambda a, b, exclude: [m for m in range(1, 200) if m not in exclude])
    info, seen = {}, []
    have = pairs.collect(STORM, 2, PUCK, 2, 25, info=info, progress=lambda h, t, n: seen.append((h, n)))
    assert have >= 25 and info["reason"] == "target"
    assert info["requests"] <= 4 and info["requests"] == len(sz.sizes)   # not one request per match
    assert seen[-1] == (have, info["requests"])                          # progress: matches and requests
    # opened again: everything from the cache, no request
    sz.sizes.clear()
    assert pairs.collect(STORM, 2, PUCK, 2, 25, info={}) == have and not sz.sizes
