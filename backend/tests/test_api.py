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
    b = body["build"]
    assert (b["builds"] or b["approximate"]) and body["vs"]
    base = b["builds"][0] if b["builds"] else b["approximate"]
    assert base["core"] and base["boots"]
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
    # an update brings new files: merged into stratz, existing ones untouched; model stays whole
    (seed / "stratz" / "match_players").mkdir(parents=True)
    (seed / "stratz" / "match_players" / "1.jsonl").write_text("new")
    (seed / "stratz" / "match_players" / "4.jsonl").write_text("new")
    (seed / "model" / "y.txt").write_text("2")
    (data / "stratz" / "match_players").mkdir(parents=True)
    (data / "stratz" / "match_players" / "1.jsonl").write_text("mine")
    assert config.ensure_seed() == ["stratz"]
    assert (data / "stratz" / "match_players" / "1.jsonl").read_text() == "mine"
    assert (data / "stratz" / "match_players" / "4.jsonl").read_text() == "new"
    assert not (data / "model" / "y.txt").exists() and config.ensure_seed() == []


def test_lane(client):
    r = client.get("/lane", params={"hero": AM, "pos": 1, "enemy": AXE})
    assert r.status_code == 200
    b = r.json()
    assert b["enemy_pos"] in (3, 4) and b["status"] == "ready" and "games" in b["analysis"] and not b["off_lane"]
    assert client.get("/lane", params={"hero": AM, "pos": 1, "enemy": AM}).status_code == 422
    assert client.get("/lane", params={"hero": AM, "pos": 9, "enemy": AXE}).status_code == 422
    # Axe with "carry" selected: Axe is an offlaner, so the lane is the offlane, facing the carry AM
    b = client.get("/lane", params={"hero": AXE, "pos": 1, "enemy": AM}).json()
    assert b["pos"] == 3 and b["requested_pos"] == 1 and b["enemy_pos"] == 1
    # a mid hero never stands on the safe lane against a carry
    assert client.get("/lane", params={"hero": AM, "pos": 1, "enemy": 17}).json()["off_lane"]
    opp = client.post("/lane/opponents", json={"pos": 1, "enemies": [LION, AXE, PUDGE]}).json()
    assert opp["pos"] == 1 and opp["opponents"][0]["hero"] == AXE and opp["opponents"][0]["main"]
    assert {o["hero"] for o in opp["opponents"]} == {LION, AXE, PUDGE}
    opp = client.post("/lane/opponents", json={"pos": 1, "hero": AXE, "enemies": [AM, 17]}).json()
    assert opp["pos"] == 3 and opp["requested_pos"] == 1
    first = opp["opponents"][0]
    assert first["hero"] == AM and first["on_lane"] and first["pos"] == 1
    storm = next(o for o in opp["opponents"] if o["hero"] == 17)
    assert not storm["on_lane"] and storm["lane_pos"] is None


def test_settings_put_changes_only_sent_fields(client, tmp_path, monkeypatch):
    from drafter import settings as user_settings
    monkeypatch.setattr(user_settings, "PATH", tmp_path / "settings.json")
    client.put("/settings", json={"vision_collect": False, "vision_collect_mb": 800})
    s = client.put("/settings", json={"pos": 2}).json()     # an older client that knows only pos
    assert s["pos"] == 2 and s["vision_collect"] is False and s["vision_collect_mb"] == 800


# ---------- hero grids ---------------------------------------------------------------------------

@pytest.fixture()
def grid_env(tmp_path, monkeypatch):
    """The user's cfg folder in tmp, Dota closed, the file in the game's own layout."""
    from drafter import hero_grid as hg
    cfg_dir = tmp_path / "steam" / "userdata" / "42" / "570" / "remote" / "cfg"
    cfg_dir.mkdir(parents=True)
    path = cfg_dir / hg.FILE_NAME
    original = '{\n\t"version": 3,\n\t"configs":\n\t[\n\t]\n}'
    path.write_text(original, encoding="utf-8", newline="")
    monkeypatch.setattr(hg.dota_paths, "steam_path", lambda: tmp_path / "steam")
    monkeypatch.setattr(hg, "backup_dir", lambda: tmp_path / "backups")
    state = {"running": False}
    monkeypatch.setattr(hg, "dota_running", lambda: state["running"])
    monkeypatch.setattr(api.config, "settings", lambda: type("S", (), {"account_id": 42, "stratz_token": None, "opendota_key": None})())
    return path, state, original


def test_hero_grids_preview_state_and_write(client, grid_env):
    path, state, original = grid_env
    prev = client.get("/hero-grids").json()
    assert [g["id"] for g in prev["grids"]] == ["roles", "meta", "pool", "counters"]
    roles = prev["grids"][0]
    assert roles["config_name"] == "Драфтер · Роли" and len(roles["categories"]) == 5 and roles["heroes"] > 50
    st = client.get("/hero-grids/state").json()
    assert st["found"] and st["exists"] and st["dota_running"] is False and st["ours"] == [] and st["backups"] == []

    state["running"] = True  # Dota open: no write, nothing changes
    r = client.post("/hero-grids/write", json={"grids": ["roles", "meta"]})
    assert r.status_code == 409 and "Дота запущена" in r.json()["detail"]
    assert client.get("/hero-grids/state").json()["dota_running"] is True and path.read_text(encoding="utf-8") == original

    state["running"] = False
    done = client.post("/hero-grids/write", json={"grids": ["roles", "meta"]}).json()
    assert done["written"] == ["Драфтер · Роли", "Драфтер · Мета"] and done["backup"]
    st = client.get("/hero-grids/state").json()
    assert st["ours"] == ["Драфтер · Роли", "Драфтер · Мета"] and len(st["backups"]) == 1

    back = client.post("/hero-grids/restore", json={"name": done["backup"]}).json()
    assert back["restored"] == done["backup"] and path.read_text(encoding="utf-8") == original
    client.post("/hero-grids/write", json={"grids": ["meta"]})
    assert client.post("/hero-grids/remove").json()["removed"] == ["Драфтер · Мета"]
    assert path.read_text(encoding="utf-8") == original


def test_hero_grids_validation_and_errors(client, grid_env):
    path, _, _ = grid_env
    assert client.post("/hero-grids/write", json={"grids": []}).status_code == 422
    assert client.post("/hero-grids/write", json={"grids": ["nonsense"]}).status_code == 422
    assert client.post("/hero-grids/restore", json={"name": "../x"}).status_code == 422
    path.write_text('{"version": 9, "configs": []}', encoding="utf-8")
    r = client.post("/hero-grids/write", json={"grids": ["meta"]})
    assert r.status_code == 422 and "формат" in r.json()["detail"]
    assert client.get("/hero-grids/state").json()["error"]
