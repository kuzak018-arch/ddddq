"""Capture of the Dota 2 window only (Windows Graphics Capture via `windows-capture`).

Window capture, not the monitor: our overlay sitting on top of the game is not in the frame.
WGC returns physical pixels, so Windows display scaling (100-175%) does not shift the slots. In
windowed mode the frame also holds the title bar and the borders: they are cut off (client area
from Windows, in the same physical pixels), so the frame is exactly what Dota draws, in any mode.
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


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def client_crop(window: tuple[int, int, int, int], client: tuple[int, int, int, int], frame_w: int, frame_h: int):
    """(x, y, w, h) of the client area inside a captured frame, or None when the frame is the
    client area already (borderless, fullscreen). window: the visible window bounds (l, t, r, b);
    client: its client area (l, t, r, b), both in screen pixels; the frame may be scaled."""
    wl, wt, wr, wb = window
    cl, ct, cr, cb = client
    if wr <= wl or wb <= wt or cr <= cl or cb <= ct:
        return None
    sx, sy = frame_w / (wr - wl), frame_h / (wb - wt)
    x, y = round((cl - wl) * sx), round((ct - wt) * sy)
    w, h = round((cr - cl) * sx), round((cb - ct) * sy)
    x, y = max(0, x), max(0, y)
    w, h = min(w, frame_w - x), min(h, frame_h - y)
    if w < frame_w * 0.5 or h < frame_h * 0.5:
        return None          # nonsense (minimised, mid-resize): keep the whole frame
    if x <= 1 and y <= 1 and w >= frame_w - 2 and h >= frame_h - 2:
        return None
    return x, y, w, h


def _client_box(hwnd: int, frame_w: int, frame_h: int):
    """The client area of the window in this frame (see client_crop). Asked per-monitor DPI aware,
    so the rects are physical pixels like the frame."""
    try:
        _user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        old = _user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))   # PER_MONITOR_AWARE_V2
    except AttributeError:
        old = None
    try:
        win, cr, pt = _RECT(), _RECT(), _POINT(0, 0)
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), 9, ctypes.byref(win), ctypes.sizeof(win)) != 0:
            if not _user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(win)):
                return None
        if not _user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(cr)) or \
                not _user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt)):
            return None
        return client_crop((win.left, win.top, win.right, win.bottom), (pt.x, pt.y, pt.x + cr.right, pt.y + cr.bottom),
                           frame_w, frame_h)
    except Exception:   # never let this break capturing: the whole frame is the old behaviour
        return None
    finally:
        if old:
            _user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(old))


def _cut(img: np.ndarray, hwnd: int) -> np.ndarray:
    box = _client_box(hwnd, img.shape[1], img.shape[0])
    if not box:
        return img
    x, y, w, h = box
    return np.ascontiguousarray(img[y:y + h, x:x + w])


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
    return _cut(got["img"], hwnd)


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
        self._hwnd = hwnd
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
            img = self._frame
        return None if img is None else _cut(img, self._hwnd)

    def stop(self) -> None:
        try:
            self._control.stop()
        except Exception:
            pass
        self.closed = True
