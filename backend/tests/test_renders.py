"""Hero models on a transparent background: the render's frame is kept only when it is a real
cut-out, a hero without one gets the background removed once, the glow colour."""

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from drafter.data import constants, renders

pytestmark = pytest.mark.skipif(not (constants.DIR / "heroes.json").exists(), reason="нужны константы")

KEY = "bloodseeker"


@pytest.fixture(autouse=True)
def tmp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(renders, "DIR", tmp_path)
    monkeypatch.setattr(renders, "META", tmp_path / "meta.json")
    monkeypatch.setattr(renders, "_failed", set())


def figure(w=600, h=800, color=(30, 30, 200)):
    """A 'model': a red body with a head, and the mask it covers."""
    mask = np.zeros((h, w), np.uint8)
    cv2.ellipse(mask, (w // 2, h // 2 + 60), (w // 5, h // 3), 0, 0, 360, 255, -1)
    cv2.circle(mask, (w // 2, h // 5), w // 9, 255, -1)
    body = np.zeros((h, w, 3), np.uint8)
    body[:] = color
    noise = np.random.default_rng(0).integers(0, 40, (h, w, 3), dtype=np.uint8)
    body = cv2.add(body, noise)
    return body, mask


def png(img):
    return cv2.imencode(".png", img)[1].tobytes()


def test_a_real_cut_out_is_kept_with_its_colour():
    body, mask = figure()
    out = renders.save_still(KEY, png(np.dstack([body, mask])))
    assert out["still"] and out["source"] == "render"
    r, g, b = (int(out["color"][i:i + 2], 16) for i in (1, 3, 5))
    assert r > 150 and r > g + 60 and r > b + 60          # the red of the model, brightened
    saved = cv2.imread(str(renders.DIR / f"{KEY}.png"), cv2.IMREAD_UNCHANGED)
    assert saved.shape[2] == 4 and saved.shape[0] < 800    # empty margins trimmed
    x, y, w, h = out["crop"]                               # and where the kept box was in the frame
    assert out["frame"] == [600, 800] and round(h * 800) == saved.shape[0] and round(w * 600) == saved.shape[1]
    assert 0 < x < 0.5 and 0 < y < 0.2


def test_a_frame_with_a_scene_is_refused():
    body, _ = figure()
    with pytest.raises(renders.RenderError):
        renders.save_still(KEY, png(body))                                     # no alpha at all
    with pytest.raises(renders.RenderError):
        renders.save_still(KEY, png(np.dstack([body, np.full(body.shape[:2], 255, np.uint8)])))  # opaque
    with pytest.raises(renders.RenderError):
        renders.info("not_a_hero")


def test_background_removal_finds_the_model():
    body, mask = figure()
    rng = np.random.default_rng(3)
    scene = cv2.GaussianBlur(rng.integers(60, 140, body.shape, dtype=np.uint8), (0, 0), 9)
    scene[:, :, 0] = np.clip(scene[:, :, 0].astype(int) + 40, 0, 255)   # a bluish rocky scene
    img = np.where(mask[:, :, None] > 0, body, scene)
    out = renders.cut_out(img)
    got = out[:, :, 3] > 127
    truth = mask > 0
    iou = (got & truth).sum() / (got | truth).sum()
    assert iou > 0.9, iou


def test_segment_uses_the_still_with_a_scene(monkeypatch):
    body, mask = figure()
    scene = np.full(body.shape, (120, 90, 60), np.uint8)
    img = np.where(mask[:, :, None] > 0, body, scene)

    class R:
        is_success = True
        headers = {"content-type": "image/png"}
        content = png(img)

    monkeypatch.setattr(renders, "_get", lambda path: R())
    out = renders.segment(KEY)
    assert out["still"] and out["source"] == "segmented" and out["color"]


def test_video_is_downloaded_once_and_a_missing_one_not_asked_again(monkeypatch):
    calls = []

    class R:
        def __init__(self, ok):
            self.is_success = ok
            self.content = b"\x1a\x45\xdf\xa3webm" if ok else b""

    monkeypatch.setattr(renders, "_get", lambda path: calls.append(path) or R(True))
    assert renders.video(KEY).read_bytes().startswith(b"\x1a\x45\xdf\xa3")
    renders.video(KEY)
    assert len(calls) == 1 and calls[0].endswith(f"/renders/{KEY}.webm")
    monkeypatch.setattr(renders, "_get", lambda path: calls.append(path) or R(False))
    assert renders.video("axe") is None and renders.video("axe") is None and len(calls) == 2
    assert renders.info("axe")["video_missing"]


def test_api(monkeypatch):
    from drafter.api import app as api
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    body, mask = figure()
    with TestClient(api.app) as c:
        assert c.get(f"/hero-render/{KEY}").json()["still"] is False
        r = c.post(f"/hero-render/{KEY}/still", content=png(body))
        assert r.status_code == 422 and "прозрачного" in r.json()["detail"]
        assert c.post(f"/hero-render/{KEY}/still", content=png(np.dstack([body, mask]))).json()["source"] == "render"
        assert c.get(f"/hero-render/{KEY}").json()["still"]
        assert c.get("/hero-render/nope").status_code == 422
