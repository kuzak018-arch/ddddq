"""Where the hero portraits are on the draft screen.

Rects are stored as fractions of the window size [x, y, w, h], so one calibration works for any
resolution with the same aspect ratio. The preset is a starting point only (the in-game top bar
layout for 16:9); the calibration wizard lets the user drag the rects onto their own screenshot.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator

from .. import config

PATH = config.DATA / "vision" / "calibration.json"
Rect = list[float]


class Calibration(BaseModel):
    aspect: float = Field(16 / 9, description="ширина/высота окна при калибровке")
    radiant: list[Rect]
    dire: list[Rect]
    bans: list[Rect] = Field(default_factory=list)
    threshold: float = Field(0.55, ge=0.2, le=0.95, description="минимальная уверенность")
    margin: float = Field(0.06, ge=0, le=0.5, description="отрыв от второго кандидата")
    preset: bool = False

    @field_validator("radiant", "dire")
    @classmethod
    def five(cls, v):
        if len(v) != 5:
            raise ValueError("нужно ровно 5 слотов")
        return v

    @field_validator("radiant", "dire", "bans")
    @classmethod
    def in_frame(cls, v):
        for r in v:
            if len(r) != 4 or not all(0 <= x <= 1 for x in r) or r[2] <= 0 or r[3] <= 0:
                raise ValueError("рамка должна быть [x, y, w, h] в долях окна")
        return v


def preset_16_9() -> Calibration:
    """Approximate in-game top bar (portraits either side of the clock). Needs checking on a real
    screenshot: Valve moves this UI between patches."""
    w, h, step, y = 0.0300, 0.0300, 0.0326, 0.0035
    radiant = [[0.2865 + i * step, y, w, h] for i in range(5)]
    dire = [[1 - (r[0] + w), y, w, h] for r in reversed(radiant)]  # mirror around the centre
    return Calibration(radiant=radiant, dire=dire, preset=True)


def load() -> Calibration:
    if PATH.exists():
        return Calibration.model_validate_json(PATH.read_text(encoding="utf-8"))
    return preset_16_9()


def save(c: Calibration) -> Calibration:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(c.model_dump(), indent=1), encoding="utf-8")
    return c


def to_pixels(rect: Rect, width: int, height: int) -> tuple[int, int, int, int]:
    x, y, w, h = rect
    return round(x * width), round(y * height), max(1, round(w * width)), max(1, round(h * height))
