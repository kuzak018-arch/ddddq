"""How a match is judged: label from IMP and the result, reasons from the norm, the summary."""

import time

import pytest

from drafter.data import my_matches as mm

ME = 1477734386


def rec(match_id, win, imp, *, nw=15000, norm_nw=15000, deaths=5, norm_deaths=5.0, cs10=40, norm_cs10=40,
        lane="SAFE_LANE", radiant=True, lanes=None, parsed=True, team=None, start=0):
    return {
        "id": match_id, "start": start, "duration": 31 * 60, "radiant_win": win == radiant, "parsed": parsed,
        "lanes": lanes or {"top": "TIE", "mid": "TIE", "bot": "TIE"},
        "me": {"hero": 4, "radiant": radiant, "win": win, "pos": 1, "lane": lane, "k": 6, "d": deaths, "a": 6,
               "lh": 230, "dn": 10, "gpm": 465, "xpm": 560, "nw": nw, "hd": 18000, "td": 1800, "imp": imp,
               "award": None, "cs10": cs10, "nw10": 3400},
        "norm": {"t": 31, "nw": norm_nw, "xp": 17360, "kills": 7, "deaths": norm_deaths, "assists": 7,
                 "hd": 18000, "td": 1800, "cs10": norm_cs10, "nw10": 3400},
        "team": team,
    }


def test_labels_follow_result_and_imp():
    cases = [(True, 25, "carried"), (True, 0, "won_together"), (True, -20, "team_carried"),
             (False, 15, "lost_played_well"), (False, 3, "lost_together"), (False, -30, "threw")]
    for win, imp, key in cases:
        assert mm.assess(rec(1, win, imp))["label_key"] == key


def test_reasons_carry_numbers_in_the_labels_direction():
    bad = mm.assess(rec(1, False, -30, nw=11000, norm_nw=15000, deaths=11, norm_deaths=4.5,
                        lanes={"top": "TIE", "mid": "TIE", "bot": "DIRE_STOMP"}))
    assert bad["label"] == "слил игру я"
    text = " ".join(bad["reasons"])
    # the two worst deviations win: 11 deaths against 4.5 and a stomped lane outweigh -27% networth
    assert "IMP -30" in text and "смертей 11 при норме 4.5" in text and "линия проиграна с разгромом" in text
    assert bad["metrics"]["nw"] == round((11000 / 15000 - 1) * mm.WEIGHTS["nw"], 3)
    only_nw = mm.assess(rec(5, False, -30, nw=11000, norm_nw=15000))
    assert any("нетворс 11k при норме 15k к 31-й минуте (-27%)" == r for r in only_nw["reasons"])
    good = mm.assess(rec(2, True, 30, nw=19000, norm_nw=15000, cs10=60, norm_cs10=40))
    assert any("+27%" in r for r in good["reasons"]) and any("+50%" in r for r in good["reasons"])


def test_lane_side_and_team_context():
    team = [{"acc": ME, "hero": 4, "radiant": False, "pos": 1, "nw": 15000, "imp": 20}] + \
           [{"acc": i, "hero": 10 + i, "radiant": False, "pos": 2 + i % 4, "nw": 9000 + i, "imp": -25} for i in range(4)] + \
           [{"acc": 100 + i, "hero": 20 + i, "radiant": True, "pos": 1 + i, "nw": 12000, "imp": 10} for i in range(5)]
    r = rec(3, False, 20, radiant=False, lane="SAFE_LANE", lanes={"top": "DIRE_VICTORY", "mid": "TIE", "bot": "TIE"}, team=team)
    a = mm.assess(r)
    assert mm.lane_result(r) == "won"               # Dire's safe lane is the top one
    assert a["nw_place"] == 1 and a["team_imp"] == -25
    assert a["label"] == "проиграл, хотя сыграл хорошо" and any("остальных в команде -25" in x for x in a["reasons"])


def test_unparsed_match_waits(monkeypatch):
    a = mm.assess(rec(4, True, None, parsed=False, start=time.time() - 3600))
    assert a["status"] == "queued" and "запрос на разбор" in a["pending"] and "label" not in a


def test_summary_splits_losses(monkeypatch, tmp_path):
    data = {"fetched": 1, "matches": {str(i): r for i, r in enumerate([
        rec(1, False, -30, start=5), rec(2, False, 20, start=4), rec(3, False, 0, start=3),
        rec(4, True, 30, start=2), rec(5, True, None, parsed=False, start=time.time() - 600)])}}
    monkeypatch.setattr(mm, "load", lambda: data)
    h = mm.history()
    s = h["summary"]
    assert (s["losses"], s["losses_me"], s["losses_team"], s["losses_together"]) == (3, 1, 1, 1)
    assert (s["wins"], s["wins_me"], s["pending"]) == (1, 1, 1)
    assert [m["id"] for m in h["matches"]] == [5, 1, 2, 3, 4]     # newest first
    assert [m["status"] for m in h["matches"]] == ["queued", "parsed", "parsed", "parsed", "parsed"]


