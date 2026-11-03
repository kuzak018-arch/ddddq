"""Read the whole draft (10 picks + bans) from one frame using the calibration."""

from __future__ import annotations

from dataclasses import asdict, replace

import numpy as np

from . import bars, calibration, layout, matcher


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
    `exclude`: leave out templates learned from that draft (fair accuracy on its own frames).
    Without `cal` the slots are found by the players' colour bars (bars.find), else the rects for
    this frame's size (layout.for_frame)."""
    h, w = frame.shape[:2]
    cal = cal or bars.find(frame) or layout.for_frame(w, h)
    warnings = []
    if abs(w / h - cal.aspect) > 0.02:
        warnings.append(f"соотношение сторон окна {w}×{h} отличается от этих рамок — для этого размера есть встроенный профиль")
    result: dict = {"warnings": warnings, "source": cal.source}
    for group, items in crops(frame, cal).items():
        res = []
        for crop in items:
            if crop.size == 0:
                res.append(matcher.SlotResult(None, 0, 0, [], empty=True))
                continue
            aspect = crop.shape[1] / crop.shape[0]
            res.append(matcher.bank(aspect, exclude).match(crop, cal.threshold, cal.margin, ban=group == "bans"))
        result[group] = res
    _drop_repeated(result)
    return result


def _drop_repeated(result: dict) -> None:
    """One hero «found» in REPEATED_SLOTS or more pick slots of the frame is a template that looks
    like anything (a placeholder saved under a hero): those slots stay empty, and the hero's
    learned portraits, when it has any, are moved to quarantine so the next frames are read by art."""
    picks = [r for g in ("radiant", "dire") for r in result.get(g, [])]
    counts: dict[int, int] = {}
    for r in picks:
        if r.hero:
            counts[r.hero] = counts.get(r.hero, 0) + 1
    for hero, n in counts.items():
        if n < matcher.REPEATED_SLOTS:
            continue
        for g in ("radiant", "dire"):   # copies: the bank keeps its results for the next frames
            result[g] = [replace(r, hero=None) if r.hero == hero else r for r in result.get(g, [])]
        moved = matcher.quarantine(hero)
        result["warnings"].append(f"один герой нашёлся в {n} слотах — слоты оставлены пустыми"
                                  + (f", его запомненные портреты ({moved}) убраны в карантин" if moved else ""))


def as_json(result: dict) -> dict:
    return {k: (v if k in ("warnings", "source") else [asdict(r) for r in v]) for k, v in result.items()}
