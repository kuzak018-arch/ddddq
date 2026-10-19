import json

import cv2
import numpy as np
import pytest

from drafter.data import constants
from drafter.vision import calibration, evaluate, matcher, reader, runner

pytestmark = pytest.mark.skipif(not matcher.has_templates(), reason="нужны иконки героев")

AM, AXE, PUDGE, LION = 1, 2, 14, 26


def frame_with(heroes_r, heroes_d, cal, size=(1920, 1080)):
    W, H = size
    frame = np.full((H, W, 3), 25, np.uint8)
    keys = {h["id"]: h["key"] for h in constants.hero_index()}
    for group, heroes in (("radiant", heroes_r), ("dire", heroes_d)):
        for rect, hid in zip(getattr(cal, group), heroes):
            if hid:
                x, y, w, h = calibration.to_pixels(rect, W, H)
                art = matcher._read(matcher.template_path(keys[hid]))
                frame[y:y + h, x:x + w] = cv2.resize(art, (w, h), interpolation=cv2.INTER_AREA)
    return frame


def test_preset_is_symmetric_and_valid():
    c = calibration.preset_16_9()
    assert len(c.radiant) == len(c.dire) == 5
    assert abs((c.radiant[0][0] + c.dire[4][0] + c.dire[4][2]) - 1) < 1e-9


def test_reader_finds_heroes_and_leaves_empty_slots_empty():
    cal = calibration.preset_16_9()
    res = reader.read(frame_with([AM, PUDGE, None, None, None], [AXE, None, None, None, LION], cal), cal)
    assert [r.hero for r in res["radiant"]] == [AM, PUDGE, None, None, None]
    assert [r.hero for r in res["dire"]] == [AXE, None, None, None, LION]
    assert res["radiant"][2].empty


def test_aspect_mismatch_warns():
    cal = calibration.preset_16_9()
    res = reader.read(frame_with([AM] + [None] * 4, [None] * 5, cal, size=(1600, 1200)), cal)
    assert res["warnings"]


def test_runner_needs_two_frames_side_and_respects_manual_edits():
    cal = calibration.preset_16_9()
    applied = []
    state = {"allies": [None] * 5, "enemies": [None] * 5, "bans": [], "side": None, "phase": "draft"}

    def patch(**c):
        applied.append(c)
        state.update(c)

    r = runner.Runner(lambda: state, patch, lambda d: None)
    f = frame_with([AM, None, None, None, None], [AXE, None, None, None, None], cal)
    assert r.step(f, dict(state), cal) is None          # side unknown -> nothing applied
    state["side"] = "dire"
    assert r.step(f, dict(state), cal) is None          # first sighting
    ch = r.step(f, dict(state), cal)                    # second -> applied, dire = mine
    assert ch["allies"][0] == AXE and ch["enemies"][0] == AM
    state["allies"][0] = LION                           # the user corrects the slot by hand
    r.step(f, dict(state), cal)
    r.step(f, dict(state), cal)
    assert state["allies"][0] == LION and ("dire", 0) in r.locked


def test_learned_template_and_eval_report(tmp_path, monkeypatch):
    monkeypatch.setattr(matcher, "LEARNED", tmp_path / "learned")
    cal = calibration.preset_16_9()
    f = frame_with([AM, PUDGE, None, None, None], [None] * 5, cal)
    crop = reader.crops(f, cal)["radiant"][0]
    p = matcher.learn(AM, crop)
    assert p.exists() and AM in matcher.bank(crop.shape[1] / crop.shape[0]).learned
    ds = tmp_path / "ds"
    ds.mkdir()
    cv2.imencode(".png", f)[1].tofile(str(ds / "a.png"))
    (ds / "a.json").write_text(json.dumps({"radiant": [AM, PUDGE, None, None, None], "dire": [None] * 5, "bans": []}))
    r = evaluate.evaluate(ds, cal)
    assert r["precision"] == 1.0 and r["recall"] == 1.0
