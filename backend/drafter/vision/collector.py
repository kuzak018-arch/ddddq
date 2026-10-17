"""Collects real draft frames by itself, so calibration and accuracy don't wait for screenshots.

While GSI reports hero selection (or strategy time), a frame of the Dota window is taken every
INTERVAL seconds and saved only when the top band (where picks and bans are) has changed; at
most MAX_PER_DRAFT per draft. Frames go to the wizard's snapshot folder as auto-<draft>-<n>.jpg
(JPEG 95: ~0.6 MB instead of ~3 MB, without visible artefacts), so the wizard can open them.
Frames taken during strategy time show all ten heroes: they are marked complete.

Labels come from the draft board: the final allies / enemies / bans, including the user's own
corrections after the draft. They are kept up to date while the draft and the match run and
frozen when the match ends (so clearing the board for the next game doesn't wipe them). The
board's slot order needn't match the screen's, so labels are sets per team.

The disk limit removes the oldest drafts first; the draft being collected is never removed.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from .. import config
from . import capture

SNAPSHOTS = config.DATA / "vision" / "snapshots"
DRAFTS = config.DATA / "vision" / "collected"
INTERVAL = 3.0
TOP_BAND = 0.16
PIXEL_DIFF = 25           # a pixel of the downscaled top band changed if it moved by more than this (0-255) ...
CHANGED_SHARE = 0.003     # ... and a frame is new if this share of the band changed (one new portrait is ~0.8%)
MAX_PER_DRAFT = 25
JPEG_QUALITY = 95
COMPLETE_STATES = {"DOTA_GAMERULES_STATE_STRATEGY_TIME"}


def _band(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    top = frame[: max(1, int(h * TOP_BAND))]
    return cv2.resize(cv2.cvtColor(top, cv2.COLOR_BGR2GRAY), (320, 40), interpolation=cv2.INTER_AREA).astype(np.float32)


def labels_from_session(s: dict) -> dict | None:
    """Teams as sets (lists) of hero ids from the board, by side; None if the side is unknown."""
    side = s.get("side")
    if side not in ("radiant", "dire"):
        return None
    allies = [int(h) for h in s.get("allies", []) if h]
    enemies = [int(h) for h in s.get("enemies", []) if h]
    if not allies and not enemies:
        return None
    radiant, dire = (allies, enemies) if side == "radiant" else (enemies, allies)
    return {"radiant": radiant, "dire": dire, "bans": list(s.get("bans", [])), "side": side}


def draft_path(draft_id: str) -> Path:
    return DRAFTS / f"{draft_id}.json"


def load_draft(draft_id: str) -> dict | None:
    p = draft_path(draft_id)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except ValueError:
        return None


def drafts() -> list[dict]:
    """Every collected draft, newest first."""
    if not DRAFTS.exists():
        return []
    out = [d for p in sorted(DRAFTS.glob("*.json"), reverse=True) if (d := load_draft(p.stem))]
    return out


def frame_path(snap_id: str) -> Path:
    return SNAPSHOTS / f"{snap_id}.jpg"


def used_bytes() -> int:
    return sum(p.stat().st_size for p in SNAPSHOTS.glob("auto-*.jpg")) if SNAPSHOTS.exists() else 0


def _save_draft(d: dict) -> None:
    DRAFTS.mkdir(parents=True, exist_ok=True)
    tmp = draft_path(d["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(draft_path(d["id"]))


def remove_draft(draft_id: str) -> None:
    d = load_draft(draft_id) or {}
    for f in d.get("frames", []):
        frame_path(f["id"]).unlink(missing_ok=True)
    draft_path(draft_id).unlink(missing_ok=True)


class Collector:
    def __init__(self, get_session: Callable[[], dict], get_game_state: Callable[[], str | None],
                 get_settings: Callable[[], object], on_finalize: Callable[[dict], None] | None = None):
        self.get_session, self.get_game_state, self.get_settings = get_session, get_game_state, get_settings
        self.on_finalize = on_finalize
        self.draft: dict | None = None
        self.error: str | None = None
        self._last_band: np.ndarray | None = None
        self._last_grab = 0.0
        self._last_rev = -1
        self._offered: np.ndarray | None = None   # frames from the reader, when it runs
        self._offered_at = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- lifecycle ----
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="vision-collect", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def offer(self, frame: np.ndarray) -> None:
        """A frame the screen reader already grabbed (so the window isn't captured twice)."""
        with self._lock:
            self._offered, self._offered_at = frame, time.time()

    def status(self) -> dict:
        s = self.get_settings()
        cur = self.draft and {"id": self.draft["id"], "frames": len(self.draft["frames"]),
                              "labeled": bool(self.draft.get("labels"))}
        all_drafts = drafts()
        return {"enabled": bool(getattr(s, "vision_collect", False)), "limit_mb": getattr(s, "vision_collect_mb", 0),
                "used_mb": round(used_bytes() / 1e6, 1), "drafts": len(all_drafts),
                "frames": sum(len(d.get("frames", [])) for d in all_drafts),
                "labeled_drafts": sum(1 for d in all_drafts if d.get("labels")), "current": cur, "error": self.error}

    # ---- the loop ----
    def _loop(self) -> None:
        grabber = None
        try:
            while not self._stop.is_set():
                try:
                    grabber = self.tick(grabber)
                except capture.CaptureError as e:
                    self.error = str(e)
                    if grabber:
                        grabber.stop()
                    grabber = None
                    self._stop.wait(5.0)
                except Exception as e:  # never kill the app over a frame
                    self.error = f"{type(e).__name__}: {e}"
                self._stop.wait(1.0)
        finally:
            if grabber:
                grabber.stop()

    def tick(self, grabber=None, frame: np.ndarray | None = None):
        """One step: start / continue / freeze the current draft, maybe save a frame, refresh labels.
        `frame` is for tests; otherwise the reader's latest frame or our own capture is used."""
        s = self.get_session()
        settings = self.get_settings()
        phase = s.get("phase")
        if phase == "draft":
            if self.draft is None or self.draft.get("frozen"):
                self._begin()
            if getattr(settings, "vision_collect", False) and time.time() - self._last_grab >= INTERVAL:
                if frame is None:
                    with self._lock:
                        fresh = self._offered if time.time() - self._offered_at < 2 else None
                    if fresh is not None:
                        frame = fresh
                        if grabber:
                            grabber.stop()
                            grabber = None
                    else:
                        if grabber is None or grabber.closed:
                            grabber = capture.Grabber()
                        frame = grabber.latest()
                if frame is not None:
                    self._last_grab = time.time()
                    self._consider(frame, self.get_game_state())
                    self.error = None
        elif grabber:
            grabber.stop()
            grabber = None
        if self.draft and not self.draft.get("frozen"):
            if phase == "idle":
                self._freeze()
            elif s.get("rev", 0) != self._last_rev:
                self._last_rev = s.get("rev", 0)
                if (labels := labels_from_session(s)) is not None:
                    self.draft["labels"] = {**labels, "updated": time.time()}
                    _save_draft(self.draft)
        return grabber

    def _begin(self) -> None:
        if self.draft and not self.draft.get("frozen"):
            self._freeze()
        draft_id = time.strftime("%Y%m%d-%H%M%S")
        self.draft = {"id": draft_id, "started": time.time(), "frames": [], "labels": None, "frozen": False}
        self._last_band = None
        _save_draft(self.draft)

    def _consider(self, frame: np.ndarray, game_state: str | None) -> None:
        d = self.draft
        if d is None or len(d["frames"]) >= MAX_PER_DRAFT:
            return
        band = _band(frame)
        complete = game_state in COMPLETE_STATES
        changed = self._last_band is None or float((np.abs(band - self._last_band) > PIXEL_DIFF).mean()) >= CHANGED_SHARE
        # one complete frame is always worth keeping, even if the bar looks the same
        if not changed and not (complete and not any(f.get("complete") for f in d["frames"])):
            return
        snap_id = f"auto-{d['id']}-{len(d['frames']):02d}"
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            return
        buf.tofile(str(frame_path(snap_id)))
        h, w = frame.shape[:2]
        d["frames"].append({"id": snap_id, "ts": time.time(), "state": game_state, "complete": complete,
                            "width": w, "height": h})
        self._last_band = band
        _save_draft(d)
        self._enforce_limit()

    def _freeze(self) -> None:
        d = self.draft
        if not d or d.get("frozen"):
            return
        d["frozen"] = True
        d["frozen_at"] = time.time()
        if not d["frames"]:
            remove_draft(d["id"])     # nothing captured (collection off or no window): no empty entries
            return
        _save_draft(d)
        if self.on_finalize:
            try:
                self.on_finalize(d)
            except Exception as e:
                self.error = f"после драфта: {type(e).__name__}: {e}"

    def _enforce_limit(self) -> None:
        limit = int(getattr(self.get_settings(), "vision_collect_mb", 500)) * 1_000_000
        if used_bytes() <= limit:
            return
        for d in reversed(drafts()):           # oldest first
            if self.draft and d["id"] == self.draft["id"]:
                continue
            remove_draft(d["id"])
            if used_bytes() <= limit:
                break
