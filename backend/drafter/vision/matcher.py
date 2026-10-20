"""Hero portrait recognition by template matching (OpenCV, no neural networks).

Every slot crop and every template is brought to the same small size and compared by
  - normalised cross-correlation of blurred grey images (insensitive to brightness/contrast, so
    greyed-out ban portraits still match), and
  - hue/saturation histogram correlation (colour; skipped for bans, which are grey).
Templates: hero art shipped with the program (shared/hero-templates, the same for everyone; the
Steam CDN copy in the user's data only for heroes newer than the program), plus "learned" crops from the user's own game, saved
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

ICONS = config.DATA / "icons" / "heroes"        # downloaded hero art: heroes newer than the program
TEMPLATES = config.SHARED / "hero-templates"   # the same art shipped with the program (192x108)
LEARNED = config.DATA / "vision" / "learned"
CANON_W = 48           # canonical width; height follows the slot's aspect ratio
W_NCC, W_HIST = 0.75, 0.25
EMPTY_STD = 9.0        # a flat (empty / placeholder) slot has almost no texture
WRONG_HERO_SCORE = 0.6  # a learned crop is thrown out when the art says it is another hero this surely...
WRONG_HERO_GAP = 0.15   # ...and its own hero's art matches it this much worse


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


# How the game may show the same art compared with our copy: a bit zoomed in and/or shifted (the
# portraits are slanted and the slot rects are measured, not exact). Each art template is also
# matched in these variants (zoom, horizontal shift and vertical shift as shares of its size); a
# crop that is slightly off then still finds its hero. Learned crops are exact and stay as they are.
VARIANTS = [(1.0, 0.0, 0.0), (1.15, 0.0, 0.0), (1.3, 0.0, 0.0), (1.0, -0.08, 0.0), (1.0, 0.08, 0.0),
            (1.15, -0.08, 0.0), (1.15, 0.08, 0.0), (1.0, 0.0, 0.06), (1.0, 0.0, -0.06), (1.0, -0.14, 0.0), (1.0, 0.14, 0.0)]


def _variant(img: np.ndarray, aspect: float, zoom: float, dx: float, dy: float) -> np.ndarray:
    h, w = img.shape[:2]
    ch = h / zoom
    cw = ch * aspect
    if cw > w:
        cw, ch = w, w / aspect
    x0 = int(np.clip(w / 2 + dx * w - cw / 2, 0, w - cw))
    y0 = int(np.clip(h / 2 + dy * h - ch / 2, 0, h - ch))
    return img[y0:y0 + max(1, int(ch)), x0:x0 + max(1, int(cw))]


def _read(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)  # cv2.imread can't open non-ASCII paths on Windows
    img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 3 and img.shape[2] == 4:  # transparent PNG: flatten on black like the game UI
        alpha = img[:, :, 3:4].astype(np.float32) / 255
        img = (img[:, :, :3].astype(np.float32) * alpha).astype(np.uint8)
    return img


def template_path(key: str) -> Path | None:
    """The hero's art: the copy shipped with the program, else the downloaded one."""
    return next(iter(template_paths(key)), None)


def template_paths(key: str) -> list[Path]:
    """All copies of the hero's art: the one shipped with the program and the one downloaded from the
    CDN (newer when Valve redrew the hero; both are templates, the better match wins)."""
    return [p for p in (TEMPLATES / f"{key}.jpg", ICONS / f"{key}.png") if p.exists()]


def has_templates() -> bool:
    return TEMPLATES.exists() or ICONS.exists()


