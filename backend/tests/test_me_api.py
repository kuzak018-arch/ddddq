"""GET /me: the profile header gets the rank medal's data (tier, leaderboard place) and Dota Plus."""

from fastapi.testclient import TestClient

from drafter.api import app as api
from drafter.data import me


def test_me_carries_leaderboard_and_plus(monkeypatch):
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    monkeypatch.setenv("DRAFTER_NO_BUILD_LOAD", "1")
    data = {"account_id": 7, "fetched": 1, "matches": [],
            "profile": {"rank_tier": 80, "leaderboard_rank": 57, "profile": {"personaname": "kuz", "plus": True}}}
    monkeypatch.setattr(me, "load", lambda: data)
    monkeypatch.setattr(me, "hero_pool", lambda d=None: {"overall": None, "experience": None, "heroes": {}})
    with TestClient(api.app) as c:
        r = c.get("/me").json()
    assert (r["rank_tier"], r["leaderboard"], r["plus"], r["name"]) == (80, 57, True, "kuz")
    data["profile"] = {"rank_tier": 54, "profile": {}}
    with TestClient(api.app) as c:
        r = c.get("/me").json()
    assert r["leaderboard"] is None and r["plus"] is False
