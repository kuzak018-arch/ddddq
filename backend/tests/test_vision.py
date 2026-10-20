import json

import cv2
import numpy as np
import pytest

from drafter.data import constants
from drafter.vision import calibration, evaluate, matcher, reader, runner

pytestmark = pytest.mark.skipif(not (constants.DIR / "heroes.json").exists() or not matcher.has_templates(),
                                reason="нужны константы и иконки героев")

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
    r.cautious = False                                  # accuracy proven: the normal pace
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


def test_cautious_reader_needs_a_frame_more_and_more_confidence(monkeypatch, tmp_path):
    monkeypatch.setattr(calibration, "PATH", tmp_path / "calibration.json")
    from drafter.vision import layout
    monkeypatch.setattr(layout, "PATH", tmp_path / "layout.json")
    cal = layout.for_frame(1920, 1080)
    state = {"allies": [None] * 5, "enemies": [None] * 5, "bans": [], "side": "radiant", "phase": "draft"}
    r = runner.Runner(lambda: state, lambda **c: state.update(c), lambda d: None)
    assert r.cautious                                   # from the first draft, before any proof
    f = frame_with([AM, None, None, None, None], [None] * 5, cal)
    assert r.step(f, dict(state)) is None and r.step(f, dict(state)) is None   # two frames: not yet
    ch = r.step(f, dict(state))
    assert ch["allies"][0] == AM and r.status()["cautious"]
    # a weak read (a blurred, darkened portrait) is left out while cautious, taken when proven
    weak = cv2.addWeighted(cv2.GaussianBlur(frame_with([None, PUDGE, None, None, None], [None] * 5, cal), (0, 0), 4), 0.55,
                           np.zeros_like(f), 0, 0)
    res = r._read(weak)
    r.cautious = False
    loose = r._read(weak)
    assert sum(x.hero is not None for x in res["radiant"]) <= sum(x.hero is not None for x in loose["radiant"])


def test_a_half_filled_board_does_not_make_right_reads_wrong(monkeypatch):
    from drafter.vision import collector
    S = matcher.SlotResult
    res = {"radiant": [S(AM, .9, .2, []), S(PUDGE, .9, .2, []), S(LION, .9, .2, []), S(None, 0, 0, [], True), S(None, 0, 0, [], True)],
           "dire": [S(10, .9, .2, []), S(AXE, .9, .2, []), S(None, 0, 0, [], True), S(None, 0, 0, [], True), S(None, 0, 0, [], True)],
           "bans": [], "warnings": [], "source": "profile"}
    monkeypatch.setattr(matcher, "_read", lambda p: np.zeros((10, 10, 3), np.uint8))
    monkeypatch.setattr(reader, "read", lambda img, cal=None, exclude=None: res)
    monkeypatch.setattr(collector, "frame_path", lambda fid: fid)
    # the user put only Anti-Mage on our side, but all five enemies (Lion among them)
    draft = {"id": "d", "frames": [{"id": "f", "complete": False}],
             "labels": {"radiant": [AM], "dire": [10, 11, 12, 13, LION], "bans": []}}
    r = evaluate.evaluate_collected(draft_list=[draft])
    # right: AM, 10. Wrong: Lion on our side (he is an enemy), Axe among complete enemies.
    # Pudge: our side's board is incomplete, so nobody knows - not counted
    assert (r["correct"], r["filled"], r["unknown"]) == (2, 4, 1)
    assert {w[3] for w in r["wrong"]} == {LION, AXE}


def test_one_hero_read_in_two_slots_is_put_in_one_place_only(monkeypatch):
    """A hero stably read in a radiant and a dire slot used to be put in both, and the session
    refused the patch («один и тот же герой указан дважды») — which ended screen reading."""
    S = matcher.SlotResult
    res = {"radiant": [S(AM, 0.9, 0.3, []), S(None, 0, 0, []), S(None, 0, 0, []), S(None, 0, 0, []), S(None, 0, 0, [])],
           "dire": [S(None, 0, 0, []), S(None, 0, 0, []), S(AM, 0.9, 0.3, []), S(None, 0, 0, []), S(None, 0, 0, [])],
           "bans": [S(AM, 0.9, 0.3, [])], "source": "x", "warnings": []}
    state = {"allies": [None] * 5, "enemies": [None] * 5, "bans": [], "side": "radiant", "phase": "draft"}
    r = runner.Runner(lambda: state, lambda **c: state.update(c), lambda d: None)
    r.cautious = False
    monkeypatch.setattr(r, "_read", lambda f: res)
    monkeypatch.setattr(r.autofit, "offer", lambda *a: False)
    monkeypatch.setattr(reader, "as_json", lambda x: {})
    for _ in range(4):
        r.step(None, dict(state))
    everywhere = state["allies"] + state["enemies"] + state["bans"]
    assert everywhere.count(AM) == 1 and state["allies"][0] == AM
