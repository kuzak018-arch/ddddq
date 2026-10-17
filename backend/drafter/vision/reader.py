"""Read the whole draft (10 picks + bans) from one frame using the calibration."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np

from . import calibration, matcher


def crops(frame: np.ndarray, cal: calibration.Calibration) -> dict[str, list[np.ndarray]]:
    h, w = frame.shape[:2]
    out = {}
    for group in ("radiant", "dire", "bans"):
        out[group] = []
        for rect in getattr(cal, group):
            x, y, cw, ch = calibration.to_pixels(rect, w, h)
            out[group].append(frame[y:y + ch, x:x + cw])
    return out


def read(frame: np.ndarray, cal: calibration.Calibration | None = None, exclude: str | None = None) -> dict:
    """{radiant: [SlotResult x5], dire: [...], bans: [...], warnings: [...]}
    `exclude`: leave out templates learned from that draft (fair accuracy on its own frames)."""
    cal = cal or calibration.load()
    h, w = frame.shape[:2]
    warnings = []
    if abs(w / h - cal.aspect) > 0.02:
        warnings.append(f"соотношение сторон окна {w}×{h} отличается от калибровки — откалибруй заново")
    result: dict = {"warnings": warnings}
    for group, items in crops(frame, cal).items():
        res = []
        for crop in items:
            if crop.size == 0:
                res.append(matcher.SlotResult(None, 0, 0, [], empty=True))
                continue
            aspect = crop.shape[1] / crop.shape[0]
            res.append(matcher.bank(aspect, exclude).match(crop, cal.threshold, cal.margin, ban=group == "bans"))
        result[group] = res
    return result


def as_json(result: dict) -> dict:
    return {k: (v if k == "warnings" else [asdict(r) for r in v]) for k, v in result.items()}
