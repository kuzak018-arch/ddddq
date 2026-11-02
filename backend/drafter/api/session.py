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
from .merge import merge

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
HISTORY = 64                 # states kept by rev, to merge a window's edit made from one of them
_history: dict[int, Session] = {0: _state}
MERGED = ("allies", "enemies", "bans", "side", "pos", "comfort")


def get() -> Session:
    return _state


def put(new: Session) -> Session:
    """Replace the state (from a window). rev always increases."""
    with _lock:
        snapshot = _replace(new)
    bus.publish("session", state=snapshot.model_dump())
    return snapshot


def _replace(new: Session) -> Session:
    """Store the new state (called with _lock held)."""
    global _state
    _state = new.model_copy(update={"rev": _state.rev + 1})
    _history[_state.rev] = _state
    _history.pop(_state.rev - HISTORY, None)
    return _state


def put_from(new: Session, base_rev: int | None) -> Session:
    """A window's board, edited from the state of rev `base_rev`: what changed meanwhile elsewhere
    (screen reading, GSI) is merged in rather than overwritten (merge.py). The match phase and my
    hero belong to GSI: the window's copy of them may be stale, the backend keeps its own."""
    with _lock:
        cur = _state
        new = new.model_copy(update={"phase": cur.phase, "my_hero": cur.my_hero})
        base = _history.get(base_rev) if base_rev is not None and base_rev < cur.rev else None
        if base is not None:
            m = merge(base.model_dump(), new.model_dump(), cur.model_dump())
            new = Session.model_validate({**new.model_dump(), **{k: m[k] for k in MERGED}})
        snapshot = _replace(new)
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
        # stored under the same lock it was built under: GSI and screen reading patch from their
        # own threads, and a patch built from a state another one has just replaced would undo it
        snapshot = _replace(merged)
    bus.publish("session", state=snapshot.model_dump())
    return snapshot
