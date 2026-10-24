"""The user's own ranked All Pick history from OpenDota and the hero pool derived from it."""

from __future__ import annotations

import json
import time

import httpx
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
        raise ValueError("не указан аккаунт: укажи Steam ID в «Настройки → Аккаунт»")
    od = OpenDota()
    try:
        profile = od.get(f"/players/{account_id}")
        # all time: the experience curve needs to know which game on a hero each match was
        matches = od.get(f"/players/{account_id}/matches", {"lobby_type": RANKED, "game_mode": ALL_PICK})
    finally:
        od.close()
    DIR.mkdir(parents=True, exist_ok=True)
    data = {"account_id": account_id, "fetched": int(time.time()), "profile": profile, "matches": matches}
    _write(DIR / "history.json", json.dumps(data, ensure_ascii=False))
    _download_avatar(profile)
    _refresh_positions(account_id)
    return data


def _write(path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


AVATAR = DIR / "avatar.jpg"
POSITIONS = DIR / "positions.json"


def _download_avatar(profile: dict) -> None:
    """The app's CSP only allows images from our backend and the hero CDN, so the Steam avatar
    (avatars.steamstatic.com) is downloaded and served locally."""
    url = (profile.get("profile") or {}).get("avatarfull")
    if not url:
        return
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": config.USER_AGENT})
        if r.is_success and r.headers.get("content-type", "").startswith("image"):
            AVATAR.write_bytes(r.content)
    except httpx.HTTPError:
        pass  # keep the previous avatar, if any


def _refresh_positions(account_id: int) -> None:
    """Position (1-5) of the user's recent matches, from Stratz (OpenDota doesn't know positions)."""
    if not config.settings().stratz_token:
        return
    from . import stratz
    try:
        sz = stratz.Stratz()
        try:
            ms = sz.q("""{ player(steamAccountId: %d) { matches(request: {take: 100}) { id players(steamAccountId: %d)
                       { position } } } }""" % (account_id, account_id))["player"]["matches"] or []
        finally:
            sz.close()
    except RuntimeError:
        return
    pos = {}
    for m in ms:
        p = (m.get("players") or [{}])[0].get("position") or ""
        if p.startswith("POSITION_"):
            pos[str(m["id"])] = int(p[-1])
    _write(POSITIONS, json.dumps(pos))


def summary(pos_mat=None, data: dict | None = None) -> dict:
    """Last 20 games, winrate by position, main heroes of the last 30 days."""
    data = data or load()
    if not data:
        return {"form": [], "positions": [], "month_heroes": []}
    ms = sorted((m for m in data["matches"] if m.get("hero_id")), key=lambda m: -m["start_time"])
    form = [{"match_id": m["match_id"], "hero": m["hero_id"], "win": _won(m), "kills": m.get("kills"),
             "deaths": m.get("deaths"), "assists": m.get("assists"), "duration": m.get("duration"),
             "start": m["start_time"]} for m in ms[:20]]
    try:
        known = json.loads(POSITIONS.read_text(encoding="utf-8")) if POSITIONS.exists() else {}
    except (OSError, ValueError):
        known = {}
    by_pos: dict[int, dict] = {}
    estimated = 0
    for m in ms[:100]:
        p = known.get(str(m["match_id"]))
        if p is None and pos_mat is not None:
            p = int(pos_mat[m["hero_id"]].argmax()) + 1   # not in Stratz: the hero's usual position
            estimated += 1
        if p is None:
            continue
        s = by_pos.setdefault(p, {"pos": p, "games": 0, "wins": 0})
        s["games"] += 1
        s["wins"] += _won(m)
    positions = [{**s, "wr": s["wins"] / s["games"]} for s in sorted(by_pos.values(), key=lambda s: s["pos"])]
    month = [m for m in ms if m["start_time"] >= time.time() - 30 * 86400]
    heroes: dict[int, dict] = {}
    for m in month:
        h = heroes.setdefault(m["hero_id"], {"hero": m["hero_id"], "games": 0, "wins": 0})
        h["games"] += 1
        h["wins"] += _won(m)
    month_heroes = sorted(({**h, "wr": h["wins"] / h["games"]} for h in heroes.values()), key=lambda h: -h["games"])[:8]
    return {"form": form, "positions": positions, "positions_estimated": estimated,
            "positions_games": min(len(ms), 100), "month_heroes": month_heroes, "month_games": len(month)}


def load() -> dict | None:
    p = DIR / "history.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except ValueError:
        return None  # broken file: as if there were no history until the next refresh


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
    if len(set(y)) < 2:
        # only wins or only losses (a new account): nothing to fit, no experience penalty
        wr = (y.mean() * len(y) + 1) / (len(y) + 2) if len(y) else 0.5
        return {"k": 5, "A": 0.0, "c": float(np.log(wr / (1 - wr))), "games": len(games)}
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


_pool_cache: dict = {}


def hero_pool(data: dict | None = None) -> dict:
    """Per hero: games, wins, the experience term and a shrunk personal skill edge — how much better
    or worse than the experience curve predicts the user does on this hero (log-odds).
    The saved history's pool is cached until the history is refreshed."""
    if data is None:
        data = load()
        key = data and (data["account_id"], data["fetched"], len(data["matches"]))
        if key and _pool_cache.get("key") == key:
            return _pool_cache["pool"]
        pool = hero_pool(data) if data else hero_pool({"matches": []})
        _pool_cache.update(key=key, pool=pool)
        return pool
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
