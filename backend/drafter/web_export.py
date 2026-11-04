"""The data of the browser demo (GitHub Pages or a claude.ai page, app built with VITE_DEMO=1): the
draft model's numbers, so the browser computes the same chances and suggestions as the app
(app/src/demo/model.ts ports Predictor.evaluate/suggest/bans), and the answers of the read-only
pages (meta, heroes, abilities, builds, neutral items) taken from the app's own API on the seed
data. Few files (a page host may cap their number): the per-hero answers are packed by kind and
position (`pack/<name>.json` = {hero id: answer}), and the hero, item and ability icons are small
WebP data URIs in `icons/<group>.json` (no request per icon, no other host needed).

    python -m drafter.web_export OUT_DIR

Nothing personal goes out: no account, no match history, no tokens (the demo has no profile).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

R = 5  # decimals kept for the model's numbers


def _arr(a) -> list:
    return np.round(np.asarray(a, dtype=float), R).tolist()


def model_json(pr) -> dict:
    return {
        "n_ids": int(pr.n_ids),
        "S": _arr(pr.S),
        "C": _arr(pr.C),
        "hero_w": _arr(pr.hero_w),
        "hero_group_w": _arr(pr.hero_group_w),
        "intercept": float(pr.intercept),
        "cal_a": float(pr.cal_a),
        "cal_b": float(pr.cal_b),
        "pick_rate": _arr(pr.pick_rate),
        "lw": _arr(pr.lw),
        "pos_mat": _arr(pr.pos_mat),
        "positions_source": pr.positions_source,
        "names": {str(h): v["name"] for h, v in pr.heroes.items()},
    }


def counter_json() -> dict:
    """builds/counter.py against(): the rules, the enemy heroes' tags and the items they name."""
    from .builds import counter, tags
    from .data import constants
    rules = counter._rules()
    items = constants._load("items")
    keys = {k for r in rules for xs in r["items"].values() for k in xs}
    by_key = {v["key"]: h for h, v in constants.hero_by_id().items()}
    tag_table = tags.load()
    return {
        "rules": rules,
        "tags": {str(by_key[k]): v for k, v in tag_table.items() if k in by_key},
        "items": {k: {"dname": items[k]["dname"], "cost": items[k].get("cost")}
                  for k in keys if k in items and k not in constants.RETIRED_ITEMS},
        "rare_on_hero": counter.RARE_ON_HERO,
    }


ICON_WIDTH = {"heroes": 128, "items": 88, "abilities": 64}


def icons_json(icons_dir: Path, group: str) -> dict[str, str]:
    """{path as the app asks it ("/icons/items/blink.png"): data URI of a small WebP}."""
    import base64

    import cv2
    out = {}
    for f in sorted((icons_dir / group).glob("*.png")):
        img = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if img is None:
            continue
        h, w = img.shape[:2]
        width = ICON_WIDTH[group]
        if w > width:
            img = cv2.resize(img, (width, max(1, round(h * width / w))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".webp", img, [cv2.IMWRITE_WEBP_QUALITY, 82])
        if ok:
            out[f"/icons/{group}/{f.name}"] = "data:image/webp;base64," + base64.b64encode(buf.tobytes()).decode()
    return out


def export(out: Path) -> dict:
    from fastapi.testclient import TestClient

    from .api.app import app
    from .model import predictor

    out.mkdir(parents=True, exist_ok=True)
    c = TestClient(app)   # not entered: no lifespan, so no GSI server, no background jobs

    def get(path: str):
        r = c.get(path)
        r.raise_for_status()
        return r.json()

    def put(name: str, data) -> None:
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    pr = predictor.get()
    put("model.json", model_json(pr))
    put("counter.json", counter_json())
    health = get("/health")
    put("health.json", {**health, "account_id": None, "stratz": False, "demo": True})
    heroes = get("/heroes")
    put("heroes.json", heroes)
    put("settings.json", get("/settings"))
    for pos in (None, 1, 2, 3, 4, 5):
        put(f"tierlist/{pos or 'all'}.json", get(f"/meta/tierlist{f'?pos={pos}' if pos else ''}"))
    ids = [h["id"] for h in heroes["heroes"]]
    put("pack/hero.json", {h: get(f"/heroes/{h}") for h in ids})
    put("pack/abilities.json", {h: get(f"/heroes/{h}/abilities") for h in ids})
    for pos in range(1, 6):
        put(f"pack/builds_{pos}.json", {h: get(f"/builds/{h}?pos={pos}") for h in ids})

    # neutral items: what each does and how popular it is on the hero (the same for every position here)
    put("pack/neutrals.json", {h: get(f"/heroes/{h}/neutrals") for h in ids})
    from . import config
    for group in ICON_WIDTH:
        put(f"icons/{group}.json", icons_json(config.DATA / "icons", group))
    return {"heroes": len(ids), "patch": health.get("patch"), "trained": health.get("model_trained")}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("python -m drafter.web_export OUT_DIR")
    print(export(Path(sys.argv[1])))
