"""Frames collected during drafts: saving on change, labels from the board, freezing, and the
after-draft pipeline (auto calibration, templates, accuracy, switching the feature on)."""

import types

import cv2
import numpy as np
import pytest

from drafter.data import constants
from drafter.vision import auto, autocal, calibration, collector, evaluate, matcher

pytestmark = pytest.mark.skipif(not (constants.DIR / "items.json").exists() or not matcher.ICONS.exists(),
                                reason="нужны константы и иконки героев")

W, H = 1920, 1080
X0, STEP, SW, SH, Y = 0.262, 0.0365, 0.031, 0.040, 0.009     # deliberately not the preset
RAD = [[X0 + k * STEP, Y, SW, SH] for k in range(5)]
DIRE = [[1 - r[0] - r[2], Y, SW, SH] for r in reversed(RAD)]


def heroes_with_icons(n, seed):
    hs = [h["id"] for h in constants.hero_index() if (matcher.ICONS / f"{h['key']}.png").exists()]
    return [int(h) for h in np.random.default_rng(seed).choice(hs, n, replace=False)]


def frame_with(radiant, dire, rng):
    """Synthetic draft screen: portraits cropped into the slots (as the game does), noise around."""
    img = np.full((H, W, 3), 25, np.uint8)
    img = cv2.GaussianBlur(img + rng.integers(0, 25, img.shape, dtype=np.uint8), (0, 0), 5)
    for heroes, rects in ((radiant, RAD), (dire, DIRE)):
        for h, r in zip(heroes, rects):
            if not h:
                continue
            x, y, w, hh = calibration.to_pixels(r, W, H)
            key = constants.hero_by_id()[h]["key"]
            art = evaluate._distort(matcher._read(matcher.ICONS / f"{key}.png"), rng, False)
            art = matcher._center_crop(art, w / hh)
            img[y:y + hh, x:x + w] = cv2.resize(art, (w, hh), interpolation=cv2.INTER_AREA)
    return img


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "SNAPSHOTS", tmp_path / "snapshots")
    monkeypatch.setattr(collector, "DRAFTS", tmp_path / "collected")
    monkeypatch.setattr(collector, "INTERVAL", 0.0)
    monkeypatch.setattr(matcher, "LEARNED", tmp_path / "learned")
    monkeypatch.setattr(calibration, "PATH", tmp_path / "calibration.json")
    monkeypatch.setattr(auto, "STATE", tmp_path / "auto.json")
    monkeypatch.setattr(evaluate, "LABELED", tmp_path / "labeled")
    matcher._bank.cache_clear()
    yield tmp_path
    matcher._bank.cache_clear()


def run_draft(col, sess, state, radiant, dire, rng):
    """Bans, half the picks, all picks + strategy time, then the match and the end."""
    sess.update(phase="draft", side="radiant", allies=[None] * 5, enemies=[None] * 5, rev=sess["rev"] + 1)
    steps = [([None] * 5, [None] * 5, "DOTA_GAMERULES_STATE_HERO_SELECTION"),
             (radiant[:2] + [None] * 3, dire[:3] + [None] * 2, "DOTA_GAMERULES_STATE_HERO_SELECTION"),
             (radiant, dire, "DOTA_GAMERULES_STATE_HERO_SELECTION"),
             (radiant, dire, "DOTA_GAMERULES_STATE_STRATEGY_TIME")]
    for r, d, st in steps:
        state["gs"] = st
        col.tick(frame=frame_with(r, d, rng))
    # the user fills the board (in another order than the screen) while the match runs
    sess.update(phase="game", allies=list(reversed(radiant)), enemies=list(dire), rev=sess["rev"] + 1)
    col.tick()
    sess.update(phase="idle", rev=sess["rev"] + 1)
    col.tick()


