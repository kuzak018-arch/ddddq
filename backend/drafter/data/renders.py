"""Hero models on a transparent background, kept locally.

dota2.com shows each hero as an animated render, `/apps/dota2/videos/dota_react/heroes/renders/
<key>.webm`: VP9 with an alpha channel, the model alone. The `.png` next to it is a still WITH the
scene behind the model, which is what looked wrong in the app. So:

1. the webm is downloaded once into data/icons/renders (`video`);
2. the app (WebView2 decodes VP9 alpha) draws its first frame on a canvas and sends the PNG back
   (`save_still`): it is kept only when it really is transparent (the corners clear, the model
   opaque), together with the hero's colour for the glow;
3. a hero without a transparent render (a brand-new one, or the video missing at the CDN) gets
   the background removed here once (`segment`, GrabCut on the still with a scene, or on the
   hero's icon) and that is cached the same way, marked "segmented".
"""

from __future__ import annotations

import json
import threading

import cv2
import httpx
import numpy as np

from .. import config
from . import constants

DIR = config.DATA / "icons" / "renders"
META = DIR / "meta.json"
RENDERS = "/apps/dota2/videos/dota_react/heroes/renders"
MAX_VIDEO = 40_000_000
MAX_STILL = 12_000_000
_lock = threading.Lock()
_failed: set[str] = set()     # videos the CDN does not have: not asked again until restart


class RenderError(RuntimeError):
    pass


def _check_key(key: str) -> str:
    if not key.replace("_", "").isalnum() or key not in {h["key"] for h in constants.hero_index()}:
        raise RenderError(f"нет такого героя: {key}")
    return key


def meta() -> dict:
    try:
        return json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    except ValueError:
        return {}


def _save_meta(key: str, entry: dict) -> None:
    with _lock:
        m = meta()
        m[key] = entry
        DIR.mkdir(parents=True, exist_ok=True)
        tmp = META.with_suffix(".tmp")
        tmp.write_text(json.dumps(m, indent=1), encoding="utf-8")
        tmp.replace(META)


def info(key: str) -> dict:
    """What there is for this hero: the still (and how it was made), the video, the colour."""
    _check_key(key)
    e = meta().get(key) or {}
    return {"key": key, "still": (DIR / f"{key}.png").exists() and bool(e), "source": e.get("source"),
            "color": e.get("color"), "size": e.get("size"), "crop": e.get("crop"), "frame": e.get("frame"),
            "video": (DIR / f"{key}.webm").exists(),
            "video_missing": key in _failed}


def _get(path: str) -> httpx.Response:
    with httpx.Client(timeout=60, headers={"User-Agent": config.USER_AGENT}, follow_redirects=True) as http:
        return http.get(constants.CDN + path)


def video(key: str):
    """The cached webm, downloaded on first use; None when the CDN has none for this hero."""
    _check_key(key)
    dest = DIR / f"{key}.webm"
    if dest.exists():
        return dest
    if key in _failed:
        return None
    r = _get(f"{RENDERS}/{key}.webm")
    if not r.is_success or not r.content[:4] == b"\x1a\x45\xdf\xa3" or len(r.content) > MAX_VIDEO:
        _failed.add(key)
        return None
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    return dest


