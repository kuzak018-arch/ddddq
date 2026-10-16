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


def test_session_shared_between_clients(client):
    empty = [None] * 5
    with client.websocket_connect("/events") as ws:
        assert ws.receive_json()["type"] == "hello"
        r = client.put("/session", json={"allies": [AM, None, None, None, None], "enemies": empty,
                                          "bans": [AXE], "pos": 2, "source": "overlay-1"})
        assert r.status_code == 200 and r.json()["rev"] >= 1
        ev = ws.receive_json()
        assert ev["type"] == "session" and ev["state"]["allies"][0] == AM and ev["state"]["source"] == "overlay-1"
    assert client.get("/session").json()["bans"] == [AXE]
    bad = client.put("/session", json={"allies": [AM, None, None, None, None], "enemies": [AM, None, None, None, None]})
    assert bad.status_code == 422
    assert client.put("/session", json={"allies": [AM], "enemies": empty}).status_code == 422


def test_dota_endpoints(client):
    d = client.get("/dota/display").json()
    assert "found" in d
    assert isinstance(client.get("/dota/keybinds").json()["keys"], list)


def test_setup_writes_env_and_keeps_other_lines(client, tmp_path, monkeypatch):
    from drafter import config
    env = tmp_path / ".env"
    env.write_text("# comment\nOPENDOTA_API_KEY=\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env)
    monkeypatch.delenv("STRATZ_TOKEN", raising=False)
    r = client.put("/setup", json={"account_id": 123456, "stratz_token": "abc.DEF-1"}).json()
    assert r["account_id"] == 123456 and r["has_stratz_token"]
    text = env.read_text(encoding="utf-8")
    assert "# comment" in text and "DOTA_ACCOUNT_ID=123456" in text and "STRATZ_TOKEN=abc.DEF-1" in text
    assert client.put("/setup", json={"stratz_token": "bad token with spaces"}).status_code == 422
    monkeypatch.setenv("DOTA_ACCOUNT_ID", "1477734386")


def test_seed_copy(tmp_path, monkeypatch):
    from drafter import config
    seed, data = tmp_path / "seed", tmp_path / "data"
    (seed / "model").mkdir(parents=True)
    (seed / "model" / "x.txt").write_text("1")
    (data / "constants").mkdir(parents=True)
    monkeypatch.setattr(config, "SEED", seed)
    monkeypatch.setattr(config, "DATA", data)
    assert config.ensure_seed() == ["model"]
    assert (data / "model" / "x.txt").exists() and config.ensure_seed() == []
