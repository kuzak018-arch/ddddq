"""Draft slots from the players' colour bars: exact on a real frame, any size, no calibration."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from drafter.data import constants
from drafter.vision import bars, matcher, reader

FIX = Path(__file__).parent / "fixtures" / "topbar_2000x840.png"
PLAYER_COLORS = [(255, 117, 51), (191, 255, 102), (191, 0, 191), (11, 243, 243), (0, 107, 255),   # BGR
                 (195, 132, 254), (71, 180, 161), (247, 217, 101), (34, 131, 0), (0, 106, 164)]
needs_heroes = pytest.mark.skipif(not (constants.DIR / "heroes.json").exists() or not matcher.has_templates(),
                                  reason="нужны константы героев и шаблоны (есть только на ПК)")


def frame(w=1920, h=1080, slot=None, pitch=None, gap=None, top=0, art=None):
    """A synthetic top bar: 10 coloured bars, textured portraits under them."""
    slot = slot or round(0.104 * h)
    pitch = pitch or round(slot * 1.15)
    gap = gap or round(slot * 1.8)
    img = np.full((h, w, 3), (60, 45, 35), np.uint8)
    rng = np.random.default_rng(1)
    c = w // 2
    lefts = [c - gap // 2 - slot - (4 - k) * pitch for k in range(5)] + [c + gap // 2 + k * pitch for k in range(5)]
    bar = max(3, round(0.006 * h))
    for i, x in enumerate(lefts):
        img[top:top + bar, x:x + slot] = PLAYER_COLORS[i]
        ph = round(0.6 * slot)
        tile = art[i] if art else rng.integers(0, 255, (ph, slot, 3), dtype=np.uint8)
        img[top + bar:top + bar + ph, x:x + slot] = cv2.resize(tile, (slot, ph))
    return img, lefts, slot


@pytest.mark.parametrize("w,h", [(1920, 1080), (2560, 1440), (2560, 1080), (3440, 1440), (1280, 720), (1680, 1050)])
def test_slots_on_any_screen(w, h):
    img, lefts, slot = frame(w, h)
    cal = bars.find(img)
    assert cal is not None and cal.source == "bars"
    got = [r[0] * w for r in cal.radiant + cal.dire]
    inset = bars.INSET * slot
    assert all(abs(g - (x + inset)) <= 2 for g, x in zip(got, lefts))


def test_a_missing_bar_is_filled_in_from_the_others():
    img, lefts, slot = frame()
    img[:6, lefts[6]:lefts[6] + slot] = (60, 45, 35)       # one player's bar not drawn
    cal = bars.find(img)
    assert cal is not None and abs(cal.dire[1][0] * 1920 - (lefts[6] + bars.INSET * slot)) <= 2


def test_no_bars_no_slots():
    assert bars.find(np.full((1080, 1920, 3), 90, np.uint8)) is None
    img, *_ = frame()
    img[:12] = (60, 45, 35)
    assert bars.find(img) is None


def test_the_users_frame():
    """A 2000×840 screenshot of the user's draft (top bar only kept): the default layout missed the
    portraits there; the bars put all ten slots on them."""
    img = cv2.imread(str(FIX))
    cal = bars.find(img)
    lefts = [round(r[0] * img.shape[1]) for r in cal.radiant + cal.dire]
    expected = [69, 209, 349, 489, 629, 1084, 1224, 1364, 1504, 1644]
    assert all(abs(a - (b + round(bars.INSET * 121))) <= 3 for a, b in zip(lefts, expected))


@needs_heroes
def test_the_users_enemies_are_read():
    img = cv2.imread(str(FIX))
    cal = bars.find(img).model_copy(update={"threshold": 0.5, "margin": 0.08})
    res = reader.read(img, cal)
    names = {h["id"]: h["name"] for h in constants.hero_index()}
    dire = [names.get(r.hero) for r in res["dire"]]
    assert dire[:4] == ["Dragon Knight", "Winter Wyvern", "Wraith King", "Earthshaker"]
    assert [names.get(r.hero) for r in res["radiant"]][1:] == ["Dazzle", "Underlord", "Witch Doctor", "Warlock"]
