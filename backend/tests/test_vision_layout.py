"""Reading the draft without calibration: one layout for every resolution, the fit to a frame,
the window chrome cut off."""

import cv2
import numpy as np
import pytest

from drafter.data import constants
from drafter.vision import calibration, capture, layout, matcher, reader, runner

pytestmark = pytest.mark.skipif(not matcher.has_templates(), reason="нужны иконки героев")

HEROES = [1, 2, 14, 26, 8, 74, 35, 11, 17, 106]


@pytest.fixture(autouse=True)
def no_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(calibration, "PATH", tmp_path / "calibration.json")
    monkeypatch.setattr(layout, "PATH", tmp_path / "layout.json")


def draw(size, heroes_r, heroes_d, scale=1.0, dx=0.0, dy=0.0, seed=0, lay=None):
    """A frame like Dota's: dark textured background, portraits where the layout puts them (moved by
    scale/dx/dy), a bit of blur and JPEG."""
    W, H = size
    rng = np.random.default_rng(seed)
    frame = cv2.GaussianBlur(rng.integers(15, 45, (H, W, 3), dtype=np.uint8), (0, 0), 3)
    keys = {h["id"]: h["key"] for h in constants.hero_index()}
    rects = layout.to_rects(lay or layout.DEFAULT, W, H, scale, dx, dy)
    for g, heroes in (("radiant", heroes_r), ("dire", heroes_d)):
        for r, hid in zip(rects[g], heroes):
            if hid:
                x, y, w, h = calibration.to_pixels(r, W, H)
                frame[y:y + h, x:x + w] = cv2.resize(matcher._read(matcher.template_path(keys[hid])), (w, h),
                                                     interpolation=cv2.INTER_AREA)
    frame = cv2.GaussianBlur(frame, (0, 0), 0.6)
    return cv2.imdecode(cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])[1], cv2.IMREAD_COLOR)


def test_one_layout_for_every_resolution():
    a, b, c = layout.profile(1920, 1080), layout.profile(2560, 1440), layout.profile(3840, 2160)
    assert np.allclose(a.radiant, b.radiant) and np.allclose(b.radiant, c.radiant)   # 16:9: the same fractions
    wide = layout.profile(3440, 1440)
    # 21:9: the same height share, the same pixels from the centre, so a smaller share of the width
    assert wide.dire[0][3] == pytest.approx(b.dire[0][3])
    assert (wide.dire[0][0] - 0.5) * 3440 == pytest.approx((b.dire[0][0] - 0.5) * 2560)
    for cal in (a, layout.profile(1920, 1200), wide):  # Radiant mirrors Dire around the centre
        assert cal.radiant[0][0] == pytest.approx(1 - cal.dire[4][0] - cal.dire[4][2])
    assert calibration.preset_16_9().radiant == a.radiant and a.source == "profile"


def test_saved_rects_carry_over_to_other_resolutions():
    own = layout.to_rects(layout.DEFAULT, 2560, 1440, 1.1, 30, 12)   # the user's own rects at 1440p
    calibration.save(calibration.Calibration(aspect=2560 / 1440, **own, threshold=0.6))
    same = layout.for_frame(1920, 1080)
    assert same.source == "manual" and same.radiant == own["radiant"] and same.threshold == 0.6
    other = layout.for_frame(2560, 1080)                 # 21:9: converted, not used as fractions
    assert other.source == "from-manual"
    back = layout.from_calibration(other)
    mine = layout.from_calibration(calibration.Calibration(aspect=16 / 9, **own))
    assert np.allclose(np.array(back["dire"]), np.array(mine["dire"]), atol=1e-6)


@pytest.mark.parametrize("size,scale,dx,dy", [((2560, 1440), 1.0, 0, 0), ((2560, 1440), 1.06, 25, 9),
                                              ((1920, 1200), 0.95, -18, 4), ((3440, 1440), 1.04, 12, 0)])
def test_detect_fits_scale_and_offset(size, scale, dx, dy):
    W, H = size
    frame = draw(size, HEROES[:4] + [None], [None] + HEROES[5:9], scale, dx, dy)
    fit, info = layout.detect(frame)
    assert fit, info
    slot = layout.DEFAULT["dire"][0][2] * H / layout.REF_H
    assert fit["scale"] == pytest.approx(scale, rel=0.015)
    assert abs(fit["dx"] - dx) < 0.1 * slot and abs(fit["dy"] - dy) < 0.1 * slot
    layout.save_fit(W, H, fit)
    cal = layout.for_frame(W, H)
    assert cal.source == "detected"
    res = reader.read(frame)
    assert [r.hero for r in res["radiant"]] == HEROES[:4] + [None]
    assert [r.hero for r in res["dire"]] == [None] + HEROES[5:9]