def test_collect_label_freeze_and_switch_on(sandbox, monkeypatch):
    monkeypatch.setattr(auto, "AUTO_MIN_FRAMES", 4)
    monkeypatch.setattr(auto, "AUTO_MIN_FILLED", 10)
    rng = np.random.default_rng(3)
    sess = {"phase": "idle", "side": None, "allies": [None] * 5, "enemies": [None] * 5, "bans": [], "rev": 0}
    state = {"gs": None}
    enabled = {"on": False}
    finals = []

    def finalize(d):
        finals.append(auto.finalize(d, lambda on: enabled.update(on=on), lambda: enabled["on"]))

    settings = types.SimpleNamespace(vision_collect=True, vision_collect_mb=500)
    col = collector.Collector(lambda: sess, lambda: state["gs"], lambda: settings, on_finalize=finalize)

    hs = heroes_with_icons(20, 7)
    run_draft(col, sess, state, hs[:5], hs[5:10], rng)
    d1 = collector.drafts()[0]
    assert d1["frozen"] and len(d1["frames"]) == 4 and d1["frames"][-1]["complete"]
    assert sorted(d1["labels"]["radiant"]) == sorted(hs[:5]) and sorted(d1["labels"]["dire"]) == sorted(hs[5:10])
    first = finals[0]
    assert first["calibration"]["done"] and calibration.load().auto        # rects found on the frame
    assert first["learned"] >= 8                                             # templates from the screen
    assert not enabled["on"]                                                 # one draft is not enough

    # the board is cleared for the next game: the frozen labels must stay
    sess.update(allies=[None] * 5, enemies=[None] * 5, rev=sess["rev"] + 1)
    col.tick()
    assert collector.load_draft(d1["id"])["labels"]["radiant"]

    import time
    time.sleep(1.1)   # draft ids are per second
    run_draft(col, sess, state, hs[10:15], hs[15:20], rng)
    ev = finals[-1]["evaluation"]
    assert ev["drafts"] == 2 and ev["precision"] >= 0.98
    assert enabled["on"] and finals[-1]["switched"] == "on"

    # a frame of a known draft gives the same rects through the API helper
    f = auto.complete_frame(collector.drafts()[0])
    cal, info = autocal.locate(matcher._read(collector.frame_path(f["id"])), hs[10:15], hs[15:20])
    assert cal and info["fitted"] >= 8


def test_disk_limit_drops_oldest_drafts(sandbox):
    rng = np.random.default_rng(5)
    sess = {"phase": "idle", "side": "radiant", "allies": [None] * 5, "enemies": [None] * 5, "bans": [], "rev": 0}
    state = {"gs": "DOTA_GAMERULES_STATE_HERO_SELECTION"}
    settings = types.SimpleNamespace(vision_collect=True, vision_collect_mb=50)
    col = collector.Collector(lambda: sess, lambda: state["gs"], lambda: settings)
    hs = heroes_with_icons(10, 9)
    ids = []
    import time
    for k in range(3):
        sess.update(phase="draft")
        col.tick(frame=frame_with(hs[:5], hs[5:], rng))
        ids.append(col.draft["id"])
        sess.update(phase="idle")
        col.tick()
        time.sleep(1.1)
    assert [d["id"] for d in collector.drafts()] == list(reversed(ids))
    settings.vision_collect_mb = 0          # anything over 0 bytes is too much
    sess.update(phase="draft")
    col.tick(frame=frame_with(hs[:5], hs[5:], rng))
    left = [d["id"] for d in collector.drafts()]
    assert left == [col.draft["id"]]        # only the draft being collected survives


def test_collection_off_saves_nothing(sandbox):
    sess = {"phase": "draft", "side": "radiant", "allies": [None] * 5, "enemies": [None] * 5, "bans": [], "rev": 0}
    settings = types.SimpleNamespace(vision_collect=False, vision_collect_mb=500)
    col = collector.Collector(lambda: sess, lambda: None, lambda: settings)
    col.tick(frame=np.zeros((H, W, 3), np.uint8))
    sess.update(phase="idle")
    col.tick()
    assert collector.drafts() == []     # an empty draft is not kept