def team_of(my_imp, mates_imp, radiant=True):
    return [{"acc": ME, "hero": 4, "radiant": radiant, "pos": 1, "nw": 15000, "imp": my_imp}] + \
           [{"acc": i, "hero": 10 + i, "radiant": radiant, "pos": 2 + i, "nw": 9000, "imp": mates_imp} for i in range(4)]


def test_blame_is_relative_to_the_team():
    # everyone played badly: not "I threw", a loss together
    assert mm.assess(rec(1, False, -48, team=team_of(-48, -42)))["label_key"] == "lost_together"
    # the rest did clearly better: on me
    assert mm.assess(rec(2, False, -30, team=team_of(-30, 5)))["label_key"] == "threw"
    # I was good and so was everyone: a win together, not "carried"
    assert mm.assess(rec(3, True, 25, team=team_of(25, 20)))["label_key"] == "won_together"
    assert mm.assess(rec(4, True, 25, team=team_of(25, -5)))["label_key"] == "carried"


# ---------- matches without a parse ------------------------------------------------------------

HOUR = 3600


def unparsed(win=False, *, start=None, norm=True, **me):
    r = rec(9, win, None, parsed=False, start=start if start is not None else time.time() - 3 * 24 * HOUR)
    r["me"].update(me)
    r["norm"]["cs"] = 230
    if not norm:
        r["norm"] = None
    return r


def test_old_unparsed_match_gets_a_simplified_estimate():
    bad = mm.assess(unparsed(False, nw=9000, xpm=380, lh=120, hd=9000, k=1, a=3, d=12))
    assert bad["status"] == "simple" and bad["simple"] and bad["label_key"] == "threw"
    assert bad["reasons"][0].startswith("упрощённая оценка") and any("смертей 12" in x for x in bad["reasons"])
    even = mm.assess(unparsed(True))                         # the numbers of the norm: won together
    assert even["label_key"] == "won_together" and abs(even["simple_score"]) < 0.05
    # a support's thin farm counts for less: the same numbers judge milder
    core = mm.simplified(unparsed(False, pos=1, nw=9000, lh=100))
    sup = mm.simplified(unparsed(False, pos=5, nw=9000, lh=100))
    assert sup["simple_score"] > core["simple_score"]


BENCH = {m: [{"percentile": p, "value": v * k} for p, v in ((0.1, 0.6), (0.5, 1.0), (0.9, 1.4), (0.99, 1.8))]
         for m, k in (("gold_per_min", 500), ("xp_per_min", 600), ("last_hits_per_min", 7), ("hero_damage_per_min", 600),
                      ("kills_per_min", 0.2))}


def test_without_the_norm_opendota_benchmarks_are_used():
    m = 31  # minutes in rec()
    good = mm.assess(unparsed(True, norm=False, gpm=700, xpm=840, lh=int(9.8 * m), hd=int(840 * m), k=int(0.28 * m)), BENCH)
    assert good["simple_source"] == "benchmarks" and good["label_key"] == "carried"
    assert any("GPM 700 — лучше, чем в 90% игр" in x for x in good["reasons"])
    assert mm._percentile(BENCH["gold_per_min"], 400) == pytest.approx(0.3)
    nothing = mm.assess(unparsed(True, norm=False))
    assert nothing["status"] == "simple" and "не хватает данных" in nothing["pending"]


def test_parse_status():
    now = time.time()
    fresh = unparsed(start=now - HOUR)
    assert mm.parse_status(fresh, now) == "queued"
    assert mm.parse_status({**fresh, "parse": {"state": "unavailable"}}, now) == "simple"   # the replay is gone
    assert mm.parse_status({**fresh, "parse": {"state": "replay"}}, now) == "queued"        # Stratz still to parse
    assert "OpenDota её разобрал" in mm.assess({**fresh, "parse": {"state": "replay"}})["pending"]
    assert mm.parse_status(fresh, now + mm.PARSE_WAIT_S) == "simple"                        # waited a day
    assert mm.parse_status(rec(1, True, 5)) == "parsed"


