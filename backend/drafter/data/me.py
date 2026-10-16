"""The user's own ranked All Pick history from OpenDota and the hero pool derived from it."""

from __future__ import annotations

import json
import time

import numpy as np
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

from .. import config
from .http import OpenDota
from .matches import ALL_PICK, RANKED

DIR = config.DATA / "me"
PRIOR_GAMES = 10  # comfort winrate is shrunk toward the player's overall winrate by this many games


def refresh(account_id: int | None = None) -> dict:
    account_id = account_id or config.settings().account_id
    if not account_id:
        raise ValueError("нет DOTA_ACCOUNT_ID в .env")
    od = OpenDota()
    try:
        profile = od.get(f"/players/{account_id}")
        # all time: the experience curve needs to know which game on a hero each match was
        matches = od.get(f"/players/{account_id}/matches", {"lobby_type": RANKED, "game_mode": ALL_PICK})
    finally:
        od.close()
    DIR.mkdir(parents=True, exist_ok=True)
    data = {"account_id": account_id, "fetched": int(time.time()), "profile": profile, "matches": matches}
    (DIR / "history.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def load() -> dict | None:
    p = DIR / "history.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _won(m: dict) -> bool:
    return (m["player_slot"] < 128) == m["radiant_win"]


def _games_in_order(data: dict) -> list[tuple[int, int, bool]]:
    """(hero_id, how many earlier games on this hero, won) in chronological order."""
    seen: dict[int, int] = {}
    out = []
    for m in sorted((m for m in data["matches"] if m.get("hero_id")), key=lambda m: m["start_time"]):
        n = seen.get(m["hero_id"], 0)
        out.append((m["hero_id"], n, _won(m)))
        seen[m["hero_id"]] = n + 1
    return out


def fit_experience(data: dict | None = None) -> dict:
    """Experience curve from the user's own games: logit P(win) = c - A * k / (k + n),
    n = earlier games on that hero. A (the first-game penalty) and k (how fast it fades)
    are fitted by maximum likelihood; k by grid search."""
    data = data or load()
    games = _games_in_order(data)
    n = np.array([g[1] for g in games], dtype=float)
    y = np.array([g[2] for g in games], dtype=float)
    best = None
    for k in (1, 2, 3, 5, 8, 12, 20, 30):
        x = (k / (k + n)).reshape(-1, 1)
        lr = LogisticRegression(C=1e6).fit(x, y)
        ll = -log_loss(y, lr.predict_proba(x)[:, 1], normalize=False)
        if best is None or ll > best[0]:
            best = (ll, k, float(-lr.coef_[0][0]), float(lr.intercept_[0]))
    _, k, A, c = best
    return {"k": k, "A": max(A, 0.0), "c": c, "games": len(games)}


def experience_term(n: int, exp: dict) -> float:
    """Log-odds change from having played the hero n times before (0 for a well-practised hero)."""
    return -exp["A"] * exp["k"] / (exp["k"] + n)


def hero_pool(data: dict | None = None) -> dict:
    """Per hero: games, wins, the experience term and a shrunk personal skill edge — how much better
    or worse than the experience curve predicts the user does on this hero (log-odds)."""
    data = data or load()
    if not data or not data["matches"]:
        return {"overall": None, "experience": None, "heroes": {}}
    exp = fit_experience(data)
    heroes: dict[int, dict] = {}
    for hid, n, won in _games_in_order(data):
        h = heroes.setdefault(hid, {"games": 0, "wins": 0, "expected": 0.0})
        h["games"] += 1
        h["wins"] += won
        h["expected"] += float(expit(exp["c"] + experience_term(n, exp)))
    for h in heroes.values():
        # residual wins beyond the curve, shrunk by PRIOR_GAMES; /0.25 turns probability into log-odds near 50%
        h["edge"] = (h["wins"] - h["expected"]) / (h["games"] + PRIOR_GAMES) / 0.25
        h["experience"] = experience_term(h["games"], exp)
    wins = sum(h["wins"] for h in heroes.values())
    games = sum(h["games"] for h in heroes.values())
    return {"overall": {"games": games, "wins": wins, "wr": wins / games}, "experience": exp, "heroes": heroes}


def rank_tier(data: dict | None = None) -> int | None:
    data = data or load()
    return (data or {}).get("profile", {}).get("rank_tier")
