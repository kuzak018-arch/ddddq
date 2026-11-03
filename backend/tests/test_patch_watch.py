import httpx

from drafter import patch_watch as W


def test_behind_when_valve_has_a_newer_patch(monkeypatch, tmp_path):
    monkeypatch.setattr(W, "PATH", tmp_path / "pw.json")
    monkeypatch.setattr(W.constants, "current_patch", lambda: {"name": "7.41f", "ts": 1000})
    monkeypatch.setattr(W, "_model_patch", lambda: "7.41e")
    feed = {"patches": [{"patch_name": "7.41f", "patch_timestamp": 1000}, {"patch_name": "7.42", "patch_timestamp": 2000}]}
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=feed)))
    assert W.status()["behind"] is False and W.status()["latest"] is None      # never checked: no banner
    W.check(http, now=5)
    st = W.status()
    assert st["latest"] == {"name": "7.42", "ts": 2000} and st["behind"] and st["data_patch"] == "7.41f"
    assert st["model_behind"] and st["checked"] == 5
    # the data refreshed to the new patch: no longer behind
    monkeypatch.setattr(W.constants, "current_patch", lambda: {"name": "7.42", "ts": 2000})
    assert not W.status()["behind"]


def test_a_failed_check_keeps_the_last_answer(monkeypatch, tmp_path):
    monkeypatch.setattr(W, "PATH", tmp_path / "pw.json")
    monkeypatch.setattr(W.constants, "current_patch", lambda: {"name": "7.41f", "ts": 1000})
    monkeypatch.setattr(W, "_model_patch", lambda: None)
    ok = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"patches": [{"patch_name": "7.42", "patch_timestamp": 2000}]})))
    W.check(ok, now=1)
    down = httpx.Client(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))))
    d = W.check(down, now=2)
    assert d["error"] and d["latest"]["name"] == "7.42"
    assert W.status()["behind"] and not W.status()["model_behind"]
