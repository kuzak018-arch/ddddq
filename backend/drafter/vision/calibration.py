"""Where the hero portraits are on the draft screen.

Rects are stored as fractions of the window size [x, y, w, h], so one calibration works for any
resolution with the same aspect ratio. Without a calibration the rects come from the built-in
layout for the frame's size (layout.py); the wizard lets the user drag them by hand as a fallback.
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
    auto: bool = Field(False, description="рамки найдены автоматически по кадру с известными героями")
    source: str = Field("manual", description="откуда рамки: manual, auto, detected, profile, from-manual, from-auto")

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
    """The built-in rects for 16:9 (see layout.py: one layout for every resolution)."""
    from . import layout
    return layout.profile(1920, 1080)


def load() -> Calibration:
    """The saved rects, or the built-in 16:9 ones. The reader uses layout.for_frame instead, which
    picks the rects for the frame's own size."""
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
