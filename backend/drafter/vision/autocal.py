"""Calibration from one frame whose heroes are known: find the slots instead of dragging rects.

Input: a frame from the end of hero selection (all ten portraits on the top bar) and the two
teams as sets (order unknown). Each hero's portrait is searched in the top band of the frame by
normalised cross-correlation at several sizes and aspect ratios. The confident hits must agree
on one row (same height and size); then five evenly spaced slots per team are fitted to them,
Radiant left of the centre and Dire mirrored, and the rects are returned in window fractions.
Valve moves this UI between patches, so this beats a fixed preset whenever a labelled frame exists.
"""

from __future__ import annotations

import statistics

import cv2
import numpy as np

from ..data import constants
from . import calibration, matcher

BAND = 0.16                  # portraits are in the top part of the window
HEIGHTS = np.geomspace(0.016, 0.075, 16)   # slot height as a share of the window height
ASPECTS = (None, 4 / 3, 1.0)               # None: the template's own aspect (16:9 hero icons)
MIN_SCORE = 0.45
MIN_HITS = 6
WORK_W = 1600                # the band is searched at most this wide (speed); results scale back


def _templates(hero_id: int, learned: bool) -> list[np.ndarray]:
    """The hero's art from the CDN, or (learned=True) crops learned from the user's screen. The art
    comes first: learned crops repeat the rects they were cut with and would pull the fit there."""
    if learned:
        folder = matcher.LEARNED / str(hero_id)
        paths = sorted(folder.glob("*.png"))[-3:] if folder.exists() else []
        return [img for p in paths if (img := matcher._read(p)) is not None]
    key = constants.hero_by_id()[hero_id]["key"]
    path = matcher.template_path(key)
    icon = matcher._read(path) if path else None
    return [icon] if icon is not None else []


def _find(band_grey: np.ndarray, hero_id: int, frame_h: float, learned: bool = False) -> tuple[float, int, int, int, int] | None:
    """Best (score, x, y, w, h) of this hero's portrait in the band (band pixel units)."""
    best = None
    for tpl in _templates(hero_id, learned):
        tgrey = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
        for aspect in ASPECTS:
            t = matcher._center_crop(tgrey, aspect) if aspect else tgrey
            ta = t.shape[1] / t.shape[0]
            for hf in HEIGHTS:
                h = int(round(hf * frame_h))
                w = int(round(h * ta))
                if h < 8 or w < 8 or h >= band_grey.shape[0] or w >= band_grey.shape[1]:
                    continue
                small = cv2.resize(t, (w, h), interpolation=cv2.INTER_AREA)
                res = cv2.matchTemplate(band_grey, small, cv2.TM_CCOEFF_NORMED)
                _, score, _, (x, y) = cv2.minMaxLoc(res)
                if best is None or score > best[0]:
                    best = (float(score), x, y, w, h)
    return best


def _fit_row(xs: list[float], step: float, tol: float) -> tuple[float, list[int]] | None:
    """x0 such that as many xs as possible sit at x0 + k*step (k = 0..4); returns x0 and the ks."""
    best = None
    for anchor in xs:
        for k in range(5):
            x0 = anchor - k * step
            ks = [round((x - x0) / step) for x in xs]
            fits = sum(0 <= kk <= 4 and abs(x - (x0 + kk * step)) <= tol for x, kk in zip(xs, ks))
            # more fits first; then the row closest to the centre (the bar hugs the clock)
            key = (fits, x0)
            if best is None or key > best[0]:
                best = (key, x0, ks)
    if best is None:
        return None
    return best[1], best[2]


def locate(frame: np.ndarray, radiant: list[int], dire: list[int],
           base: calibration.Calibration | None = None) -> tuple[calibration.Calibration | None, dict]:
    """A calibration fitted to this frame, and what was found (for the wizard / the log)."""
    H, W = frame.shape[:2]
    band = frame[: max(1, int(H * BAND))]
    scale = min(1.0, WORK_W / W)
    if scale < 1:
        band = cv2.resize(band, (int(W * scale), int(band.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    grey = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    hits = []
    for learned in (False, True):          # the art first; the user's own crops only if that fails
        hits = []
        for team, heroes in (("radiant", radiant), ("dire", dire)):
            for h in heroes:
                if not h:
                    continue
                f = _find(grey, h, H * scale, learned)
                if f and f[0] >= MIN_SCORE:
                    s, x, y, w, hh = f
                    hits.append({"team": team, "hero": h, "score": round(s, 3),
                                 "x": x / scale, "y": y / scale, "w": w / scale, "h": hh / scale})
        if len(hits) >= MIN_HITS:
            break
    info = {"hits": len(hits), "searched": sum(1 for h in radiant + dire if h)}
    if len(hits) < MIN_HITS:
        info["reason"] = f"нашёл уверенно только {len(hits)} портретов из {info['searched']}"
        return None, info
    # one row: drop hits of another size or height (a hero art elsewhere on the screen)
    mh = statistics.median(x["h"] for x in hits)
    my = statistics.median(x["y"] for x in hits)
    row = [x for x in hits if abs(x["h"] - mh) <= 0.2 * mh and abs(x["y"] - my) <= 0.5 * mh]
    if len(row) < MIN_HITS:
        info["reason"] = "портреты не выстроились в один ряд"
        return None, info
    w = statistics.median(x["w"] for x in row)
    h = statistics.median(x["h"] for x in row)
    cy = statistics.median(x["y"] + x["h"] / 2 for x in row)
    # centres, not left edges: a hit's width depends on the template crop that matched best.
    # Radiant slots left of the centre, Dire mirrored onto the same axis: one fit for both teams.
    pts = [x["x"] + x["w"] / 2 if x["team"] == "radiant" else W - (x["x"] + x["w"] / 2) for x in row]
    gaps = sorted(b - a for a, b in zip(sorted(pts), sorted(pts)[1:]) if b - a > 0.5 * w)
    if not gaps:
        info["reason"] = "не удалось определить шаг между слотами"
        return None, info
    step = gaps[0] if len(gaps) < 3 else statistics.median([g for g in gaps if g <= 1.5 * gaps[0]])
    fit = _fit_row(pts, step, tol=0.25 * step)
    if fit is None:
        info["reason"] = "слоты не легли на ровный ряд"
        return None, info
    x0, ks = fit
    fitted = sum(0 <= k <= 4 and abs(p - (x0 + k * step)) <= 0.25 * step for p, k in zip(pts, ks))
    info.update(fitted=fitted, step=round(step / W, 4), size=[round(w / W, 4), round(h / H, 4)])
    if fitted < MIN_HITS:
        info["reason"] = f"в ровный ряд легли только {fitted} портретов"
        return None, info
    rad = [[(x0 + k * step - w / 2) / W, (cy - h / 2) / H, w / W, h / H] for k in range(5)]
    dire_rects = [[1 - r[0] - r[2], r[1], r[2], r[3]] for r in reversed(rad)]
    clamp = lambda r: [min(max(v, 0.0), 1.0) for v in r]
    base = base or calibration.load()
    cal = calibration.Calibration(aspect=W / H, radiant=[clamp(r) for r in rad], dire=[clamp(r) for r in dire_rects],
                                  bans=base.bans, threshold=base.threshold, margin=base.margin, preset=False, auto=True)
    return cal, info