class FakeOD:
    def __init__(self, jobs, versions, refuse=()):
        self.jobs, self.versions, self.refuse, self.calls = jobs, versions, set(refuse), []

    def post(self, path, params=None):
        self.calls.append(("POST", path))
        mid = int(path.rsplit("/", 1)[1])
        if mid in self.refuse:
            raise RuntimeError("400 match ID not found")
        return {"job": {"jobId": mid * 10}}

    def get(self, path, params=None):
        self.calls.append(("GET", path))
        if path.startswith("/request/"):
            return {"jobId": 1} if self.jobs.get(int(path.rsplit("/", 1)[1])) else None
        if path.startswith("/matches/"):
            return {"version": self.versions.get(int(path.rsplit("/", 1)[1]))}
        if path == "/benchmarks":
            return {"hero_id": params["hero_id"], "result": BENCH}
        raise AssertionError(path)

    def close(self):
        pass


def test_parse_requests_are_sent_once_and_followed(monkeypatch, tmp_path):
    monkeypatch.setattr(mm, "CACHE", tmp_path / "m.json")
    monkeypatch.setattr(mm, "BENCH", tmp_path / "b.json")
    now = time.time()
    recs = {i: dict(unparsed(start=now - HOUR), id=i) for i in (1, 2, 3, 4, 5)}
    data = {"matches": {str(i): r for i, r in recs.items()}}
    od = FakeOD(jobs={10: True}, versions={2: 7}, refuse={3})   # jobs by job id, versions by match
    monkeypatch.setattr(mm, "OpenDota", lambda: od)
    mm._follow_parses(list(recs.values()), data)
    posts = [c for c in od.calls if c[0] == "POST"]
    assert len(posts) == mm.PARSE_PER_REFRESH                 # OpenDota counts each as 10 calls
    states = {i: (data["matches"][str(i)].get("parse") or {}).get("state") for i in recs}
    assert list(states.values()).count("queued") == 2 and list(states.values()).count("unavailable") == 1
    # later: the rest are requested, and the finished jobs are looked at
    od.calls.clear()
    for r in data["matches"].values():
        if r.get("parse"):
            r["parse"]["checked"] -= mm.PARSE_CHECK_S
    mm._follow_parses(list(data["matches"].values()), data)
    assert sum(1 for c in od.calls if c[0] == "POST") == 2     # never twice for the same match
    assert ("GET", "/request/10") in od.calls
    for mid, want in ((1, "queued"), (2, "replay")):           # match 2's job is done and the replay parsed
        st = data["matches"][str(mid)]["parse"]
        assert st["state"] == want, (mid, st)
    assert mm.load()["matches"]["2"]["parse"]["state"] == "replay"   # written as it goes


def test_benchmarks_are_fetched_for_simplified_matches(monkeypatch, tmp_path):
    monkeypatch.setattr(mm, "CACHE", tmp_path / "m.json")
    monkeypatch.setattr(mm, "BENCH", tmp_path / "b.json")
    r = dict(unparsed(norm=False), id=8, parse={"requested": 1, "state": "unavailable"})
    data = {"matches": {"8": r}}
    od = FakeOD({}, {})
    monkeypatch.setattr(mm, "OpenDota", lambda: od)
    mm._follow_parses([r], data)
    assert ("GET", "/benchmarks") in od.calls and "4:core" in mm._bench_load()
    monkeypatch.setattr(mm, "load", lambda: data)
    row = mm.history()["matches"][0]
    assert row["status"] == "simple" and row["simple"] and row["simple_source"] == "benchmarks"


def test_waiting_matches_are_rechecked_sooner(monkeypatch):
    started = []
    monkeypatch.setattr(mm.config, "settings", lambda: type("S", (), {"stratz_token": "t", "account_id": 1})())
    monkeypatch.setattr(mm.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: started.append(1)})())
    monkeypatch.setattr(mm, "_job", {"status": "done"})
    fetched = time.time() - mm.REFRESH_QUEUED_S - 5
    monkeypatch.setattr(mm, "load", lambda: {"fetched": fetched, "matches": {"1": rec(1, True, 5)}})
    mm.ensure_fresh()
    assert not started                                         # nothing waits: every 20 minutes
    monkeypatch.setattr(mm, "load", lambda: {"fetched": fetched, "matches": {"1": unparsed(start=time.time() - HOUR)}})
    mm.ensure_fresh()
    assert started


def test_stratz_schema_is_searched_for_a_parse_request():
    class SZ:
        def q(self, query):
            assert "__schema" in query
            return {"__schema": {"mutationType": {"fields": [
                {"name": "stratz", "type": {"name": "StratzMutation", "fields": [
                    {"name": "matchRetry", "args": [{"name": "id"}]}, {"name": "follow", "args": []}]}},
                {"name": "yogurt", "type": {"name": "Y", "fields": []}}]}}}

    r = mm.probe_stratz(SZ())
    assert r["found"] == [{"name": "stratz.matchRetry", "args": ["id"]}] and r["mutations"] == 2

    class Down:
        def q(self, query):
            raise RuntimeError("introspection disabled")

    assert mm.probe_stratz(Down())["error"]
