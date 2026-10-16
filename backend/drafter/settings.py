"""User settings persisted in data/settings.json (UI preferences live in the app itself)."""

from __future__ import annotations

import json
import threading

from pydantic import BaseModel, Field

from . import config

PATH = config.DATA / "settings.json"
_lock = threading.Lock()


class Settings(BaseModel):
    pos: int = Field(1, ge=1, le=5, description="моя позиция по умолчанию")
    use_comfort: bool = Field(True, description="учитывать мой опыт на героях")
    comfort_weight: float = Field(0.5, ge=0, le=1)
    rank_tier: int | None = Field(None, ge=11, le=80, description="переопределить ранг (иначе из профиля)")
    tier_days: int = Field(14, ge=1, le=60, description="за сколько дней тир-лист")
    vision_enabled: bool = Field(False, description="читать драфт с экрана (экспериментально)")


def load() -> Settings:
    with _lock:
        if PATH.exists():
            try:
                return Settings.model_validate_json(PATH.read_text(encoding="utf-8"))
            except ValueError:
                pass  # corrupted or old format: fall back to defaults
        return Settings()


def save(s: Settings) -> Settings:
    with _lock:
        PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(s.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(PATH)
    return s
