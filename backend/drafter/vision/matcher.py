"""Hero portrait recognition by template matching (OpenCV, no neural networks).

Every slot crop and every template is brought to the same small size and compared by
  - normalised cross-correlation of blurred grey images (insensitive to brightness/contrast, so
    greyed-out ban portraits still match), and
  - hue/saturation histogram correlation (colour; skipped for bans, which are grey).
Templates: hero art from the Steam CDN, plus "learned" crops from the user's own game, saved
whenever they correct a slot. A learned crop is the strongest evidence, because it is literally
how that portrait looks on their screen.

A slot is filled only when the best score clears `threshold` and beats the runner-up by `margin`;
otherwise it stays empty (a wrong hero is worse than a blank slot).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .. import config
from ..data import constants

ICONS = config.DATA / "icons" / "heroes"
LEARNED = config.DATA / "vision" / "learned"
CANON_W = 48           # canonical width; height follows the slot's aspect ratio
W_NCC, W_HIST = 0.75, 0.25
EMPTY_STD = 9.0        # a flat (empty / placeholder) slot has almost no texture


@dataclass
class SlotResult:
    hero: int | None
    score: float
    margin: float
    candidates: list[tuple[int, float]]   # top-3 (hero, score)
    empty: bool = False


def _canon_size(aspect: float) -> tuple[int, int]:
    return CANON_W, max(8, round(CANON_W / aspect))


def _center_crop(img: np.ndarray, aspect: float) -> np.ndarray:
    h, w = img.shape[:2]
    if w / h > aspect:   # too wide: cut the sides
        nw = round(h * aspect)
        x0 = (w - nw) // 2
        return img[:, x0:x0 + nw]
    nh = round(w / aspect)
    y0 = (h - nh) // 2
    return img[y0:y0 + nh]


def _features(img_bgr: np.ndarray, aspect: float) -> tuple[np.ndarray, np.ndarray]:
    cw, ch = _canon_size(aspect)
    small = cv2.resize(_center_crop(img_bgr, aspect), (cw, ch), interpolation=cv2.INTER_AREA)
    grey = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (3, 3), 0).astype(np.float32).ravel()
    grey -= grey.mean()
    grey /= np.linalg.norm(grey) + 1e-6
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [12, 4], [0, 180, 0, 256]).astype(np.float32).ravel()
    hist -= hist.mean()
    hist /= np.linalg.norm(hist) + 1e-6
    return grey, hist


def _read(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)  # cv2.imread can't open non-ASCII paths on Windows
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 3 and img.shape[2] == 4:  # transparent PNG: flatten on black like the game UI
        alpha = img[:, :, 3:4].astype(np.float32) / 255
        img = (img[:, :, :3].astype(np.float32) * alpha).astype(np.uint8)
    return img


class TemplateBank:
    """Feature matrices for all heroes at one slot aspect ratio."""

    def __init__(self, aspect: float):
        self.aspect = aspect
        ids, greys, hists = [], [], []
        for h in constants.hero_index():
            sources = [ICONS / f"{h['key']}.png", *sorted((LEARNED / str(h["id"])).glob("*.png"))]
            for p in sources:
                img = _read(p) if p.exists() else None
                if img is None:
                    continue
                g, hh = _features(img, aspect)
                ids.append(h["id"])
                greys.append(g)
                hists.append(hh)
        self.ids = np.array(ids)
        self.grey = np.stack(greys)
        self.hist = np.stack(hists)
        self.learned = {int(p.name) for p in LEARNED.glob("*") if p.is_dir() and any(p.glob("*.png"))} \
            if LEARNED.exists() else set()

    def match(self, crop_bgr: np.ndarray, threshold: float, margin: float, ban: bool = False) -> SlotResult:
        grey_raw = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        if grey_raw.std() < EMPTY_STD:
            return SlotResult(None, 0.0, 0.0, [], empty=True)
        g, hh = _features(crop_bgr, self.aspect)
        score = self.grey @ g if ban else W_NCC * (self.grey @ g) + W_HIST * (self.hist @ hh)
        best: dict[int, float] = {}
        for hid, s in zip(self.ids.tolist(), score.tolist()):   # several templates per hero: keep the best
            if s > best.get(hid, -9):
                best[hid] = s
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        (h1, s1), (_, s2) = ranked[0], ranked[1]
        ok = s1 >= threshold and s1 - s2 >= margin
        return SlotResult(h1 if ok else None, round(s1, 4), round(s1 - s2, 4),
                          [(h, round(s, 4)) for h, s in ranked[:3]])


@lru_cache(maxsize=8)
def _bank(aspect_key: float, version: float) -> TemplateBank:
    return TemplateBank(aspect_key)


_learned_version = 0.0


def bank(aspect: float) -> TemplateBank:
    """Banks are cached per slot aspect (rounded) and rebuilt when a learned template is added."""
    return _bank(round(aspect, 2), _learned_version)


def learn(hero_id: int, crop_bgr: np.ndarray) -> Path:
    """Save how this hero's portrait looks in the user's game; used as a template from now on."""
    global _learned_version
    folder = LEARNED / str(hero_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{int(time.time() * 1000)}.png"
    ok, buf = cv2.imencode(".png", crop_bgr)
    if not ok:
        raise ValueError("не удалось сохранить вырезку")
    buf.tofile(str(path))
    _learned_version = time.time()
    return path
