"""The wizard's crop preview is exactly what the reader cuts out (same rectangles, same frame)."""

import base64

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from drafter.api import app as api
from drafter.vision import calibration, reader


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    monkeypatch.setattr(api, "SNAPSHOTS", tmp_path)
    with TestClient(api.app) as c:
        yield c


def test_crops_match_what_the_reader_cuts(client):
    # a 2560x1440 frame (Windows at 125%: the capture is in real pixels) with a distinct block per slot
    W, H = 2560, 1440
    rng = np.random.default_rng(1)
    frame = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    ok, png = cv2.imencode(".png", frame)
    snap = client.post("/vision/upload", content=png.tobytes()).json()
    assert (snap["width"], snap["height"]) == (W, H)
    cal = calibration.preset_16_9()
    r = client.post("/vision/crops", json={"snapshot": snap["id"], "calibration": cal.model_dump()}).json()
    assert r["width"] == W and r["height"] == H and not r["warnings"]
    want = reader.crops(frame, cal)
    for group in ("radiant", "dire"):
        assert len(r[group]) == 5
        for url, crop in zip(r[group], want[group]):
            got = cv2.imdecode(np.frombuffer(base64.b64decode(url.split(",", 1)[1]), np.uint8), cv2.IMREAD_COLOR)
            scale = min(1.0, 96 / crop.shape[1])
            assert got.shape[1] == max(1, round(crop.shape[1] * scale))
            assert abs(got.shape[0] - round(crop.shape[0] * scale)) <= 1
            # the same picture: compare the shrunk reader crop with what came back
            ref = cv2.resize(crop, (got.shape[1], got.shape[0]), interpolation=cv2.INTER_AREA) if scale < 1 else crop
            assert float(np.abs(ref.astype(int) - got.astype(int)).mean()) < 1.0


def test_crops_warn_on_another_aspect(client):
    frame = np.zeros((1479, 2576, 3), np.uint8)  # a window with a title bar and borders
    ok, png = cv2.imencode(".png", frame)
    snap = client.post("/vision/upload", content=png.tobytes()).json()
    r = client.post("/vision/crops", json={"snapshot": snap["id"], "calibration": calibration.preset_16_9().model_dump()}).json()
    assert r["warnings"] and "Встроенный профиль" in r["warnings"][0]
