"""Files cut off by a crash mid-write must not break the app: /health answers, readers start over."""

import polars as pl
from fastapi.testclient import TestClient

from drafter.api import app as api
from drafter.data import matches
from drafter.data import stratz_matches as sm


def test_broken_match_state_keeps_health_up(tmp_path, monkeypatch):
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    monkeypatch.setattr(matches, "DIR", tmp_path)
    monkeypatch.setattr(matches, "PAGES", tmp_path / "pages")
    monkeypatch.setattr(matches, "STATE", tmp_path / "state.json")
    matches.PAGES.mkdir()
    pl.DataFrame({"match_id": [1], "start_time": [1], "duration": [2000]}).write_parquet(matches.PAGES / "1_1.parquet")
    matches.STATE.write_text("")
    assert matches._state() == {}
    assert TestClient(api.app).get("/health").status_code == 200
    matches._save_state({"since_ts": 5})
    assert matches._state() == {"since_ts": 5} and not list(tmp_path.glob("*.tmp"))


def test_broken_specialists_file_is_fetched_again(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "SPECIALISTS", tmp_path)
    (tmp_path / "1.json").write_text('{"fetched": 1', encoding="utf-8")

    class Fake:
        def __init__(self, **kw):
            pass

        def close(self):
            pass

        def q(self, query):
            return {"leaderboard": {"hero": []}}

    monkeypatch.setattr(sm.stratz, "Stratz", Fake)
    assert sm._specialists(1)["players"] == []
    assert sm._specialists(1)["fetched"] > 1   # rewritten whole