def _decode(png: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RenderError("это не картинка")
    return img


def transparent(img: np.ndarray) -> bool:
    """A real cut-out: clear corners and border, a solid model in the middle."""
    if img.ndim != 3 or img.shape[2] != 4:
        return False
    a = img[:, :, 3].astype(np.float32) / 255
    h, w = a.shape
    b = max(2, min(h, w) // 40)
    border = np.concatenate([a[:b].ravel(), a[-b:].ravel(), a[:, :b].ravel(), a[:, -b:].ravel()])
    opaque = (a > 0.9).mean()
    return float(border.mean()) < 0.03 and 0.03 < opaque < 0.9


def _trim(img: np.ndarray, pad: float = 0.02) -> tuple[np.ndarray, list[float]]:
    """Cut the empty margins around the model (a little air left). Also returns the box kept, as
    fractions of the frame [x, y, w, h]: the app places the video so its model lands on the still."""
    h, w = img.shape[:2]
    ys, xs = np.nonzero(img[:, :, 3] > 8)
    if not len(xs):
        return img, [0.0, 0.0, 1.0, 1.0]
    p = int(max(h, w) * pad)
    y0, y1 = max(0, ys.min() - p), min(h, ys.max() + p + 1)
    x0, x1 = max(0, xs.min() - p), min(w, xs.max() + p + 1)
    return img[y0:y1, x0:x1], [x0 / w, y0 / h, (x1 - x0) / w, (y1 - y0) / h]


def hero_color(img: np.ndarray) -> str:
    """The hero's colour for the glow: the most common saturated hue of the opaque pixels, averaged,
    then brightened so it glows on a dark background."""
    bgr = img[:, :, :3]
    alpha = img[:, :, 3] if img.shape[2] == 4 else np.full(img.shape[:2], 255, np.uint8)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    a = alpha.reshape(-1).astype(np.float32) / 255
    s, v = hsv[:, 1] / 255, hsv[:, 2] / 255
    wgt = a * s * v * (s > 0.25) * (v > 0.2)
    if wgt.sum() < 1:
        wgt = a
    bins = (hsv[:, 0] / 10).astype(int).clip(0, 17)
    hist = np.bincount(bins, weights=wgt, minlength=18)
    top = int(hist.argmax())
    sel = (bins == top) & (wgt > 0)
    if not sel.any():
        sel = wgt > 0
    rgb = (bgr.reshape(-1, 3)[sel].astype(np.float32) * wgt[sel, None]).sum(0) / max(wgt[sel].sum(), 1e-6)
    hsv1 = cv2.cvtColor(np.uint8([[rgb]]), cv2.COLOR_BGR2HSV)[0, 0].astype(int)
    hsv1[1] = max(hsv1[1], 150)
    hsv1[2] = max(hsv1[2], 200)
    b, g, r = cv2.cvtColor(np.uint8([[hsv1]]), cv2.COLOR_HSV2BGR)[0, 0]
    return f"#{r:02x}{g:02x}{b:02x}"


def _store(key: str, img: np.ndarray, source: str) -> dict:
    frame = [int(img.shape[1]), int(img.shape[0])]
    img, crop = _trim(img)
    ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 7])
    if not ok:
        raise RenderError("не удалось сохранить картинку")
    DIR.mkdir(parents=True, exist_ok=True)
    dest = DIR / f"{key}.png"
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(buf.tobytes())
    tmp.replace(dest)
    _save_meta(key, {"source": source, "color": hero_color(img), "size": [int(img.shape[1]), int(img.shape[0])],
                     "crop": [round(v, 5) for v in crop], "frame": frame})
    return info(key)


def save_still(key: str, png: bytes) -> dict:
    """The first frame of the render, drawn by the app: kept only if it is a real cut-out."""
    _check_key(key)
    if len(png) > MAX_STILL:
        raise RenderError("кадр слишком большой")
    img = _decode(png)
    if not transparent(img):
        raise RenderError("в кадре нет прозрачного фона")
    if img.shape[1] > 900:   # the renders are 1080p-ish: the cards need a fraction of that
        k = 900 / img.shape[1]
        img = cv2.resize(img, (900, round(img.shape[0] * k)), interpolation=cv2.INTER_AREA)
    return _store(key, img, "render")


def cut_out(img: np.ndarray) -> np.ndarray:
    """Background removal without a network model: GrabCut seeded with the border as background and
    the centre column as the model, then the mask cleaned and feathered. Returns BGRA."""
    bgr = img[:, :, :3] if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = bgr.shape[:2]
    scale = min(1.0, 640 / max(h, w))
    small = cv2.resize(bgr, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else bgr.copy()
    sh, sw = small.shape[:2]
    mask = np.full((sh, sw), cv2.GC_PR_BGD, np.uint8)
    b = max(2, sw // 30)
    mask[:b], mask[-b:], mask[:, :b], mask[:, -b:] = cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD, cv2.GC_BGD
    mask[sh // 6:sh - b, sw // 4:sw - sw // 4] = cv2.GC_PR_FGD
    mask[sh // 3:sh * 5 // 6, sw * 2 // 5:sw * 3 // 5] = cv2.GC_FGD
    bg, fg = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(small, mask, None, bg, fg, 6, cv2.GC_INIT_WITH_MASK)
    m = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    # the largest piece only, holes closed, a soft edge
    n, labels, stats, _ = cv2.connectedComponentsWithStats(m)
    if n > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        m = np.where(labels == big, 255, 0).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    m = cv2.GaussianBlur(m, (0, 0), max(1.0, w / 400))
    return np.dstack([bgr, m])


def segment(key: str) -> dict:
    """No transparent render: cut the model out of the still with a scene (or the icon) once."""
    _check_key(key)
    r = _get(f"{RENDERS}/{key}.png")
    src = None
    if r.is_success and r.headers.get("content-type", "").startswith("image"):
        src = _decode(r.content)
    if src is None:
        icon = constants.ICONS / "heroes" / f"{key}.png"
        if not icon.exists():
            raise RenderError("нет ни рендера, ни картинки героя")
        src = _decode(icon.read_bytes())
    if src.ndim == 3 and src.shape[2] == 4 and transparent(src):
        return _store(key, src, "render")     # the still turned out transparent after all
    return _store(key, cut_out(src), "segmented")
