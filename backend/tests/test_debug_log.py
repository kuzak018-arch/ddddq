"""The UI debug log: appended in the user's logs folder, one line per entry, size kept bounded."""

import pytest
from fastapi.testclient import TestClient

from drafter.api import app as api


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    monkeypatch.setattr(api.config, "ROOT", tmp_path)
    with TestClient(api.app) as c:
        yield c, tmp_path


def test_lines_are_appended_one_per_line(client):
    c, root = client
    assert c.post("/debug/log", json={"lines": ["wheel a", "two\nlines"]}).json()["ok"]
    c.post("/debug/log", json={"lines": ["wheel b"]})
    text = (root / "logs" / "ui-debug.log").read_text(encoding="utf-8")
    assert text.splitlines() == ["wheel a", "two lines", "wheel b"]


def test_the_log_stays_small(client, monkeypatch):
    c, root = client
    monkeypatch.setattr(api, "UI_DEBUG_MAX", 1000)
    for _ in range(30):
        c.post("/debug/log", json={"lines": ["x" * 100]})
    assert (root / "logs" / "ui-debug.log").stat().st_size < 2200
    assert c.post("/debug/log", json={"lines": ["y"] * 501}).status_code == 422
