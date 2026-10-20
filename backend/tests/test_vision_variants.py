"""A portrait shown slightly shifted or zoomed (slanted slots, measured rects) still finds its hero."""

import cv2
import numpy as np
import pytest

from drafter.data import constants
from drafter.vision import matcher

ASPECT = 1.47
needs_heroes = pytest.mark.skipif(not (constants.DIR / "heroes.json").exists() or not matcher.has_templates(),
                                  reason="нужны константы героев и шаблоны (есть только на ПК)")


def crop(key, zoom=1.0, dx=0.0, dy=0.0, blur=0.0, bright=1.0, hw=96):
    img = matcher._read(matcher.template_path(key))
    c = cv2.resize(matcher._variant(img, ASPECT, zoom, dx, dy), (hw, int(hw / ASPECT)), interpolation=cv2.INTER_AREA)
    if blur:
        c = cv2.GaussianBlur(c, (0, 0), blur)
    return np.clip(c.astype(np.float32) * bright, 0, 255).astype(np.uint8)


def test_variant_crop_stays_inside_the_art_and_keeps_the_aspect():
    img = np.zeros((108, 192, 3), np.uint8)
    for zoom, dx, dy in matcher.VARIANTS:
        v = matcher._variant(img, ASPECT, zoom, dx, dy)
        assert 0 < v.shape[0] <= 108 and 0 < v.shape[1] <= 192 and abs(v.shape[1] / v.shape[0] - ASPECT) < 0.1


@needs_heroes
@pytest.mark.parametrize("kw", [{}, {"zoom": 1.3}, {"dx": 0.08}, {"dx": -0.12, "blur": 1.5}, {"zoom": 1.3, "dx": -0.08, "bright": 0.8}])
def test_shifted_zoomed_dimmed_portraits_are_still_recognised(kw):
    bank = matcher.bank(ASPECT)
    heroes = [h for h in constants.hero_index() if matcher.template_path(h["key"])][::4]       # every 4th: ~30 heroes
    got = [bank.match(crop(h["key"], **kw), 0.5, 0.08).hero for h in heroes]
    right = sum(g == h["id"] for g, h in zip(got, heroes))
    wrong = sum(g is not None and g != h["id"] for g, h in zip(got, heroes))
    assert right >= 0.95 * len(heroes) and wrong == 0


# ---------- learned crops that are filed under the wrong hero ----------------------------------

from pathlib import Path

from drafter.vision import bars, reader

REAL = Path(__file__).parent / "fixtures" / "draft_2000x514.png"     # the user's draft screen, top bar only (nicknames blanked)
LION, DAZZLE, MAGNUS, DISRUPTOR, OD, WARLOCK, WITCH_DOCTOR = "lion", "dazzle", "magnataur", "disruptor", "obsidian_destroyer", "warlock", "witch_doctor"


def _ids():
    return {h["key"]: h["id"] for h in constants.hero_index()}


@needs_heroes
def test_the_real_draft_frame_is_read():
    ids = _ids()
    frame = cv2.imread(str(REAL))
    res = reader.read(frame, bars.find(frame))
    got = {g: [r.hero for r in res[g]] for g in ("radiant", "dire")}
    assert got["radiant"][0] == ids[LION] and got["radiant"][1] == ids[DAZZLE] and got["radiant"][2] == ids[MAGNUS]
    assert got["radiant"][4] == ids[DISRUPTOR]
    assert got["dire"][0] == ids[OD] and got["dire"][3] == ids[WARLOCK] and got["dire"][4] == ids[WITCH_DOCTOR]


@needs_heroes
def test_a_mislabelled_learned_crop_does_not_take_over(tmp_path, monkeypatch):
    """Warlock's portrait once saved as Crystal Maiden used to make every Warlock read as CM for ever."""
    ids = _ids()
    frame = cv2.imread(str(REAL))
    cal = bars.find(frame)
    warlock_crop = reader.crops(frame, cal)["dire"][3]
    monkeypatch.setattr(matcher, "LEARNED", tmp_path / "learned")
    matcher._bank.cache_clear()
    # the poison, as old versions could write it: straight into the learned folder
    bad = tmp_path / "learned" / str(ids["crystal_maiden"])
    bad.mkdir(parents=True)
    cv2.imwrite(str(bad / "1.png"), warlock_crop)
    bank = matcher.bank(warlock_crop.shape[1] / warlock_crop.shape[0])
    assert bank.dropped == 1                                                  # recognised as someone else and left out
    assert reader.read(frame, cal)["dire"][3].hero == ids[WARLOCK]
    # and the same crop is refused when something tries to save it under the wrong name
    assert matcher.learn(ids["crystal_maiden"], warlock_crop) is None
    assert matcher.learn(ids[WARLOCK], warlock_crop) is not None              # under its own name it is welcome
    matcher._bank.cache_clear()


@needs_heroes
def test_a_hero_whose_art_is_stale_can_still_be_learned_from_the_screen():
    """Tinker's art in the program is the old model; the game shows the new one. His crop matches no
    art well, but nothing else claims it either: it is welcome as a learned template."""
    ids = _ids()
    frame = cv2.imread(str(REAL))
    tinker = reader.crops(frame, bars.find(frame))["radiant"][3]
    assert not matcher.contradicts_art(ids["tinker"], tinker)
    assert matcher.contradicts_art(ids["crystal_maiden"], reader.crops(frame, bars.find(frame))["dire"][3])   # Warlock's face is not CM
