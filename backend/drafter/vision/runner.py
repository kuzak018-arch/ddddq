"""Background loop: while hero selection is on (GSI phase "draft") and the feature is enabled,
read the draft from the Dota window and fill the shared session.

Rules that keep it from getting in the way:
  - a slot changes only after the same hero is read in 2 frames in a row (3 while cautious); a slot
    the reader filled itself is replaced when 2 frames more read another hero;
  - one hero, one slot: a frame that reads the same hero twice keeps only the better read;
  - the board follows the screen's order: a hero that Dota (GSI: my own hero, the draft block) put
    into another slot of the same team moves to the slot it is seen in; nothing is removed that the
    reader did not put there;
  - manual edits win: a slot the user changed (it no longer holds what the reader put there)
    is locked until the next match;
  - the slots found by the colour bars are kept for the session: a frame where the bars are covered
    is read with the last ones, not with a stored layout;
  - my own hero (GSI) that no template recognises (a persona, a redrawn portrait) is placed by
    elimination once the four other allies are read, and that portrait is learned;
  - Radiant/Dire are mapped to my team / enemies only when my side is known (GSI or chosen);
  - nothing is captured outside hero selection.
"""

from __future__ import annotations

import dataclasses
import threading
import time

from . import bars, calibration, capture, layout, matcher, reader

INTERVAL = 0.7
STABLE_FRAMES = 2
# until the accuracy on the user's own drafts is proven: only confident reads, and one frame more
CAUTIOUS_THRESHOLD = 0.62
CAUTIOUS_MARGIN = 0.10
# with the slots found by the players' colour bars the crops sit exactly on the portraits. Measured
# on the user's frames: right heroes score 0.59-0.90 and lead by 0.10 or more; a portrait without a
# template (a persona, an old art) scores about 0.5 with a lead below 0.08
BARS_THRESHOLD = 0.55
BARS_MARGIN = 0.08
CORRECT_EXTRA = 2   # frames more than a first fill that a different hero must be read to replace the reader's own pick
ME_FRAMES = 3       # frames in a row my hero's slot must be the only unread one before it is placed by elimination


