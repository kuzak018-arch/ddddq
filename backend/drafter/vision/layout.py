"""Where the draft portraits are on any screen, without calibration.

Panorama (Dota's UI) lays out in units of 1/1080 of the window height: the same panel is the same
share of the height at 1080p, 1440p and 2160p, and a bar anchored to the centre stays at the same
height-units from the centre on 16:10 and 21:9 (more of the world shows on the sides). So a layout
is stored once, in those units relative to the horizontal centre, and becomes rects (window
fractions) for whatever frame comes in.

The default layout was measured on a 2560×1440 frame of the user's game (strategy time, ranked All
Pick, client of October 2026): the top bar with five portraits per team either side of the clock.
When the user (or the automatic fit on a labelled frame) saved rects, those become the layout for
every other resolution too. On top of that `detect` fits scale and offset to a frame with portraits
(no labels needed): the crops that land exactly on the portraits match the hero art best.
"""

from __future__ import annotations

import json
import time

import numpy as np

from .. import config
from . import calibration, matcher

REF_H = 1080
PATH = config.DATA / "vision" / "layout.json"     # detected fits per resolution

# Dire slot k (0..4) from the centre: left edge 146 + 123k, 107 wide; art 5..65 from the top.
# Radiant is the mirror image. Measured, ±3 units: `detect` fixes the rest on the first frames.
DEFAULT = {
    "dire": [[146 + 123 * k, 5, 107, 60] for k in range(5)],
    "bans": [],
}
DEFAULT["radiant"] = [[-(x + w), y, w, h] for x, y, w, h in reversed(DEFAULT["dire"])]

# Resolutions shown in the wizard; every other one works the same way.
PROFILES = [(1920, 1080), (2560, 1440), (3840, 2160), (1920, 1200), (2560, 1600), (2560, 1080), (3440, 1440)]

GROUPS = ("radiant", "dire", "bans")
ASPECT_TOL = 0.02


def aspect_label(w: int, h: int) -> str:
    a = w / h
    for name, v in (("16:9", 16 / 9), ("16:10", 16 / 10), ("21:9", 64 / 27), ("21:9", 43 / 18), ("4:3", 4 / 3)):
        if abs(a - v) < ASPECT_TOL:
            return name
    return f"{a:.2f}:1"


def from_calibration(cal: calibration.Calibration) -> dict:
    """Rects in window fractions at the calibration's aspect -> height units from the centre."""
    a = cal.aspect * REF_H
    return {g: [[(x - 0.5) * a, y * REF_H, w * a, h * REF_H] for x, y, w, h in getattr(cal, g)] for g in GROUPS}


def to_rects(layout: dict, width: int, height: int, scale: float = 1.0, dx: float = 0.0, dy: float = 0.0) -> dict:
    """Height units -> window fractions for this frame. scale: on top of height/1080; dx, dy: shift
    of the whole bar in pixels."""
    k = height / REF_H * scale
    out = {}
    for g in GROUPS:
        rs = []
        for ux, uy, uw, uh in layout.get(g, []):
            x = (width / 2 + dx + ux * k) / width
            y = (dy + uy * k) / height
            w, h = uw * k / width, uh * k / height
            # inside the frame: a rect half outside would be cut by the reader anyway
            x, y = min(max(x, 0.0), 1 - w), min(max(y, 0.0), 1 - h)
            rs.append([x, y, min(w, 1.0), min(h, 1.0)])
        out[g] = rs
    return out


def _saved() -> calibration.Calibration | None:
    if not calibration.PATH.exists():
        return None
    try:
        return calibration.Calibration.model_validate_json(calibration.PATH.read_text(encoding="utf-8"))
    except ValueError:
        return None


def base() -> tuple[dict, str]:
    """The layout every resolution starts from: the user's saved rects if any, else the measured one."""
    cal = _saved()
    if cal and not cal.preset:
        lay = from_calibration(cal)
        if not lay["bans"]:
            lay["bans"] = DEFAULT["bans"]
        return lay, "auto" if cal.auto else "manual"
    return DEFAULT, "default"


def _detected() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    except ValueError:
        return {}


def _key(width: int, height: int) -> str:
    return f"{width}x{height}"


def profile(width: int, height: int) -> calibration.Calibration:
    """The built-in rects for this resolution (no detection, no saved rects)."""
    return _make(DEFAULT, width, height, source="profile")


def _make(layout: dict, width: int, height: int, source: str, fit: dict | None = None) -> calibration.Calibration:
    saved = _saved()
    fit = fit or {}
    rects = to_rects(layout, width, height, fit.get("scale", 1.0), fit.get("dx", 0.0), fit.get("dy", 0.0))
    return calibration.Calibration(aspect=width / height, **rects,
                                   threshold=saved.threshold if saved else 0.55, margin=saved.margin if saved else 0.06,
                                   preset=source == "profile", auto=source != "manual", source=source)


