"""The background lane download: needs no data, everything it would download is stubbed."""

import threading
import types

from drafter.lane import bulk


def test_bulk_job_survives_a_restart(monkeypatch, tmp_path):
    """Started by the user: the wish outlives the app; on the next start the job resumes by itself
    and skips pairs it already has; a finished job or the user's stop is not resumed."""
    monkeypatch.setattr(bulk, "STATE_FILE", tmp_path / "bulk.json")
    monkeypatch.setattr(bulk.config, "settings", lambda: types.SimpleNamespace(stratz_token="t"))
    todo = [{"a": 10, "pa": 1, "b": 20, "pb": 3, "why": "pool"}, {"a": 30, "pa": 2, "b": 31, "pb": 2, "why": "all"}]
    monkeypatch.setattr(bulk, "plan", lambda pos_mat, pool: [dict(p) for p in todo])
    monkeypatch.setattr(bulk, "_pool", lambda pos_mat: [(10, 1)])
    have = {(10, 20): bulk.BULK_TARGET, (30, 31): 0}   # the pool pair was downloaded before the restart
    monkeypatch.setattr(bulk, "_have", lambda p: have[(p["a"], p["b"])])
    fetched, gate, inside = [], threading.Event(), threading.Event()

    def collect(a, pa, b, pb, target, *, stop, info, **kw):
        fetched.append((a, b))
        inside.set()
        gate.wait(5)                         # hold the job here until the test lets it go
        info["reason"] = "stopped" if stop.is_set() else "target"
        if not stop.is_set():
            have[(a, b)] = target
        return have[(a, b)]

    monkeypatch.setattr(bulk.pairs, "collect", collect)

    bulk.start(None)
    assert bulk.wanted() and inside.wait(5)
    bulk.shutdown()                          # the app exits mid-download
    gate.set()
    bulk._thread.join(5)
    assert bulk.status()["status"] == "stopped" and bulk.wanted()   # the wish survives the exit

    gate.clear()
    ran = threading.Event()
    real_start = bulk.start
    monkeypatch.setattr(bulk, "start", lambda pos_mat, resumed=False: (real_start(pos_mat, resumed), ran.set())[0])
    assert bulk.resume_later(lambda: None, delay=0.01)
    assert ran.wait(5)
    gate.set()
    bulk._thread.join(5)
    st = bulk.status()
    assert st["status"] == "done" and st["resumed"] and st["skipped"] == 1   # the pool pair: no request
    assert fetched == [(30, 31), (30, 31)] and not bulk.wanted()            # finished: nothing to resume
    assert not bulk.resume_later(lambda: None, delay=0.01)

    gate.clear()
    inside.clear()
    have[(30, 31)] = 0
    real_start(None)
    assert inside.wait(5)
    bulk.stop()                              # the user stops it: no resume after a restart
    gate.set()
    bulk._thread.join(5)
    assert not bulk.wanted() and not bulk.resume_later(lambda: None, delay=0.01)
