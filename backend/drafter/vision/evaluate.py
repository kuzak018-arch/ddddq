"""Accuracy harness for screen reading.

A dataset is a folder of PNG frames, each with a JSON of true labels next to it:
  {"radiant": [id|null x5], "dire": [id|null x5], "bans": [id, ...]}
Real screenshots go to data/vision/labeled (the calibration wizard saves them there when you
correct and confirm a frame). `synthetic()` builds a stress set from CDN art to test the
pipeline itself — it says nothing about the real game UI, only real frames do.

precision = correct heroes / heroes the reader filled in   (what matters: wrong picks mislead)
recall    = correct heroes / heroes really on the screen    (blank slots just need typing)
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .. import config
from ..data import constants
from . import calibration, layout, matcher, reader

LABELED = config.DATA / "vision" / "labeled"
SYNTH = config.DATA / "vision" / "synthetic"
REPORT = config.REPORTS / "vision.md"
REQUIRED_PRECISION = 0.98


def _distort(img: np.ndarray, rng: np.random.Generator, ban: bool) -> np.ndarray:
    h, w = img.shape[:2]
    # the game crops portraits a little differently from the CDN art, and slots are a few px off
    dx, dy = int(w * rng.uniform(0, 0.08)), int(h * rng.uniform(0, 0.08))
    img = img[dy:h - int(h * rng.uniform(0, 0.08)), dx:w - int(w * rng.uniform(0, 0.08))]
    img = cv2.convertScaleAbs(img, alpha=rng.uniform(0.75, 1.15), beta=rng.uniform(-20, 15))
    if ban:
        grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = cv2.cvtColor((grey * 0.55).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        cv2.line(img, (0, img.shape[0] - 1), (img.shape[1] - 1, 0), (40, 40, 200), max(1, img.shape[0] // 12))
    return img


def synthetic(n_frames: int = 20, size=(2560, 1440), seed: int = 0) -> Path:
    """Frames with random heroes in the calibrated slots, plus noise / blur / JPEG artefacts."""
    rng = np.random.default_rng(seed)
    cal = layout.for_frame(*size)
    heroes = [h for h in constants.hero_index() if matcher.template_path(h["key"])]
    SYNTH.mkdir(parents=True, exist_ok=True)
    W, H = size
    for f in range(n_frames):
        frame = np.zeros((H, W, 3), np.uint8)
        frame[:] = rng.integers(10, 40, 3)
        frame = cv2.GaussianBlur(frame + rng.integers(0, 25, frame.shape, dtype=np.uint8), (0, 0), 6)
        pick = rng.choice(len(heroes), 10 + len(cal.bans), replace=False)
        labels = {"radiant": [], "dire": [], "bans": []}
        k = 0
        for group in ("radiant", "dire", "bans"):
            for rect in getattr(cal, group):
                hero = heroes[pick[k]]
                k += 1
                if group != "bans" and rng.random() < 0.2:   # still unpicked
                    labels[group].append(None)
                    continue
                x, y, w, h = calibration.to_pixels(rect, W, H)
                art = _distort(matcher._read(matcher.template_path(hero["key"])), rng, group == "bans")
                frame[y:y + h, x:x + w] = cv2.resize(art, (w, h), interpolation=cv2.INTER_AREA)
                labels[group].append(hero["id"])
        frame = cv2.GaussianBlur(frame, (0, 0), rng.uniform(0.3, 0.9))
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(55, 90))])
        frame = cv2.imdecode(jpg, cv2.IMREAD_COLOR)
        cv2.imencode(".png", frame)[1].tofile(str(SYNTH / f"synth_{f:03d}.png"))
        (SYNTH / f"synth_{f:03d}.json").write_text(json.dumps(labels))
    return SYNTH


def _limits(cal: calibration.Calibration | None) -> dict:
    c = cal or calibration.load()
    return {"threshold": c.threshold, "margin": c.margin}


def evaluate(folder: Path, cal: calibration.Calibration | None = None) -> dict:
    """Without `cal` every frame is read with the rects for its own size."""
    stats = {g: {"filled": 0, "correct": 0, "present": 0, "wrong": []} for g in ("radiant", "dire", "bans")}
    frames = sorted(folder.glob("*.png"))
    for png in frames:
        labels_path = png.with_suffix(".json")
        if not labels_path.exists():
            continue
        labels = json.loads(labels_path.read_text())
        frame = matcher._read(png)
        res = reader.read(frame, cal)
        for g in stats:
            for i, r in enumerate(res[g]):
                truth = labels[g][i] if i < len(labels[g]) else None
                if truth:
                    stats[g]["present"] += 1
                if r.hero:
                    stats[g]["filled"] += 1
                    if r.hero == truth:
                        stats[g]["correct"] += 1
                    else:
                        stats[g]["wrong"].append((png.name, i, truth, r.hero, r.score))
    tot = {k: sum(s[k] for s in stats.values()) for k in ("filled", "correct", "present")}
    precision = tot["correct"] / tot["filled"] if tot["filled"] else None
    recall = tot["correct"] / tot["present"] if tot["present"] else None
    return {"folder": str(folder), "frames": len(frames), "precision": precision, "recall": recall,
            "groups": stats, **_limits(cal)}


def write_report(results: list[dict]) -> Path:
    lines = ["# Чтение драфта с экрана: точность", "",
             f"Функцию включаем, только если точность (precision) на настоящих скриншотах ≥ {REQUIRED_PRECISION:.0%}.", ""]
    for r in results:
        p = "—" if r["precision"] is None else f"{r['precision']:.1%}"
        rc = "—" if r["recall"] is None else f"{r['recall']:.1%}"
        lines += [f"## {Path(r['folder']).name}", "",
                  f"Кадров: {r['frames']}, порог {r['threshold']}, отрыв {r['margin']}.", "",
                  "| Группа | Найдено | Верно | На экране |", "|---|---|---|---|"]
        for g, s in r["groups"].items():
            lines.append(f"| {g} | {s['filled']} | {s['correct']} | {s['present']} |")
        lines += ["", f"**Точность (precision): {p}**, полнота (recall): {rc}.", ""]
        wrong = [w for s in r["groups"].values() for w in s["wrong"]][:10]
        if wrong:
            names = constants.hero_by_id()
            lines.append("Ошибки (кадр, слот, правда → распознано, уверенность):")
            lines += [f"- {f} #{i}: {names.get(t, {}).get('name', '—')} → {names[h]['name']} ({s})" for f, i, t, h, s in wrong]
            lines.append("")
    if not any("labeled" in r["folder"] for r in results):
        lines += ["Настоящих скриншотов пока нет: синтетика проверяет только сам конвейер, "
                  "а не настоящий интерфейс игры.", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return REPORT


def evaluate_collected(cal: calibration.Calibration | None = None, draft_list: list[dict] | None = None) -> dict:
    """Accuracy on frames collected during real drafts, labelled from the draft board.

    The board's slot order needn't match the screen, so a hero read in a team's slot is right if
    that team has it (and a ban if it was banned; bans count only when the board has bans). Every
    frame counts for precision (a hero shown mid-draft is already final); recall only on complete
    frames (strategy time, all ten on screen) of drafts with full teams. Each draft is read
    without the templates learned from that same draft."""
    from . import collector
    filled = correct = present = found = frames = 0
    used_drafts = 0
    wrong = []
    for d in draft_list if draft_list is not None else collector.drafts():
        lab = d.get("labels")
        if not lab or not (lab.get("radiant") or lab.get("dire")):
            continue
        truth = {"radiant": set(lab.get("radiant") or []), "dire": set(lab.get("dire") or []),
                 "bans": set(lab.get("bans") or [])}
        full = len(truth["radiant"]) == 5 and len(truth["dire"]) == 5
        before = frames
        for f in d.get("frames", []):
            img = matcher._read(collector.frame_path(f["id"]))
            if img is None:
                continue
            frames += 1
            res = reader.read(img, cal, exclude=d["id"])
            seen = set()
            for g in ("radiant", "dire", "bans"):
                if g == "bans" and not truth["bans"]:
                    continue
                for i, r in enumerate(res[g]):
                    if not r.hero:
                        continue
                    filled += 1
                    if r.hero in truth[g]:
                        correct += 1
                        if g != "bans":
                            seen.add(r.hero)
                    else:
                        wrong.append((f["id"], g, i, r.hero, r.score))
            if f.get("complete") and full:
                present += 10
                found += len(seen)
        used_drafts += frames > before
    return {"folder": "collected", "drafts": used_drafts, "frames": frames, "filled": filled, "correct": correct,
            "precision": correct / filled if filled else None, "recall": found / present if present else None,
            "wrong": wrong[:20], **_limits(cal)}
