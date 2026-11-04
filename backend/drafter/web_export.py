"""The data of the browser demo (GitHub Pages, app built with VITE_DEMO=1): the draft model's
numbers, so the browser computes the same chances and suggestions as the app (app/src/demo/model.ts
ports Predictor.evaluate/suggest/bans), and the answers of the read-only pages (meta, heroes,
abilities, builds, neutral items) taken from the app's own API on the seed data.

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
    for h in ids:
        put(f"hero/{h}.json", get(f"/heroes/{h}"))
        put(f"abilities/{h}.json", get(f"/heroes/{h}/abilities"))
        for pos in range(1, 6):
            put(f"builds/{h}_{pos}.json", get(f"/builds/{h}?pos={pos}"))
            put(f"neutrals/{h}_{pos}.json", get(f"/heroes/{h}/neutrals?pos={pos}"))
    return {"heroes": len(ids), "patch": health.get("patch"), "trained": health.get("model_trained")}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("python -m drafter.web_export OUT_DIR")
    print(export(Path(sys.argv[1])))
