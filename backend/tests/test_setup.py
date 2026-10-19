"""First-run setup: the Dota folder picked by hand, Steam accounts of this PC, the Stratz token check."""

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from drafter import dota_paths, settings as S
from drafter.api import app as api

ACC = 1477734386


@pytest.fixture()
def steam(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "PATH", tmp_path / "settings.json")
    root = tmp_path / "steam"
    (root / "config").mkdir(parents=True)
    (root / "config" / "loginusers.vdf").write_text(f'''"users"
{{
    "{ACC + dota_paths.STEAM64_BASE}" {{ "AccountName" "kuz_login" "PersonaName" "Kuzak" "MostRecent" "1" "Timestamp" "1790000000" }}
    "{555 + dota_paths.STEAM64_BASE}" {{ "AccountName" "other" "PersonaName" "Брат" "MostRecent" "0" "Timestamp" "1700000000" }}
}}''', encoding="utf-8")
    (root / "userdata" / str(ACC) / "570").mkdir(parents=True)
    (root / "userdata" / "777").mkdir(parents=True)
    monkeypatch.setattr(dota_paths, "steam_path", lambda: root)
    monkeypatch.setattr(dota_paths, "library_paths", lambda steam: [steam])
    return root


def test_accounts_of_this_pc_last_one_first(steam):
    accs = dota_paths.steam_accounts()
    assert [a["account_id"] for a in accs] == [ACC, 555, 777]
    assert accs[0]["name"] == "Kuzak" and accs[0]["recent"] and accs[0]["dota"]
    assert not accs[1]["dota"] and accs[2]["name"] is None


def test_a_dota_folder_picked_by_hand(steam, tmp_path):
    other = tmp_path / "D" / "SteamLibrary" / "steamapps" / "common" / "dota 2 beta"
    (other / "game" / "dota").mkdir(parents=True)
    (other / "game" / "bin" / "win64").mkdir(parents=True)
    assert dota_paths.dota_path() is None                      # Steam knows no Dota here
    assert dota_paths.find_dota_root(other / "game" / "bin" / "win64") == other
    assert dota_paths.find_dota_root(tmp_path / "D") is None
    S.save(S.Settings(dota_dir=str(other)))
    assert dota_paths.dota_path() == other
    S.save(S.Settings(dota_dir=str(tmp_path / "gone")))       # moved away: back to Steam's
    assert dota_paths.dota_path() is None


def test_setup_api(steam, tmp_path, monkeypatch):
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    other = tmp_path / "dota 2 beta"
    (other / "game" / "dota" / "cfg").mkdir(parents=True)
    with TestClient(api.app) as c:
        assert c.get("/setup/dota").json()["path"] is None
        assert c.put("/setup/dota", json={"path": str(tmp_path / "nothing")}).status_code == 422
        r = c.put("/setup/dota", json={"path": f'"{other / "game" / "dota"}"'}).json()
        assert r["path"] == str(other) and r["manual_ok"]
        assert c.put("/setup/dota", json={"path": None}).json()["manual"] is None
        assert c.get("/setup/accounts").json()["accounts"][0]["account_id"] == ACC


@pytest.mark.parametrize("status,ok", [(200, True), (401, False), (403, False), (429, True), (500, False)])
def test_stratz_token_check(monkeypatch, status, ok):
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    seen = {}

    def post(url, json=None, timeout=None, headers=None):
        seen["auth"] = headers["Authorization"]
        return httpx.Response(status, json={"data": {}})

    monkeypatch.setattr(api.httpx, "post", post)
    with TestClient(api.app) as c:
        r = c.post("/setup/stratz-check", json={"token": " abc.DEF-1 "}).json()
        assert r["ok"] is ok and seen["auth"] == "Bearer abc.DEF-1"
        assert not c.post("/setup/stratz-check", json={"token": "нет токена"}).json()["ok"]
