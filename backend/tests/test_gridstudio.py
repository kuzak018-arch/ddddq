"""GridStudio's workshop: lists without 18+, authors, the cache (and its use when the site is down),
files kept for good, ids checked before anything is asked."""

import json

import pytest

from drafter.data import gridstudio as G

WORK = "0f8a4c2e-1111-4a2b-9c3d-123456789abc"


class Resp:
    def __init__(self, data=None, content=b""):
        self._data, self.content = data, content

    def json(self):
        return self._data


@pytest.fixture()
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "DIR", tmp_path)
    calls = []
    answers = {
        "/works": {"total": 3, "page": 0, "items": [
            {"id": WORK, "revision": 7, "title": "Рамка", "author": "", "creator": {"name": "linsis"}, "tags": ["Рамки"], "likes": 40, "downloads": 900},
            {"id": "x" * 36, "title": "nsfw", "author": "a", "tags": ["18+"]},
            {"id": "0f8a4c2e-2222-4a2b-9c3d-123456789abc", "title": "", "author": "guest", "tags": []}]},
        f"/works/{WORK}/download": {"version": 3, "configs": [{"config_name": "Рамка", "categories": []}]},
        "/backgrounds": {"total": 1, "aspects": {"16:9": 1}, "items": [
            {"id": 12, "title": "Космос", "author": "", "creator": {"name": "x"}, "tags": ["Космос"], "aspect": "16:9", "seconds": 8, "preview": "abc"},
            {"id": 13, "title": "no", "author": "y", "tags": ["18+"]}]},
        "/backgrounds/12/video.webm": b"\x1a\x45\xdf\xa3video",
        "/arts": {"items": [{"id": 1, "name": "Сердце", "category": "Милота", "author": "z", "text": "<3"},
                            {"id": 2, "name": "no", "category": "18+", "text": "x"}]},
    }

    def get(path, params=None):
        calls.append((path, params))
        a = answers[path]
        if isinstance(a, Exception):
            raise a
        return Resp(content=a) if isinstance(a, bytes) else Resp(a)

    monkeypatch.setattr(G, "_get", get)
    return calls, answers


def test_grids_without_adult_works_and_with_authors(site):
    calls, _ = site
    out = G.grids(sort="week")
    assert [g["title"] for g in out["items"]] == ["Рамка", "Без названия"]
    assert out["items"][0]["author"] == "linsis" and out["items"][1]["author"] == "guest"
    assert out["items"][0]["url"].endswith(WORK)
    assert calls[0][1] == {"sort": "week", "page": 0}
    G.grids(sort="week")
    assert len(calls) == 1                                   # cached for a while
    with pytest.raises(G.WorkshopError):
        G.grids(tag="18+")


def test_the_last_list_is_shown_when_the_site_is_down(site, monkeypatch):
    calls, answers = site
    G.grids()
    for p in G.DIR.glob("lists/*.json"):                      # the cache got old
        import os
        os.utime(p, (0, 0))
    answers["/works"] = G.WorkshopError("GridStudio не ответил")
    out = G.grids()
    assert out["stale"] and out["items"]


def test_a_grid_is_a_dota_grid_file(site):
    data = G.grid_file(WORK)
    assert data["version"] == 3 and data["configs"][0]["config_name"] == "Рамка"
    with pytest.raises(G.WorkshopError):
        G.grid_file("../../etc/passwd")


def test_backgrounds_and_their_files(site):
    calls, _ = site
    out = G.backgrounds(aspect="16:9")
    assert [b["id"] for b in out["items"]] == [12] and out["items"][0]["has_preview"]
    path, kind = G.background_file("12", "video.webm")
    assert kind == "video/webm" and path.read_bytes().startswith(b"\x1a\x45\xdf\xa3")
    n = len(calls)
    G.background_file("12", "video.webm")
    assert len(calls) == n                                   # files are kept for good
    for bad in (("12", "../x"), ("0", "video.webm"), ("abc", "poster.jpg")):
        with pytest.raises(G.WorkshopError):
            G.background_file(*bad)
    with pytest.raises(G.WorkshopError):
        G.backgrounds(aspect="1:1")


def test_arts_library(site):
    out = G.arts()
    assert [a["name"] for a in out["items"]] == ["Сердце"]


def test_api_maps_errors(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from drafter.api import app as api
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    monkeypatch.delenv("DRAFTER_NO_BUILD_LOAD", raising=False)
    monkeypatch.setattr(G, "DIR", tmp_path)

    def down(path, params=None):
        raise G.WorkshopError("GridStudio не ответил: timeout")

    monkeypatch.setattr(G, "_get", down)
    with TestClient(api.app) as c:
        r = c.get("/workshop/grids")
        assert r.status_code == 502 and "не ответил" in r.json()["detail"]
        assert c.get("/workshop/meta").json()["aspects"]
        assert c.get("/workshop-media/bg/12/video.webm").status_code == 502


def test_cache_is_kept_under_its_limit_newest_first(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(G, "DIR", tmp_path)
    for i in range(5):
        f = tmp_path / "backgrounds" / f"f{i}"
        f.parent.mkdir(exist_ok=True)
        f.write_bytes(b"x" * 100)
        os.utime(f, (1000 + i, 1000 + i))
    G._prune(limit=250)
    assert sorted(p.name for p in (tmp_path / "backgrounds").iterdir()) == ["f3", "f4"]
