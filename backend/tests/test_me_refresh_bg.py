import time

from drafter.data import me


def test_background_refresh_only_when_stale(monkeypatch):
    monkeypatch.delenv("DRAFTER_NO_BUILD_LOAD", raising=False)
    monkeypatch.setattr(me.config, "settings", lambda: type("S", (), {"account_id": 5})())
    calls = []
    monkeypatch.setattr(me, "refresh", lambda: calls.append(1) or {"fetched": 9})
    monkeypatch.setattr(me.threading if hasattr(me, "threading") else __import__("threading"), "Thread",
                        lambda target, **k: type("T", (), {"start": lambda self: target()})())
    monkeypatch.setattr(me, "load", lambda: {"fetched": time.time() - 60})
    assert not me.refresh_in_background()                     # a minute old: kept
    done = []
    monkeypatch.setattr(me, "load", lambda: {"fetched": time.time() - 2 * 3600})
    assert me.refresh_in_background(on_done=done.append) and calls == [1] and done == [{"fetched": 9}]
    assert me.refresh_in_background(max_age=0) and calls == [1, 1]   # after a match: always
    monkeypatch.setattr(me.config, "settings", lambda: type("S", (), {"account_id": None})())
    assert not me.refresh_in_background(max_age=0)            # no account: nothing to fetch
