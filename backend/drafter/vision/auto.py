"""What happens after a collected draft is over, with no clicks needed:

1. calibration: if the user hasn't placed the rects by hand, fit them to a complete frame of the
   draft (autocal) - the preset is only a guess about Valve's UI;
2. templates: on that frame, each team's crops are matched to the team's five heroes (best
   one-to-one assignment) and saved as learned templates tagged with the draft, when the match is
   clear; accuracy on a draft is always measured without its own templates;
3. accuracy on everything collected and confirmed so far; the feature switches itself on when it
   is good enough (AUTO_* below), and off again if it was switched on automatically and has
   dropped below the bar since.
"""

from __future__ import annotations

import json
import time

import numpy as np
from scipy.optimize import linear_sum_assignment

from .. import config
from . import autocal, calibration, collector, evaluate, layout, matcher, reader

STATE = config.DATA / "vision" / "auto.json"
AUTO_MIN_DRAFTS = 2
AUTO_MIN_FRAMES = 10
AUTO_MIN_FILLED = 30          # heroes the reader put in: fewer can't show 98% with any confidence
LEARN_MIN_SCORE = 0.5
LEARN_MIN_GAP = 0.03          # the assigned hero must beat the crop's other options in its team by this


def state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    except ValueError:
        return {}


def _save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")


def complete_frame(d: dict) -> dict | None:
    done = [f for f in d.get("frames", []) if f.get("complete")]
    return done[-1] if done else None


def user_calibrated() -> bool:
    """The user placed (and saved) the rects by hand: never overwrite that."""
    if not calibration.PATH.exists():
        return False
    c = calibration.load()
    return not c.preset and not c.auto


KEEP_FOUND = 8               # an automatic calibration that still finds this many of the ten stays


def calibrate(d: dict) -> dict:
    lab = d.get("labels") or {}
    f = complete_frame(d)
    if not f or len(lab.get("radiant", [])) < 4 or len(lab.get("dire", [])) < 4:
        return {"done": False, "reason": "нет кадра со всеми героями или разметки составов"}
    img = matcher._read(collector.frame_path(f["id"]))
    if img is None:
        return {"done": False, "reason": "кадр не читается"}
    current = calibration.load()
    if current.auto:
        res = reader.read(img, current, exclude=d["id"])
        found = sum(1 for g in ("radiant", "dire") for r in res[g] if r.hero and r.hero in lab[g])
        if found >= KEEP_FOUND:
            return {"done": False, "kept": True, "found": found}
    cal, info = autocal.locate(img, lab["radiant"], lab["dire"])
    if cal is None:
        return {"done": False, **info}
    calibration.save(cal)
    return {"done": True, "frame": f["id"], **info}


def _team_scores(crop: np.ndarray, heroes: list[int], exclude: str) -> list[float]:
    bank = matcher.bank(crop.shape[1] / crop.shape[0], exclude)
    g, h = matcher._features(crop, bank.aspect)
    s = matcher.W_NCC * (bank.grey @ g) + matcher.W_HIST * (bank.hist @ h)
    return [float(s[bank.ids == hero].max()) if (bank.ids == hero).any() else 0.0 for hero in heroes]


def learn(d: dict, cal: calibration.Calibration | None = None) -> int:
    """Teach the matcher how these heroes look on this screen (one-to-one per team)."""
    lab = d.get("labels") or {}
    f = complete_frame(d)
    if not f:
        return 0
    img = matcher._read(collector.frame_path(f["id"]))
    if img is None:
        return 0
    crops = reader.crops(img, cal or layout.for_frame(img.shape[1], img.shape[0]))
    learned = 0
    for g in ("radiant", "dire"):
        heroes = [h for h in lab.get(g, []) if h]
        items = [c for c in crops[g] if c.size]
        if not heroes or not items:
            continue
        score = np.array([_team_scores(c, heroes, d["id"]) for c in items])
        rows, cols = linear_sum_assignment(-score)
        for i, j in zip(rows, cols):
            others = np.delete(score[i], j)
            if score[i, j] >= LEARN_MIN_SCORE and (not others.size or score[i, j] - others.max() >= LEARN_MIN_GAP):
                matcher.learn(heroes[j], items[i], tag=d["id"])
                learned += 1
    return learned


def evaluate_all() -> dict:
    """Collected drafts plus frames confirmed in the wizard, as one figure."""
    col = evaluate.evaluate_collected()
    man = None
    if evaluate.LABELED.exists() and any(evaluate.LABELED.glob("*.json")):
        man = evaluate.evaluate(evaluate.LABELED)
    m_filled = sum(g["filled"] for g in man["groups"].values()) if man else 0
    m_correct = sum(g["correct"] for g in man["groups"].values()) if man else 0
    filled, correct = col["filled"] + m_filled, col["correct"] + m_correct
    return {"collected": {k: v for k, v in col.items() if k != "wrong"}, "wrong": col["wrong"],
            "confirmed": man and {k: v for k, v in man.items() if k != "groups"},
            "drafts": col["drafts"] + (1 if man and man["frames"] else 0),
            "frames": col["frames"] + (man["frames"] if man else 0),
            "filled": filled, "correct": correct, "precision": correct / filled if filled else None,
            "required": evaluate.REQUIRED_PRECISION,
            "auto_rule": {"drafts": AUTO_MIN_DRAFTS, "frames": AUTO_MIN_FRAMES, "filled": AUTO_MIN_FILLED}}


def good_enough(ev: dict) -> bool:
    return (ev["drafts"] >= AUTO_MIN_DRAFTS and ev["frames"] >= AUTO_MIN_FRAMES and ev["filled"] >= AUTO_MIN_FILLED
            and ev["precision"] is not None and ev["precision"] >= evaluate.REQUIRED_PRECISION)


def finalize(d: dict, set_enabled, is_enabled) -> dict:
    """Run after a collected draft is frozen. set_enabled(bool) switches the feature on/off."""
    st = state()
    out: dict = {"draft": d["id"], "at": time.time()}
    if not d.get("labels"):
        out["skipped"] = "разметки нет: доска драфта не заполнялась или сторона неизвестна"
    else:
        if not user_calibrated():
            out["calibration"] = calibrate(d)
        out["learned"] = learn(d)
    ev = evaluate_all()
    out["evaluation"] = {k: ev[k] for k in ("drafts", "frames", "filled", "correct", "precision")}
    if good_enough(ev) and not is_enabled() and not st.get("manual_off"):   # never against the user's choice
        set_enabled(True)
        st.update(enabled_at=time.time(), auto_enabled=True)
        out["switched"] = "on"
    elif st.get("auto_enabled") and is_enabled() and ev["precision"] is not None \
            and ev["precision"] < evaluate.REQUIRED_PRECISION:
        set_enabled(False)
        st["auto_enabled"] = False
        out["switched"] = "off"
    st["last"] = out
    _save_state(st)
    return out