@lru_cache(maxsize=16)
def _art(aspect_key: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Feature matrices of the art templates alone (every hero in every VARIANT) at one aspect."""
    ids, greys, hists = [], [], []
    for h in constants.hero_index():
        for art in template_paths(h["key"]):
            img = _read(art)
            if img is None:
                continue
            for v in VARIANTS:
                g, hh = _features(_variant(img, aspect_key, *v), aspect_key)
                ids.append(h["id"])
                greys.append(g)
                hists.append(hh)
    if not ids:
        return np.zeros(0, int), np.zeros((0, 1), np.float32), np.zeros((0, 1), np.float32)
    return np.array(ids), np.stack(greys), np.stack(hists)


def _contradicts(art_ids: np.ndarray, art_grey: np.ndarray, hero_id: int, grey_feature: np.ndarray) -> bool:
    """The crop clearly shows another hero by the art templates: it was filed under the wrong name
    (a mislabelled slot). Without art for comparison nothing is judged."""
    if not len(art_ids):
        return False
    score = art_grey @ grey_feature
    best_hero, best, own = None, -9.0, -9.0
    for hid, sc in zip(art_ids.tolist(), score.tolist()):
        if sc > best:
            best_hero, best = hid, sc
        if hid == hero_id and sc > own:
            own = sc
    return best_hero != hero_id and best >= WRONG_HERO_SCORE and own < best - WRONG_HERO_GAP


class TemplateBank:
    """Feature matrices for all heroes at one slot aspect ratio. `exclude`: skip templates learned
    automatically from that draft (its frames must not be judged by crops taken from them)."""

    def __init__(self, aspect: float, exclude: str | None = None):
        self.aspect = aspect
        art_ids, art_grey, art_hist = _art(aspect)
        ids, greys, hists = list(art_ids.tolist()), list(art_grey), list(art_hist)
        # learned crops: how a portrait looks in the user's game, but only those that really are the
        # hero they are filed under: one wrong crop would otherwise win for every later look-alike
        self.dropped = 0
        for h in constants.hero_index():
            learned = sorted((LEARNED / str(h["id"])).glob("*.png"))
            if exclude:
                learned = [p for p in learned if not p.name.startswith(f"{exclude}__")]
            for p in learned:
                crop = _read(p)
                if crop is None:
                    continue
                g, hh = _features(crop, aspect)
                if _contradicts(art_ids, art_grey, h["id"], g):
                    self.dropped += 1
                    continue
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


@lru_cache(maxsize=16)
def _bank(aspect_key: float, version: float, exclude: str | None) -> TemplateBank:
    return TemplateBank(aspect_key, exclude)


_learned_version = 0.0


def reload() -> None:
    """Forget the cached template banks (the art on disk changed)."""
    _art.cache_clear()
    _bank.cache_clear()


def bank(aspect: float, exclude: str | None = None) -> TemplateBank:
    """Banks are cached per slot aspect (rounded) and rebuilt when a learned template is added."""
    return _bank(round(aspect, 2), _learned_version, exclude)


def contradicts_art(hero_id: int, crop_bgr: np.ndarray) -> bool:
    """Would this crop, filed under hero_id, be thrown out: the art says it is another hero."""
    aspect = round(crop_bgr.shape[1] / crop_bgr.shape[0], 2)
    art_ids, art_grey, _ = _art(aspect)
    g, _ = _features(crop_bgr, aspect)
    return _contradicts(art_ids, art_grey, hero_id, g)


def learn(hero_id: int, crop_bgr: np.ndarray, tag: str | None = None) -> Path | None:
    """Save how this hero's portrait looks in the user's game; used as a template from now on.
    `tag`: the draft an automatic template came from (see TemplateBank's exclude). None: the crop
    is not this hero by the art (a mislabelled slot) and is not saved."""
    global _learned_version
    if contradicts_art(hero_id, crop_bgr):
        return None
    folder = LEARNED / str(hero_id)
    folder.mkdir(parents=True, exist_ok=True)
    prefix = f"{tag}__" if tag else ""
    path = folder / f"{prefix}{int(time.time() * 1000)}.png"
    ok, buf = cv2.imencode(".png", crop_bgr)
    if not ok:
        raise ValueError("не удалось сохранить вырезку")
    buf.tofile(str(path))
    _learned_version = time.time()
    return path
