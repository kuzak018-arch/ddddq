"""How the screen reader fills the draft board: one hero per slot, the screen's order, my own
hero placed by elimination, the bars' slots kept when a frame hides them."""

import cv2
import numpy as np
import pytest

from drafter.data import constants
from drafter.vision import bars, calibration, matcher, runner
from tests.test_vision import AM, AXE, LION, PUDGE, frame_with

pytestmark = pytest.mark.skipif(not (constants.DIR / "heroes.json").exists() or not matcher.has_templates(),
                                reason="нужны константы и иконки героев")

CM, WD, SVEN, ZEUS = 5, 30, 18, 22


def board(side="radiant", allies=None, enemies=None, me=None):
    return {"allies": allies or [None] * 5, "enemies": enemies or [None] * 5, "bans": [], "side": side,
            "phase": "draft", "my_hero": me}


def run(r, state, frame, cal, n):
    for _ in range(n):
        r.step(frame, dict(state, allies=list(state["allies"]), enemies=list(state["enemies"])), cal)


def make(state):
    r = runner.Runner(lambda: state, lambda **c: state.update(c), lambda d: None)
    r.cautious = False
    return r


def slot_result(hero, score):
    return matcher.SlotResult(hero, score, 0.2, [(hero, score)] if hero else [])


def test_one_hero_is_kept_only_in_its_best_slot():
    res = {"radiant": [slot_result(CM, 0.6), slot_result(AM, 0.8)] + [slot_result(None, 0)] * 3,
           "dire": [slot_result(None, 0)] * 3 + [slot_result(CM, 0.75), slot_result(CM, 0.7)], "bans": []}
    out = runner.unique(res)
    got = [r.hero for r in out["radiant"] + out["dire"]]
    assert got.count(CM) == 1 and out["dire"][3].hero == CM and out["radiant"][1].hero == AM


def test_my_hero_from_gsi_moves_to_the_slot_it_is_seen_in():
    cal = calibration.preset_16_9()
    # GSI put my hero (Pudge) into the first free slot; on the screen I am the third
    state = board(allies=[PUDGE, None, None, None, None], me=PUDGE)
    r = make(state)
    run(r, state, frame_with([AM, AXE, PUDGE, None, None], [None] * 5, cal), cal, 3)
    assert state["allies"][:3] == [AM, AXE, PUDGE] and state["allies"].count(PUDGE) == 1


def test_a_hero_the_user_typed_is_never_replaced():
    cal = calibration.preset_16_9()
    state = board(enemies=[LION, None, None, None, None])
    r = make(state)
    run(r, state, frame_with([None] * 5, [AXE, PUDGE, None, None, None], cal), cal, 6)
    assert state["enemies"][0] == LION and state["enemies"][1] == PUDGE


def test_my_hero_on_an_unknown_portrait_is_placed_by_elimination_and_learned(tmp_path, monkeypatch):
    monkeypatch.setattr(matcher, "LEARNED", tmp_path / "learned")
    matcher.reload()
    cal = calibration.preset_16_9()
    frame = frame_with([AM, AXE, None, LION, PUDGE], [None] * 5, cal)
    # slot 3: a portrait no template knows (a persona): textured, not a hero art
    x, y, w, h = calibration.to_pixels(cal.radiant[2], 1920, 1080)
    keys = {h["id"]: h["key"] for h in constants.hero_index()}
    a, b = (cv2.resize(matcher._read(matcher.template_path(keys[k])), (w, h)) for k in (CM, ZEUS))
    frame[y:y + h, x:x + w] = cv2.flip(cv2.addWeighted(a, 0.5, b, 0.5, 0), 1)
    state = board(allies=[SVEN, None, None, None, None], me=SVEN)
    r = make(state)
    run(r, state, frame, cal, 3 + runner.ME_FRAMES)
    assert state["allies"][2] == SVEN and sorted(h for h in state["allies"] if h) == sorted([AM, AXE, SVEN, LION, PUDGE])
    assert any((tmp_path / "learned" / str(SVEN)).glob("*.png"))
    matcher.reload()


def test_slots_from_the_bars_are_kept_when_a_frame_hides_them():
    from tests.test_vision_bars import frame as bar_frame
    img, _, _ = bar_frame()
    r = make(board())
    assert r._read(img)["source"] == "bars"
    hidden = img.copy()
    hidden[: int(0.03 * img.shape[0])] = 30        # the bars covered (tooltip, animation)
    assert bars.find(hidden) is None and r._read(hidden)["source"] == "bars-kept"
