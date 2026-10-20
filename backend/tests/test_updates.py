"""Updates: the newest release of the public releases repository, checked by SHA-256."""

import hashlib
from contextlib import contextmanager

import httpx
import pytest

from drafter import updates

EXE = b"MZ fake installer " * 1000
SHA = hashlib.sha256(EXE).hexdigest()
NAME = "Dota.Drafter_1.2.0_x64-setup.exe"


def release(tag="v1.2.0", sha=True):
    assets = [{"name": NAME, "browser_download_url": "https://x/exe", "size": len(EXE)}]
    if sha:
        assets.append({"name": NAME + ".sha256", "browser_download_url": "https://x/sha"})
    return {"tag_name": tag, "body": "Что нового", "html_url": "https://github.com/r/releases/v1.2.0",
            "published_at": "2026-10-20T10:00:00Z", "assets": assets}


def listing(*rels):
    """GitHub's list of releases, newest first; a service release without a version among them."""
    return [*rels, {"tag_name": "seed-data", "assets": [{"name": "seed-data.zip", "browser_download_url": "https://x/seed"}]}]


@pytest.fixture
def net(monkeypatch, tmp_path):
    state = {"release": listing(release()), "status": 200, "sha": f"{SHA}  {NAME}\n", "body": EXE}
    monkeypatch.setattr(updates, "DIR", tmp_path / "updates")

    def get(url, **kw):
        if url.endswith("/sha"):
            return httpx.Response(200, text=state["sha"], request=httpx.Request("GET", url))
        return httpx.Response(state["status"], json=state["release"], request=httpx.Request("GET", url))

    @contextmanager
    def stream(method, url, **kw):
        yield httpx.Response(200, content=state["body"], request=httpx.Request(method, url))

    monkeypatch.setattr(updates, "_get", get)
    monkeypatch.setattr(updates.httpx, "stream", stream)
    return state


def test_versions():
    assert updates.parse_version("v1.10.0") > updates.parse_version("1.9.9")
    assert updates.parse_version("1.2") is None


def test_check_newer_and_same(net):
    c = updates.check("1.1.0")
    assert c["newer"] and c["latest"] == "1.2.0" and c["notes"] == "Что нового" and c["ready"] is None
    assert not updates.check("1.2.0")["newer"]
    assert not updates.check("2.0.0")["newer"]


def test_no_release_yet(net):
    net["status"] = 404
    with pytest.raises(updates.UpdateError, match="ещё нет"):
        updates.check("1.1.0")


def test_download_checks_sha_and_keeps_one(net):
    (updates.DIR).mkdir(parents=True)
    (updates.DIR / "Dota.Drafter_1.1.5_x64-setup.exe").write_bytes(b"old")
    lines = []
    got = updates.download(lines.append)
    assert got["version"] == "1.2.0" and open(got["path"], "rb").read() == EXE
    assert [f.name for f in updates.DIR.iterdir()] == [NAME]
    assert lines[-1].startswith("Готово") and "100%" in lines
    assert updates.check("1.1.0")["ready"]["path"] == got["path"]
    # a second run doesn't download again
    assert updates.download(lines.append) == got


def test_download_bad_sha_removed(net):
    net["body"] = EXE + b"tampered"
    with pytest.raises(updates.UpdateError, match="не совпала"):
        updates.download(lambda _: None)
    assert updates.ready() is None and not list(updates.DIR.iterdir())


def test_no_sha_no_download(net):
    net["release"] = listing(release(sha=False))
    with pytest.raises(updates.UpdateError, match="контрольной сумм"):
        updates.download(lambda _: None)


def test_the_highest_version_wins_whatever_the_order_and_service_releases_are_skipped(net):
    old = release("v1.0.2", sha=False)                                      # an old release without a checksum
    newer = release("v1.10.0")
    newer["assets"][0]["browser_download_url"] = "https://x/exe110"
    net["release"] = [{"tag_name": "seed-data", "assets": []}, release("v1.9.0"), newer, old, {**release("v2.0.0"), "prerelease": True}]
    c = updates.check("1.9.0")
    assert c["latest"] == "1.10.0" and c["newer"]                           # 1.10 > 1.9 as numbers, the pre-release is ignored
    assert updates.latest()["exe"]["url"] == "https://x/exe110"


def test_default_source_is_this_repository():
    assert updates.RELEASES_REPO == "kuzak018-arch/ddddq" or "DRAFTER_RELEASES_REPO" in __import__("os").environ
