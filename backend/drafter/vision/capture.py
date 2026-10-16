"""Capture of the Dota 2 window only (Windows Graphics Capture via `windows-capture`).

Window capture, not the monitor: our overlay sitting on top of the game is not in the frame.
WGC returns physical pixels, so Windows display scaling (125% here) does not shift the slots.
Nothing is read from the game's memory; this is the same picture the screen shows.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

import numpy as np

DOTA_TITLE = "Dota 2"

_user32 = ctypes.windll.user32
_user32.FindWindowW.restype = wintypes.HWND


class CaptureError(RuntimeError):
    pass


def find_window(title: str = DOTA_TITLE) -> int | None:
    hwnd = _user32.FindWindowW(None, title)
    return int(hwnd) if hwnd else None


def grab(title: str = DOTA_TITLE, hwnd: int | None = None, timeout: float = 3.0) -> np.ndarray:
    """One BGR frame (H, W, 3) of the window. Raises CaptureError if the window is missing or
    no frame arrives (minimised window, exclusive fullscreen)."""
    from windows_capture import Frame, InternalCaptureControl, WindowsCapture

    hwnd = hwnd or find_window(title)
    if not hwnd:
        raise CaptureError(f"окно «{title}» не найдено — Дота запущена?")
    if _user32.IsIconic(hwnd):
        raise CaptureError("окно Доты свёрнуто")
    got: dict = {}
    done = threading.Event()
    cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd)

    @cap.event
    def on_frame_arrived(frame: Frame, control: InternalCaptureControl):
        if "img" not in got:
            got["img"] = np.ascontiguousarray(frame.frame_buffer[:, :, :3])  # BGRA -> BGR
        done.set()
        control.stop()

    @cap.event
    def on_closed():
        done.set()

    control = cap.start_free_threaded()
    ok = done.wait(timeout)
    try:
        control.stop()
    except Exception:  # already stopped by the callback
        pass
    if not ok or "img" not in got:
        raise CaptureError("кадр не пришёл: Дота в эксклюзивном полноэкранном режиме или окно скрыто")
    return got["img"]


class Grabber:
    """A capture session kept open while reading the draft: frames arrive at most every
    `interval_ms`, `latest()` returns the newest one (opening a session per frame costs ~0.4 s)."""

    def __init__(self, title: str = DOTA_TITLE, interval_ms: int = 400):
        from windows_capture import Frame, InternalCaptureControl, WindowsCapture

        hwnd = find_window(title)
        if not hwnd:
            raise CaptureError(f"окно «{title}» не найдено — Дота запущена?")
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self.closed = False
        cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd,
                             minimum_update_interval=interval_ms)

        @cap.event
        def on_frame_arrived(frame: Frame, control: InternalCaptureControl):
            img = np.ascontiguousarray(frame.frame_buffer[:, :, :3])
            with self._lock:
                self._frame = img

        @cap.event
        def on_closed():
            self.closed = True

        self._control = cap.start_free_threaded()

    def latest(self) -> np.ndarray | None:
        with self._lock:
            return self._frame

    def stop(self) -> None:
        try:
            self._control.stop()
        except Exception:
            pass
        self.closed = True
