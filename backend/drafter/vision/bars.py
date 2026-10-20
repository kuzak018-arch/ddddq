"""Finding the ten portrait slots of the draft by the players' colour bars — no calibration.

Above every portrait of Dota's top bar sits a thin bar in that player's colour (blue, teal, purple,
yellow, orange; pink, olive, light blue, green, brown). They are the most saturated thing at the very
top of the window, equally wide and equally spaced, and they are there in every phase of the draft,
picked or not. So their columns give the slots exactly, whatever the resolution, aspect ratio, UI
scale or window size: the bar width is the portrait width, the portrait starts right under the bar.

`find` returns the rects as a Calibration (source "bars"), or None when the frame has too few bars
(not the draft screen, or the top bar is hidden); the reader then falls back to the layout.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import calibration

BAND = 0.02          # the bars are within the top 2% of the window
MIN_SAT, MIN_VAL = 80, 90
MIN_RUNS = 4         # at least this many bars found, on both sides together
PORTRAIT_H = 0.6     # portrait height / bar width (the icons are a bit cropped 16:9 art)
INSET = 0.06         # the portraits are slanted: keep clear of the side edges


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Runs of True in a 1-D mask, as (start, end) half-open."""
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1).tolist(), np.flatnonzero(d == -1).tolist()))


def bar_runs(frame: np.ndarray) -> tuple[list[tuple[int, int]], int]:
    """Columns of the coloured bars and the row where they end. The bar rows are the topmost rows
    cut into several long clean coloured runs; the portraits below are textured and break them up."""
    H, W = frame.shape[:2]
    band = frame[: max(4, round(BAND * H))]
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    colored = (hsv[:, :, 1] >= MIN_SAT) & (hsv[:, :, 2] >= MIN_VAL)
    lo, hi = 0.05 * H, 0.25 * H     # a portrait is 5-25% of the window height wide
    counts = [sum(1 for a, b in _runs(colored[y]) if lo <= b - a <= hi) for y in range(len(colored))]
    if max(counts, default=0) < 2:
        return [], 0
    top = next(y for y, c in enumerate(counts) if c >= 2)
    peak = max(counts[top: top + 4])
    bottom = top
    while bottom < len(counts) and counts[bottom] >= max(2, 0.6 * peak):
        bottom += 1
    votes = colored[top:bottom].mean(axis=0) >= 0.6
    return [(a, b) for a, b in _runs(votes) if lo <= b - a <= hi], bottom


def fit_grid(runs: list[tuple[int, int]], width: int) -> tuple[list[int], list[int], int] | None:
    """Left edges of the 5 Radiant and 5 Dire slots and the slot width, from the bars found.
    Slots of a side are `pitch` apart; the sides mirror each other around the clock."""
    if len(runs) < MIN_RUNS:
        return None
    w = int(np.median([b - a for a, b in runs]))
    lefts = sorted(a for a, _ in runs)
    gaps = [b - a for a, b in zip(lefts, lefts[1:])]
    steps = [g for g in gaps if 1.02 * w <= g <= 1.7 * w]
    if not steps:
        return None
    pitch = float(np.median(steps))
    tol = 0.18 * pitch

    def grid(c: float, a: float) -> tuple[list[float], list[float]]:
        dire = [c + a + k * pitch for k in range(5)]
        radiant = [c - a - w - (4 - k) * pitch for k in range(5)]
        return radiant, dire

    def score(c: float, a: float) -> int:
        rad, dire = grid(c, a)
        slots = rad + dire
        return sum(1 for x in lefts if min(abs(x - s) for s in slots) <= tol)

    # the clock gap is the widest gap between bars: radiant on its left, dire on its right
    split = max(range(len(gaps)), key=gaps.__getitem__) if gaps else 0
    rad_l, dire_l = lefts[: split + 1], lefts[split + 1:]
    best = None
    candidates = []
    if rad_l and dire_l and gaps[split] > 1.7 * w:
        for d in dire_l:
            for kd in range(5):
                for r in rad_l:
                    for kr in range(5):
                        c = (d - kd * pitch + r + w + (4 - kr) * pitch) / 2
                        a = d - kd * pitch - c
                        if a > 0:
                            candidates.append((c, a))
    else:
        # one side only: the bar is centred in the window
        c = width / 2
        for x in lefts:
            for k in range(5):
                a = x - k * pitch - c if x > c else c - x - w - (4 - k) * pitch
                if a > 0:
                    candidates.append((c, a))
    for c, a in candidates:
        s = score(c, a)
        if best is None or s > best[0] or (s == best[0] and abs(c - width / 2) < abs(best[1] - width / 2)):
            best = (s, c, a)
    if best is None or best[0] < MIN_RUNS:
        return None
    rad, dire = grid(best[1], best[2])
    if rad[0] < -0.5 * w or dire[-1] + w > width + 0.5 * w:
        return None
    return [round(x) for x in rad], [round(x) for x in dire], w


def find(frame: np.ndarray) -> calibration.Calibration | None:
    H, W = frame.shape[:2]
    runs, bottom = bar_runs(frame)
    g = fit_grid(runs, W)
    if g is None:
        return None
    rad, dire, w = g
    y0 = bottom + 1
    ph = min(round(PORTRAIT_H * w), H - y0)
    inset = round(INSET * w)

    def rect(x: int) -> list[float]:
        x0 = min(max(x + inset, 0), W - 1)
        x1 = min(max(x + w - inset, x0 + 1), W)
        return [x0 / W, y0 / H, (x1 - x0) / W, ph / H]

    return calibration.Calibration(aspect=W / H, radiant=[rect(x) for x in rad], dire=[rect(x) for x in dire],
                                   source="bars")
