"""The live draft shared by every window (main, overlay) and, later, by GSI and screen reading.

Clients PUT the whole state with their own `source` id; every change is broadcast as a
"session" event, and a client ignores events carrying its own id (no echo loops).
"""

from __future__ import annotations

import threading
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..data import constants
from .events import bus

MAX_BANS = 16


class Session(BaseModel):
    allies: list[int | None] = Field(default_factory=lambda: [None] * 5)
    enemies: list[int | None] = Field(default_factory=lambda: [None] * 5)
    bans: list[int] = Field(default_factory=list, max_length=MAX_BANS)
    side: Literal["radiant", "dire"] | None = None
    pos: int | None = Field(None, ge=1, le=5)
    comfort: bool | None = None
    my_hero: int | None = None
    # idle: no match; draft: hero selection; game: match running (build mode, performance mode)
    phase: Literal["idle", "draft", "game"] = "idle"
    rev: int = 0
    source: str = ""

    @field_validator("allies", "enemies")
    @classmethod
    def five_slots(cls, v):
        if len(v) != 5:
            raise ValueError("в команде ровно 5 слотов")
        return v

    @model_validator(mode="after")
    def heroes_valid(self):
        ids = [h for h in self.allies + self.enemies + self.bans if h is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("один и тот же герой указан дважды")
        if not ids and not self.my_hero:
            return self  # nothing to check (and constants may not be on disk yet at import time)
        known = constants.hero_by_id()
        if bad := [h for h in ids + ([self.my_hero] if self.my_hero else []) if h not in known]:
            raise ValueError(f"неизвестные id героев: {bad}")
        return self


_lock = threading.Lock()
_state = Session()


def get() -> Session:
    return _state


def put(new: Session) -> Session:
    """Replace the state (from a window). rev always increases."""
    global _state
    with _lock:
        _state = new.model_copy(update={"rev": _state.rev + 1})
        snapshot = _state
    bus.publish("session", state=snapshot.model_dump())
    return snapshot


def patch(source: str, **changes) -> Session:
    """Partial update from the backend itself (GSI, screen reading). A hero that arrives in one
    slot is removed from any other slot first, so a late correction never trips validation."""
    with _lock:
        cur = _state.model_dump()
        placed = {h for k in ("allies", "enemies", "bans") if k in changes for h in changes[k] if h}
        for k in ("allies", "enemies"):
            if k not in changes:
                changes[k] = [None if h in placed else h for h in cur[k]]
        if "bans" not in changes:
            changes["bans"] = [h for h in cur["bans"] if h not in placed]
        merged = Session.model_validate({**cur, **changes, "source": source})
    return put(merged)