def unique(res: dict) -> dict:
    """One hero, one slot: when a frame reads the same hero in several slots (look-alike portraits),
    only the best-scoring read stays; the others become unread."""
    best: dict[int, tuple[str, int, float]] = {}
    for g in ("radiant", "dire", "bans"):
        for i, r in enumerate(res.get(g, [])):
            if r.hero and (r.hero not in best or r.score > best[r.hero][2]):
                best[r.hero] = (g, i, r.score)
    out = dict(res)
    for g in ("radiant", "dire", "bans"):
        out[g] = [dataclasses.replace(r, hero=None) if r.hero and best[r.hero][:2] != (g, i) else r
                  for i, r in enumerate(res.get(g, []))]
    return out


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
        self.bars_seen: dict[tuple[int, int], calibration.Calibration] = {}   # frame size -> slots last found by the bars
        self._last_cal: calibration.Calibration | None = None
        self._reset_match(None)

    def _reset_match(self, match_key):
        self.match_key = match_key
        self.applied: dict[tuple[str, int], int] = {}   # slot -> hero this runner put there
        self.locked: set[tuple[str, int]] = set()      # slots the user edited by hand
        self.pending: dict[tuple[str, int], tuple[int, int]] = {}  # slot -> (hero, frames seen)
        self.me_seen = 0        # frames in a row my hero's screen slot was found by elimination
        self.me_learned = False

    def reset_learning(self) -> None:
        """After «Сбросить обучение»: forget the slots seen and start cautious again."""
        self.bars_seen.clear()
        self.autofit = layout.AutoFit()
        self.cautious = True
        self._reset_match(self.match_key)

    def status(self) -> dict:
        return {"enabled": self.enabled, "running": bool(self._thread and self._thread.is_alive()),
                "error": self.error, "last_read": self.last_read, "locked": len(self.locked),
                "source": (self.last_result or {}).get("source"), "fit": self.autofit.last_info,
                "cautious": self.cautious}

    def _read(self, frame):
        h, w = frame.shape[:2]
        found = bars.find(frame)
        if found is not None:
            self.bars_seen[(w, h)] = found
        elif (w, h) in self.bars_seen:
            # the bars are covered on this frame (a tooltip, an animation): the slots haven't moved
            found = self.bars_seen[(w, h)].model_copy(update={"source": "bars-kept"})
        if found is not None:
            # the slots themselves, from the colour bars: no fitting, no profile, any resolution
            cal = found.model_copy(update={"threshold": BARS_THRESHOLD, "margin": BARS_MARGIN})
        else:
            cal = layout.for_frame(w, h)
            if self.cautious:
                cal = cal.model_copy(update={"threshold": max(cal.threshold, CAUTIOUS_THRESHOLD),
                                             "margin": max(cal.margin, CAUTIOUS_MARGIN)})
        self._last_cal = cal
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
        if cal is not None:
            self._last_cal = cal
            res = reader.read(frame, cal)
        else:
            res = self._read(frame)
            if self.autofit.offer(frame, res["source"]) and self.autofit.last_info.get("saved"):
                res = self._read(frame)             # read again with the rects just found
        res = unique(res)
        stable = STABLE_FRAMES + (1 if self.cautious else 0)
        self.last_read, self.last_result = time.time(), reader.as_json(res)
        self.publish({"status": self.status(), "result": self.last_result})
        side = s.get("side")
        if not side:
            return None   # can't tell which team is mine yet
        mine, theirs = ("radiant", "dire") if side == "radiant" else ("dire", "radiant")
        boards = {"allies": list(s["allies"]), "enemies": list(s["enemies"])}
        bans = list(s["bans"])
        me = s.get("my_hero")
        changed: set[str] = set()
        for team_key, group in (("allies", mine), ("enemies", theirs)):
            board = boards[team_key]
            for i, r in enumerate(res[group]):
                key = (group, i)
                if key in self.applied and board[i] != self.applied[key]:
                    self.locked.add(key)          # the user replaced or cleared what we put
                if key in self.locked or not r.hero:
                    continue
                hero, seen = self.pending.get(key, (None, 0))
                seen = seen + 1 if hero == r.hero else 1
                self.pending[key] = (r.hero, seen)
                if board[i] == r.hero or seen < (stable if board[i] is None else stable + CORRECT_EXTRA):
                    continue
                if self._place(boards, bans, team_key, group, i, r.hero, me):
                    changed.add(team_key)
        if self._place_me(res, frame, boards, mine, me):
            changed.add("allies")
        changes = {k: boards[k] for k in changed}
        new_bans = []
        for i, r in enumerate(res["bans"]):
            if not r.hero:
                continue
            hero, seen = self.pending.get(("bans", i), (None, 0))
            seen = seen + 1 if hero == r.hero else 1
            self.pending[("bans", i)] = (r.hero, seen)
            on_board = boards["allies"] + boards["enemies"]
            if seen >= stable and r.hero not in bans + on_board and r.hero not in new_bans:
                new_bans.append(r.hero)
        if new_bans:
            changes["bans"] = (bans + new_bans)[:16]
        if changes:
            self.patch(**changes)
        return changes or None

    def _place(self, boards: dict, bans: list, team_key: str, group: str, i: int, hero: int, me: int | None) -> bool:
        """Put `hero` into screen slot i of this team's board unless that removes something the
        reader didn't put there. The same hero in another slot of this team moves here (the board
        follows the screen's order); in the other team or the bans it stays: that conflict is sorted
        out when its own slot is read differently."""
        board = boards[team_key]
        other = boards["enemies" if team_key == "allies" else "allies"]
        if hero in other or hero in bans:
            return False
        j = board.index(hero) if hero in board else None
        if j is not None and (group, j) in self.locked:
            return False
        occupant = board[i]
        if occupant is not None and self.applied.get((group, i)) != occupant:
            # not the reader's own pick: only my hero may make room (GSI puts it into the first free
            # slot, wherever it is on the screen); anything else the user typed stays
            if occupant != me:
                return False
            free = [k for k, h in enumerate(board) if h is None and (group, k) not in self.locked]
            if j is not None:
                board[j] = occupant              # swap
                self.applied.pop((group, j), None)
            elif free:
                board[free[0]] = occupant
            else:
                return False
        elif j is not None:
            board[j] = None
            self.applied.pop((group, j), None)
        board[i] = hero
        self.applied[(group, i)] = hero
        return True

    def _place_me(self, res: dict, frame, boards: dict, mine: str, me: int | None) -> bool:
        """My hero (GSI knows it) on a portrait no template knows: when it is the only unread
        portrait of my team for ME_FRAMES frames, that slot is mine. The crop is learned, so from
        the next draft on the portrait is read like any other."""
        if not me or any(r.hero == me for r in res[mine]):
            self.me_seen = 0
            return False
        unread = [i for i, r in enumerate(res[mine]) if not r.hero and not r.empty]
        read = [r for r in res[mine] if r.hero]
        if len(unread) != 1 or len(read) != 4:
            self.me_seen = 0
            return False
        self.me_seen += 1
        if self.me_seen < ME_FRAMES:
            return False
        k = unread[0]
        board = boards["allies"]
        key = (mine, k)
        if key in self.locked or (board[k] is not None and board[k] != me):
            return False
        changed = board[k] != me
        if me in board:
            board[board.index(me)] = None
        board[k] = me
        self.applied[key] = me
        if not self.me_learned and self._last_cal is not None:
            crop = reader.crops(frame, self._last_cal)[mine][k]
            if crop.size:
                try:
                    self.me_learned = matcher.learn(me, crop) is not None
                except (OSError, ValueError):
                    pass
        return changed

    def new_match(self, match_key) -> None:
        if match_key != self.match_key:
            self._reset_match(match_key)
