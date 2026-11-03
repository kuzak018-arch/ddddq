"""One clean start of screen reading after an update from an older version.

Versions before 1.2.5 kept what screen reading had learned forever: portraits saved under a hero
(some of them by self-learning loops removed in 1.2.3, or a placeholder slot filed under the
user's hero), the slot rects of an older Dota layout, the frames collected for its accuracy. One
wrong portrait wins for every look-alike slot afterwards («везде виспы»). The hero art shipped
with the program reads the user's frames 9–10 of 10 by itself, so on the first start of a newer
format all of it goes, once:
  - learned portraits are moved to vision/learned-old (a backup, the previous backup replaced);
  - the saved calibration is moved next to it (calibration-old.json);
  - collected drafts, automatic snapshots, detected fits and the accuracy record are deleted.
Frames the user confirmed in the wizard (labeled) and the on/off choice stay.
"""

from __future__ import annotations

import json
import shutil
import time

from .. import config

FORMAT = 2
DIR = config.DATA / "vision"
MARK = DIR / "format.json"


def version() -> int:
    try:
        return int(json.loads(MARK.read_text(encoding="utf-8")).get("format") or 0)
    except (OSError, ValueError, AttributeError):
        return 0


def _mark() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    MARK.write_text(json.dumps({"format": FORMAT, "at": int(time.time())}), encoding="utf-8")


def run() -> dict | None:
    """Clean the old learning once; None when already done. Returns what was removed."""
    if version() >= FORMAT:
        return None
    from . import auto, calibration, collector, layout, matcher
    out = {"learned": 0, "collected": 0, "calibration": False}
    if not DIR.exists():          # a new install: nothing learned yet
        _mark()
        return out
    learned = matcher.LEARNED
    if learned.exists():
        out["learned"] = sum(1 for _ in learned.rglob("*.png"))
        backup = DIR / "learned-old"
        shutil.rmtree(backup, ignore_errors=True)
        if out["learned"]:
            shutil.move(str(learned), str(backup))
        else:
            shutil.rmtree(learned, ignore_errors=True)
    if calibration.PATH.exists():
        calibration.PATH.replace(DIR / "calibration-old.json")
        out["calibration"] = True
    if collector.DRAFTS.exists():
        out["collected"] = sum(1 for p in collector.DRAFTS.rglob("*") if p.is_file())
        shutil.rmtree(collector.DRAFTS, ignore_errors=True)
    for p in collector.SNAPSHOTS.glob("auto-*.jpg") if collector.SNAPSHOTS.exists() else []:
        p.unlink(missing_ok=True)
    layout.forget_fits()
    auto._save_state({k: v for k, v in auto.state().items() if k == "manual_off"})
    matcher.reload()
    _mark()
    return out
