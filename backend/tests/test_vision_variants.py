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