def test_detect_refuses_frames_without_portraits():
    fit, info = layout.detect(draw((1920, 1080), [HEROES[0]] + [None] * 4, [None] * 5))
    assert fit is None and "портрет" in info["reason"]
    rng = np.random.default_rng(1)
    noise = cv2.GaussianBlur(rng.integers(0, 255, (1080, 1920, 3), dtype=np.uint8), (0, 0), 2)
    fit, info = layout.detect(noise)
    assert fit is None


def test_runner_fits_on_live_frames_by_itself():
    frame = draw((2560, 1440), HEROES[:5], HEROES[5:], 1.05, 20, 6)
    state = {"allies": [None] * 5, "enemies": [None] * 5, "bans": [], "side": "radiant", "phase": "draft"}
    r = runner.Runner(lambda: state, lambda **c: state.update(c), lambda d: None)
    r.step(frame, dict(state))
    assert r.autofit.last_info["saved"] and layout.for_frame(2560, 1440).source == "detected"
    assert r.last_result["source"] == "detected"
    r.step(frame, dict(state))
    assert state["allies"] == HEROES[:5] and state["enemies"] == HEROES[5:]


def test_client_area_is_cut_out_of_a_windowed_frame():
    # 1936x1119 window (8 px borders, 31 px title) holding a 1920x1080 client area
    assert capture.client_crop((100, 50, 2036, 1169), (108, 81, 2028, 1161), 1936, 1119) == (8, 31, 1920, 1080)
    # borderless / fullscreen: nothing to cut
    assert capture.client_crop((0, 0, 2560, 1440), (0, 0, 2560, 1440), 2560, 1440) is None
    # the frame is scaled (the capture at 125% of a DPI-unaware size): the box scales too
    assert capture.client_crop((0, 0, 1000, 600), (10, 40, 990, 590), 1250, 750) == (12, 50, 1225, 688)
    # nonsense rects (minimised window) keep the whole frame
    assert capture.client_crop((0, 0, 100, 100), (0, 0, 10, 10), 100, 100) is None


def test_wizard_api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from drafter.api import app as api
    monkeypatch.delenv("DRAFTER_TOKEN", raising=False)
    monkeypatch.setattr(api, "SNAPSHOTS", tmp_path / "snaps")
    with TestClient(api.app) as client:
        frame = draw((2560, 1080), HEROES[:5], HEROES[5:], 1.03, -10, 5)
        snap = client.post("/vision/upload", content=cv2.imencode(".png", frame)[1].tobytes()).json()
        assert client.get("/vision/calibration", params={"width": 2560, "height": 1080}).json()["source"] == "profile"
        r = client.post("/vision/detect", json={"snapshot": snap["id"], "save": True}).json()
        assert r["saved"] and r["info"]["portraits"] == 10
        assert client.get("/vision/calibration", params={"width": 2560, "height": 1080}).json()["source"] == "detected"
        lay = client.get("/vision/layout").json()
        assert lay["base"] == "default" and lay["fits"][0]["size"] == "2560x1080"
        assert {p["aspect"] for p in lay["profiles"]} == {"16:9", "16:10", "21:9"}
        read = client.post("/vision/read", json={"snapshot": snap["id"]}).json()
        assert [s["hero"] for s in read["radiant"]] == HEROES[:5] and read["source"] == "detected"
        # by hand: wins for this aspect, and becomes the layout for the others
        manual = client.put("/vision/calibration", json={**r["calibration"], "auto": True, "source": "detected"}).json()
        assert manual["source"] == "manual" and not manual["auto"]
        assert client.get("/vision/calibration", params={"width": 1920, "height": 1080}).json()["source"] == "from-manual"
        assert client.get("/vision/status").json()["layout_base"] == "manual"
        assert client.delete("/vision/calibration").json()["removed"]
        assert client.get("/vision/calibration", params={"width": 2560, "height": 1080}).json()["source"] == "profile"
