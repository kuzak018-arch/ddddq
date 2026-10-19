"""Missing hero and item icons are downloaded on first request, once."""

import httpx
import pytest

from drafter.data import constants

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def client(calls, ok=True):
    def handler(req: httpx.Request):
        calls.append(req.url.path)
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"}) if ok else httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def icons(tmp_path, monkeypatch):
    monkeypatch.setattr(constants, "ICONS", tmp_path)
    monkeypatch.setattr(constants, "_icon_failed", set())
    monkeypatch.setattr(constants, "_load", lambda name: {
        "heroes": {"1": {"name": "npc_dota_hero_newhero"}},
        "items": {"new_item": {"img": "/apps/dota2/images/dota_react/items/new_item.png?t=1"}},
    }[name])
    return tmp_path


def test_hero_and_item_icons_are_fetched_once(icons):
    calls = []
    assert constants.fetch_icon("heroes/newhero.png", client(calls))
    assert (icons / "heroes" / "newhero.png").read_bytes() == PNG
    assert constants.fetch_icon("items/new_item.png", client(calls))
    assert calls == ["/apps/dota2/images/dota_react/heroes/newhero.png", "/apps/dota2/images/dota_react/items/new_item.png"]
    assert constants.fetch_icon("heroes/newhero.png", client(calls)) and len(calls) == 2  # cached: no request


def test_unknown_or_odd_paths_are_never_fetched(icons):
    calls = []
    for rel in ("heroes/nobody.png", "items/nothing.png", "abilities/x.png", "heroes/../x.png", "heroes/newhero.jpg"):
        assert not constants.fetch_icon(rel, client(calls))
    assert calls == []


def test_a_failed_download_is_not_retried(icons):
    calls = []
    assert not constants.fetch_icon("heroes/newhero.png", client(calls, ok=False))
    assert not constants.fetch_icon("heroes/newhero.png", client(calls))
    assert len(calls) == 1 and not (icons / "heroes" / "newhero.png").exists()
