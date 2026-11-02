"""Pace of the game: net worth against the top curves, last hits against OpenDota's benchmark."""

import pytest

from drafter import pace

HERO = 14


def curves(per_minute_value, n=6, pos=1):
    return [{"m": i, "t": 2_000_000_000, "pos": pos, "curve_kind": "networth", "curve": [per_minute_value * m for m in range(40)]}
            for i in range(n)]


@pytest.fixture
def top(monkeypatch):
    store = {"immortal": [], "divine": []}
    monkeypatch.setattr(pace.topgames, "patch_start", lambda: 1_700_000_000)
    monkeypatch.setattr(pace.topgames, "_read", lambda source, hero: {"matches": store.get(source, [])})
    return store


def live(clock=600, gpm=500, last_hits=60, net_worth=None):
    return {"clock": clock, "gpm": gpm, "last_hits": last_hits, "net_worth": net_worth, "hero_id": HERO}


def test_net_worth_verdicts(top):
    top["divine"] = curves(1000)                      # top: 10 000 at minute 10
    bad = pace.networth_pace(live(net_worth=7500), HERO, 1)
    assert bad["verdict"] == "bad" and bad["top"] == 10000 and bad["diff"] == -2500 and bad["ratio"] == 0.75
    assert pace.networth_pace(live(net_worth=9500), HERO, 1)["verdict"] == "ok"
    assert pace.networth_pace(live(net_worth=11500), HERO, 1)["verdict"] == "good"


def test_estimate_from_gpm_is_marked(top):
    top["divine"] = curves(1000)
    p = pace.networth_pace(live(gpm=400), HERO, 1)     # 625 + 400 * 10
    assert p["estimated"] and p["now"] == 4625 and p["verdict"] == "bad"


def test_too_early_few_matches_other_position_and_duplicates(top):
    top["divine"] = curves(1000)
    assert pace.networth_pace(live(clock=120, net_worth=900), HERO, 1) is None            # minute 2: noise
    assert pace.networth_pace(live(net_worth=9000), HERO, 3) is None                      # nobody on that position
    top["divine"] = curves(1000, n=4)
    assert pace.networth_pace(live(net_worth=9000), HERO, 1) is None                      # under MIN_CURVES
    top["divine"] = curves(1000, n=6)
    top["immortal"] = curves(1000, n=6)                                                   # the same matches in both caches
    assert pace.networth_pace(live(net_worth=9000), HERO, 1)["games"] == 6


BENCH = {"fetched": 9e12, "lh": [{"percentile": p / 100, "value": v} for p, v in
                                  [(10, 3.0), (20, 4.0), (30, 4.8), (40, 5.4), (50, 6.0), (60, 6.6), (70, 7.2), (80, 8.0), (90, 9.0)]]}


def test_last_hits_few_and_fine(monkeypatch):
    monkeypatch.setattr(pace, "benchmark", lambda hero: BENCH)
    few = pace.last_hits_pace(live(clock=600, last_hits=36), HERO, 1)      # 3.6 per minute
    assert few["few"] and few["per_min"] == 3.6 and few["median"] == 6.0 and few["expected"] == 60 and few["percentile"] == 10
    fine = pace.last_hits_pace(live(clock=600, last_hits=70), HERO, 1)     # 7 per minute
    assert not fine["few"] and fine["percentile"] == 60


def test_last_hits_only_for_farming_positions_and_after_minute_four(monkeypatch):
    monkeypatch.setattr(pace, "benchmark", lambda hero: BENCH)
    assert pace.last_hits_pace(live(last_hits=5), HERO, 5) is None
    assert pace.last_hits_pace(live(clock=150, last_hits=5), HERO, 1) is None
    monkeypatch.setattr(pace, "benchmark", lambda hero: None)              # not downloaded yet
    assert pace.last_hits_pace(live(), HERO, 1) is None


def test_pace_is_none_without_anything_to_say(top, monkeypatch):
    monkeypatch.setattr(pace, "benchmark", lambda hero: None)
    assert pace.pace(None, HERO, 1) is None and pace.pace(live(), None, 1) is None and pace.pace(live(), HERO, None) is None
    assert pace.pace(live(), HERO, 1) is None


def test_a_missing_net_worth_field_in_gsi_is_none():
    from drafter import ingame
    p = {"map": {"clock_time": 60}, "player": {"gold": 1, "gpm": 2}, "hero": {"id": 14, "level": 1}}
    assert ingame.live_from_payload(p)["net_worth"] is None and ingame.live_from_payload(p)["hero_id"] == 14
    p["player"]["net_worth"] = 1234
    assert ingame.live_from_payload(p)["net_worth"] == 1234


def test_a_failed_benchmark_is_not_asked_for_on_every_poll(tmp_path, monkeypatch):
    monkeypatch.setattr(pace, "DIR", tmp_path)
    monkeypatch.setattr(pace, "_failed", {})
    monkeypatch.setattr(pace, "_loading", set())

    class Broken:
        def __init__(self, *a, **kw):
            pass

        def get(self, *a, **kw):
            raise RuntimeError("OpenDota 400")

        def close(self):
            pass

    monkeypatch.setattr(pace, "OpenDota", Broken)
    started = []
    monkeypatch.setattr(pace.threading, "Thread", lambda target, args, **kw: type("T", (), {"start": lambda self: started.append((target, args))})())
    assert pace.benchmark(HERO) is None
    target, args = started[0]
    target(*args)   # the download runs (and fails) outside the lock, as in its own thread
    for _ in range(5):
        assert pace.benchmark(HERO) is None
    assert len(started) == 1 and HERO in pace._failed
