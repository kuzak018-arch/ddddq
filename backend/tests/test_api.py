import pytest
from fastapi.testclient import TestClient

from drafter.api import app as api
from drafter.model import train

pytestmark = pytest.mark.skipif(not (train.ART / "models.joblib").exists(), reason="нужна обученная модель")

AM, AXE, LION, PUDGE, BS = 1, 2, 26, 14, 4


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    with TestClient(api.app) as c:
        yield c


def test_health_and_heroes(client):
    h = client.get("/health").json()
    assert h["ok"] and h["patch"]
    heroes = client.get("/heroes").json()["heroes"]
    assert len(heroes) == 127
    am = next(x for x in heroes if x["id"] == AM)
    assert am["main_pos"] == 1 and abs(sum(am["positions"]) - 1) < 0.01


def test_search_slang(client):
    assert client.get("/heroes/search", params={"q": "згвпу"}).json()["ids"][0] == PUDGE


def test_evaluate_and_suggest(client):
    d = {"allies": [LION, PUDGE], "enemies": [AM, AXE], "pos": 1}
    ev = client.post("/draft/evaluate", json=d).json()
    assert 0.3 < ev["p_win"] < 0.7 and ev["terms"]
    s = client.post("/draft/suggest", json=d).json()
    main = s["main"]
    assert len(main) == 10 and all(r["pos_share"] >= 0.4 for r in main)
    assert all(r["hero"] not in d["allies"] + d["enemies"] for r in main + s["offrole"])
    assert all(r["pos_share"] < 0.4 for r in s["offrole"])
    no_comfort = client.post("/draft/suggest", json={**d, "use_comfort": False}).json()
    assert not any(t["kind"] == "comfort" for r in no_comfort["main"] for t in r["terms"])


def test_empty_draft_works(client):
    r = client.post("/draft/suggest", json={"pos": 5})
    assert r.status_code == 200 and len(r.json()["main"]) == 10
    assert client.post("/draft/bans", json={"pos": 1}).json()["bans"]


@pytest.mark.parametrize("body", [
    {"allies": [AM], "enemies": [AM]},           # same hero twice
    {"allies": [9999]},                           # unknown hero
    {"allies": [1, 2, 3, 4, 5, 6]},               # too many
    {"pos": 6},
])
def test_bad_drafts_rejected(client, body):
    assert client.post("/draft/evaluate", json=body).status_code == 422


def test_hero_page_and_tierlist(client):
    p = client.get(f"/heroes/{BS}").json()
    assert p["matchups"]["counters"] and p["matchups"]["countered_by"]
    assert client.get("/heroes/9999").status_code == 404
    t = client.get("/meta/tierlist", params={"pos": 1}).json()
    assert t["heroes"] and {r["tier"] for r in t["heroes"]} <= set("SABCD")
    assert all(r["pos_share"] >= 0.4 for r in t["heroes"])
    assert client.get("/meta/tierlist", params={"tiers": "0,9"}).status_code == 422


def test_build_vs(client):
    r = client.post(f"/builds/{BS}/vs", json={"enemies": [12, 32, 22, 36, 26], "pos": 1})
    if r.status_code == 404:
        pytest.skip("нет данных Stratz")
    body = r.json()
    assert body["build"]["core"] and body["vs"]
    assert client.get(f"/builds/{BS}", params={"pos": 9}).status_code == 422


def test_settings_roundtrip(client, tmp_path, monkeypatch):
    from drafter import settings
    monkeypatch.setattr(settings, "PATH", tmp_path / "s.json")
    s = client.get("/settings").json()
    s["pos"] = 3
    assert client.put("/settings", json=s).json()["pos"] == 3
    assert client.get("/settings").json()["pos"] == 3
    assert client.put("/settings", json={**s, "pos": 7}).status_code == 422


def test_token_required_when_set(monkeypatch):
    monkeypatch.setenv("DRAFTER_TOKEN", "secret")
    with TestClient(api.app) as c:
        assert c.get("/health").status_code == 200                       # open
        assert c.get("/settings").status_code == 401
        assert c.get("/settings", headers={"X-Drafter-Token": "secret"}).status_code == 200
        with pytest.raises(Exception):
            with c.websocket_connect("/events?token=wrong") as ws:
                ws.receive_json()
        with c.websocket_connect("/events?token=secret") as ws:
            assert ws.receive_json()["type"] == "hello"
