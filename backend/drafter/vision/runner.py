"""Background loop: while hero selection is on (GSI phase "draft") and the feature is enabled,
read the draft from the Dota window and fill the shared session.

Rules that keep it from getting in the way:
  - a slot changes only after the same hero is read in 2 frames in a row (3 while cautious); a slot
    the reader filled itself is replaced when 2 frames more read another hero;
  - manual edits win: a slot the user changed (it no longer holds what the reader put there)
    is locked until the next match;
  - Radiant/Dire are mapped to my team / enemies only when my side is known (GSI or chosen);
  - nothing is captured outside hero selection.
"""

from __future__ import annotations

import threading
import time

from . import bars, calibration, capture, layout, reader

INTERVAL = 0.7
STABLE_FRAMES = 2
# until the accuracy on the user's own drafts is proven: only confident reads, and one frame more
CAUTIOUS_THRESHOLD = 0.62
CAUTIOUS_MARGIN = 0.10
# with the slots found by the players' colour bars the crops sit exactly on the portraits, and the
# right hero scores lower in absolute terms (a portrait cut by the bar's slant) but leads clearly
BARS_THRESHOLD = 0.5
BARS_MARGIN = 0.08
CORRECT_EXTRA = 2   # frames more than a first fill that a different hero must be read to replace the reader's own pick


class Runner:
    def __init__(self, get_session, patch_session, publish):
        self.get_session, self.patch, self.publish = get_session, patch_session, publish
        self.enabled = False
        self.error: str | None = None
        self.last_read: float | None = None
        self.last_result: dict | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.on_frame = None   # the frame collector takes our frames instead of capturing the window twice
        self.autofit = layout.AutoFit()   # no calibration: fit the built-in layout to the first good frames
        self.cautious = True              # accuracy not proven yet (auto.finalize says when it is)
        self._reset_match(None)

    def _reset_match(self, match_key):
        self.match_key = match_key
        self.applied: dict[tuple[str, int], int] = {}   # slot -> hero this runner put there
        self.locked: set[tuple[str, int]] = set()      # slots the user edited by hand
        self.pending: dict[tuple[str, int], tuple[int, int]] = {}  # slot -> (hero, frames seen)

    def status(self) -> dict:
        return {"enabled": self.enabled, "running": bool(self._thread and self._thread.is_alive()),
                "error": self.error, "last_read": self.last_read, "locked": len(self.locked),
                "source": (self.last_result or {}).get("source"), "fit": self.autofit.last_info,
                "cautious": self.cautious}

    def _read(self, frame):
        h, w = frame.shape[:2]
        found = bars.find(frame)
        if found is not None:
            # the slots themselves, from the colour bars: no fitting, no profile, any resolution
            if self.cautious:
                found = found.model_copy(update={"threshold": BARS_THRESHOLD, "margin": BARS_MARGIN})
            return reader.read(frame, found)
        cal = layout.for_frame(w, h)
        if self.cautious:
            cal = cal.model_copy(update={"threshold": max(cal.threshold, CAUTIOUS_THRESHOLD),
                                         "margin": max(cal.margin, CAUTIOUS_MARGIN)})
        return reader.read(frame, cal)

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        if on and not (self._thread and self._thread.is_alive()):
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="vision", daemon=True)
            self._thread.start()
        if not on:
            self._stop.set()

    def _loop(self):
        grabber = None
        try:
            while not self._stop.is_set():
                s = self.get_session()
                if s["phase"] != "draft":
                    if grabber:
                        grabber.stop()
                        grabber = None
                    self._stop.wait(1.0)
                    continue
                try:
                    if grabber is None or grabber.closed:
                        grabber = capture.Grabber()
                    frame = grabber.latest()
                    if frame is not None:
                        if self.on_frame:
                            self.on_frame(frame)
                        self.step(frame, s)
                        self.error = None
                except capture.CaptureError as e:
                    self.error = str(e)
                    grabber = None
                    self._stop.wait(3.0)
                except Exception as e:  # noqa: BLE001 - one bad frame must not end screen reading for the session
                    self.error = f"{type(e).__name__}: {e}"
                    if grabber:
                        try:
                            grabber.stop()
                        except Exception:  # noqa: BLE001
                            pass
                    grabber = None
                    self._stop.wait(3.0)
                self._stop.wait(INTERVAL)
        finally:
            if grabber:
                grabber.stop()

    def step(self, frame, s: dict, cal: calibration.Calibration | None = None) -> dict | None:
        """Read one frame and apply stable, non-conflicting results. Returns the applied changes."""
        res = reader.read(frame, cal) if cal is not None else self._read(frame)
        if cal is None and self.autofit.offer(frame, res["source"]) and self.autofit.last_info.get("saved"):
            res = self._read(frame)             # read again with the rects just found
        stable = STABLE_FRAMES + (1 if self.cautious else 0)
        self.last_read, self.last_result = time.time(), reader.as_json(res)
        self.publish({"status": self.status(), "result": self.last_result})
        side = s.get("side")
        if not side:
            return None   # can't tell which team is mine yet
        mine, theirs = ("radiant", "dire") if side == "radiant" else ("dire", "radiant")
        changes: dict = {}
        placed: set[int] = set()   # heroes put in this step: one hero is never put in two places
        for team_key, group in (("allies", mine), ("enemies", theirs)):
            slots = list(s[team_key])
            changed = False
            for i, r in enumerate(res[group]):
                key = (group, i)
                if key in self.applied and slots[i] != self.applied[key]:
                    self.locked.add(key)          # the user replaced or cleared what we put
                if key in self.locked or not r.hero:
                    continue
                hero, seen = self.pending.get(key, (None, 0))
                seen = seen + 1 if hero == r.hero else 1
                self.pending[key] = (r.hero, seen)
                taken = (r.hero in (s["allies"] + s["enemies"] + s["bans"]) and slots[i] != r.hero) or r.hero in placed
                # a slot the reader filled itself is corrected when later frames keep reading another hero
                # (an early misread of a half-drawn portrait must not stay for the whole draft)
                mine_still = slots[i] is not None and self.applied.get(key) == slots[i] and r.hero != slots[i]
                if not taken and ((seen >= stable and slots[i] is None) or (seen >= stable + CORRECT_EXTRA and mine_still)):
                    slots[i] = r.hero
                    self.applied[key] = r.hero
                    placed.add(r.hero)
                    changed = True
            if changed:
                changes[team_key] = slots
        new_bans = []
        for i, r in enumerate(res["bans"]):
            if not r.hero:
                continue
            hero, seen = self.pending.get(("bans", i), (None, 0))
            seen = seen + 1 if hero == r.hero else 1
            self.pending[("bans", i)] = (r.hero, seen)
            if seen >= stable and r.hero not in s["bans"] + s["allies"] + s["enemies"] and r.hero not in placed:
                new_bans.append(r.hero)
                placed.add(r.hero)
        if new_bans:
            changes["bans"] = (s["bans"] + new_bans)[:16]
        if changes:
            self.patch(**changes)
        return changes or None

    def new_match(self, match_key) -> None:
        if match_key != self.match_key:
            self._reset_match(match_key)
