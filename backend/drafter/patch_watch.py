"""Has Dota got a newer patch than the app's data? Checked against Valve's patch list.

The app's data (constants, item and ability lists, the trained model, Stratz builds) belong to the
patch they were refreshed on: the last entry of data/constants/patches.json. A background thread
asks Valve's public patch list every CHECK_EVERY (the first time shortly after the start) and
keeps the answer in data/patch_watch.json. The UI shows a banner while the data is behind, with
one button to the usual refresh job; the model is retrained only once the new patch has enough
matches (refresh.MIN_MATCHES_TO_TRAIN), so «модель с прошлого патча» is said separately.
"""

from __future__ import annotations

import json
import threading
import time

import httpx

from . import config
from .data import constants

PATH = config.DATA / "patch_watch.json"
CHECK_EVERY = 6 * 3600
FIRST_AFTER = 60
_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PATH)


def check(http: httpx.Client | None = None, now: float | None = None) -> dict:
    """Ask Valve for the newest patch and remember it (errors are remembered too)."""
    now = now or time.time()
    own = http is None
    http = http or httpx.Client(timeout=20, headers={"User-Agent": config.USER_AGENT})
    try:
        patches = constants.fetch_patches(http)
        last = max(patches, key=lambda p: p["ts"])
        d = {"latest": last, "checked": now, "error": None}
    except (httpx.HTTPError, ValueError, KeyError) as e:
        d = {**_load(), "checked": now, "error": f"не удалось проверить патч: {e.__class__.__name__}"}
    finally:
        if own:
            http.close()
    with _lock:
        _save(d)
    return d


def _model_patch() -> str | None:
    from .model import train
    try:
        return json.loads((train.ART / "meta.json").read_text(encoding="utf-8")).get("patch")
    except (OSError, ValueError, AttributeError):
        return None


def status() -> dict:
    """{latest, data_patch, model_patch, behind, model_behind, checked, error}."""
    d = _load()
    try:
        data = constants.current_patch()
    except (FileNotFoundError, ValueError, IndexError, KeyError):
        data = None
    latest = d.get("latest")
    model = _model_patch()
    behind = bool(latest and data and latest["ts"] > data["ts"] and latest["name"] != data["name"])
    return {"latest": latest, "data_patch": data["name"] if data else None, "model_patch": model,
            "behind": behind, "model_behind": bool(model and data and model != data["name"]),
            "checked": d.get("checked"), "error": d.get("error")}


def start(publish=None) -> None:
    """The background check: soon after the start, then every CHECK_EVERY; a newer patch is published
    to the UI (`publish("patch", **status)`) the moment it is seen."""
    def loop():
        time.sleep(FIRST_AFTER)
        while True:
            if time.time() - (_load().get("checked") or 0) >= CHECK_EVERY - 60:
                check()
                st = status()
                if publish and st["behind"]:
                    publish("patch", **st)
            time.sleep(600)
    threading.Thread(target=loop, name="patch-watch", daemon=True).start()