def for_frame(width: int, height: int) -> calibration.Calibration:
    """The rects the reader uses on a frame of this size, best source first:
    1. rects saved for this aspect (by hand, or fitted on a frame with known heroes);
    2. scale and offset detected on an earlier frame of this resolution;
    3. the layout (the saved rects converted, or the measured default) scaled to this frame."""
    saved = _saved()
    if saved and not saved.preset and abs(saved.aspect - width / height) <= ASPECT_TOL:
        return saved.model_copy(update={"source": "auto" if saved.auto else "manual"})
    lay, origin = base()
    fit = _detected().get(_key(width, height))
    if fit and fit.get("base") == origin:
        return _make(lay, width, height, "detected", fit)
    return _make(lay, width, height, "profile" if origin == "default" else f"from-{origin}")


# ---------- detection ---------------------------------------------------------------------------

SCALES = np.geomspace(0.8, 1.25, 15)
MIN_PORTRAITS = 4            # non-empty slots needed to trust a fit
MIN_SCORE = 0.5              # mean best-template score of those slots at the fit
RETRY_AFTER = 15.0           # seconds between attempts on live frames


def _slot_scores(frame: np.ndarray, rects: dict, bank) -> list[float | None]:
    """Best template score per pick slot; None for a flat (empty) crop."""
    H, W = frame.shape[:2]
    out = []
    for g in ("radiant", "dire"):
        for r in rects[g]:
            x, y, w, h = calibration.to_pixels(r, W, H)
            crop = frame[y:y + h, x:x + w]
            if crop.size == 0 or crop.std() < matcher.EMPTY_STD:
                out.append(None)
                continue
            gr, hi = matcher._features(crop, bank.aspect)
            out.append(float((matcher.W_NCC * (bank.grey @ gr) + matcher.W_HIST * (bank.hist @ hi)).max()))
    return out


def _value(scores: list[float | None]) -> float:
    # empty slots count as 0: a fit that slides the crops off the portraits onto the background
    # must not win by having fewer, luckier crops
    return sum(s for s in scores if s is not None) / len(scores)


def detect(frame: np.ndarray, layout: dict | None = None) -> tuple[dict | None, dict]:
    """Scale and offset of the layout on this frame. Returns (fit, info); fit None when the frame
    has too few portraits or none of them matches well (not the draft screen?)."""
    H, W = frame.shape[:2]
    lay = layout or base()[0]
    uw, uh = lay["dire"][0][2], lay["dire"][0][3]
    bank = matcher.bank(uw / uh)
    # coarse: scale x horizontal shift (the bar is centred, ±3% of the width) x vertical shift
    best = (-1.0, 1.0, 0.0, 0.0)
    for s in SCALES:
        step = uw * H / REF_H * s / 8
        for dx in np.arange(-0.03 * W, 0.03 * W + 1, step):
            for dy in (0.0, 0.015 * H, 0.03 * H):
                v = _value(_slot_scores(frame, to_rects(lay, W, H, s, dx, dy), bank))
                if v > best[0]:
                    best = (v, s, dx, dy)
    # fine: around the best, a pixel or two at a time
    _, s0, dx0, dy0 = best
    for s in s0 * np.geomspace(0.97, 1.03, 9):
        px = uw * H / REF_H * s
        for dx in dx0 + np.linspace(-px / 8, px / 8, 9):
            for dy in dy0 + np.linspace(-0.01 * H, 0.01 * H, 7):
                v = _value(_slot_scores(frame, to_rects(lay, W, H, s, dx, dy), bank))
                if v > best[0]:
                    best = (v, s, dx, dy)
    v, s, dx, dy = best
    scores = _slot_scores(frame, to_rects(lay, W, H, s, dx, dy), bank)
    filled = [x for x in scores if x is not None]
    info = {"portraits": len(filled), "score": round(sum(filled) / len(filled), 3) if filled else 0.0,
            "scale": round(float(s), 4), "dx": round(float(dx), 1), "dy": round(float(dy), 1), "size": [W, H]}
    if len(filled) < MIN_PORTRAITS:
        info["reason"] = f"на кадре только {len(filled)} портретов — нужен кадр, где выбрано хотя бы {MIN_PORTRAITS} героя"
        return None, info
    if info["score"] < MIN_SCORE:
        info["reason"] = "портреты на кадре не похожи на героев: это экран выбора героев?"
        return None, info
    return {"scale": float(s), "dx": float(dx), "dy": float(dy), "score": info["score"], "portraits": len(filled)}, info


def save_fit(width: int, height: int, fit: dict) -> None:
    data = _detected()
    data[_key(width, height)] = {**fit, "base": base()[1], "at": time.time()}
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(data, indent=1), encoding="utf-8")


def forget_fits() -> None:
    PATH.unlink(missing_ok=True)


class AutoFit:
    """Live frames: until a resolution has a fit, try one on a frame with enough portraits every
    RETRY_AFTER seconds (detection takes about a second, so not on every frame)."""

    def __init__(self):
        self.last_try: dict[str, float] = {}
        self.last_info: dict | None = None

    def offer(self, frame: np.ndarray, source: str) -> dict | None:
        if source not in ("profile", "from-manual", "from-auto"):
            return None
        H, W = frame.shape[:2]
        key = _key(W, H)
        if time.time() - self.last_try.get(key, 0) < RETRY_AFTER:
            return None
        self.last_try[key] = time.time()
        fit, info = detect(frame)
        self.last_info = {**info, "at": time.time(), "saved": fit is not None}
        if fit:
            save_fit(W, H, fit)
        return self.last_info
