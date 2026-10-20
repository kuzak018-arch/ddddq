"""Hero art refresh: changed art is re-downloaded (If-Modified-Since), unchanged is left, once a week."""

import time

import httpx

from drafter.data import constants


class Http:
    def __init__(self, responses):
        self.responses, self.calls = responses, []

    def get(self, url, headers=None):
        self.calls.append((url, dict(headers or {})))
        status, body = self.responses.get(url.rsplit("/", 1)[-1], (404, b""))
        return httpx.Response(status, content=body, headers={"content-type": "image/png"} if status == 200 else {})


def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(constants, "ICONS", tmp_path / "icons")
    monkeypatch.setattr(constants, "_load", lambda name: {"1": {"name": "npc_dota_hero_tinker"}, "2": {"name": "npc_dota_hero_axe"}})
    (tmp_path / "icons" / "heroes").mkdir(parents=True)
    (tmp_path / "icons" / "heroes" / "tinker.png").write_bytes(b"old tinker")
    (tmp_path / "icons" / "heroes" / "axe.png").write_bytes(b"axe")


def test_changed_art_is_replaced_and_unchanged_is_asked_conditionally(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    http = Http({"tinker.png": (200, b"NEW tinker"), "axe.png": (304, b"")})
    assert constants.refresh_hero_art(http) == 1
    assert (tmp_path / "icons" / "heroes" / "tinker.png").read_bytes() == b"NEW tinker"
    assert (tmp_path / "icons" / "heroes" / "axe.png").read_bytes() == b"axe"
    assert all("If-Modified-Since" in h for _, h in http.calls)


def test_a_new_hero_without_art_is_downloaded(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    (tmp_path / "icons" / "heroes" / "axe.png").unlink()
    http = Http({"tinker.png": (304, b""), "axe.png": (200, b"fresh axe")})
    assert constants.refresh_hero_art(http) == 1 and (tmp_path / "icons" / "heroes" / "axe.png").read_bytes() == b"fresh axe"
    assert "If-Modified-Since" not in http.calls[1][1]


def test_once_a_week_and_never_raises_offline(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    http = Http({"tinker.png": (304, b""), "axe.png": (304, b"")})
    constants.refresh_hero_art(http)
    assert len(http.calls) == 2
    constants.refresh_hero_art(http)
    assert len(http.calls) == 2                               # checked just now: nothing asked
    stamp = tmp_path / "icons" / "heroes_checked"
    old = time.time() - 8 * 24 * 3600
    import os
    os.utime(stamp, (old, old))
    constants.refresh_hero_art(http)
    assert len(http.calls) == 4                               # a week later: asked again

    class Offline:
        def get(self, url, headers=None):
            raise httpx.ConnectError("no network")
    os.utime(stamp, (old, old))
    assert constants.refresh_hero_art(Offline()) == 0         # no exception
