"""«Игры топов»: recent matches of one hero by Immortal / Divine+ players (Stratz) and by pros
(OpenDota), current patch only, with everything the tab shows per match.

Stratz has no «matches of a hero» list and `matches(ids)` is admin-only, so the matches come from the
hero's leaderboard: its top players by bracket (`leaderboard.hero`), then each player's recent
matches on the hero (`player.matches`), several matches per request with all their players. Pro
matches come from OpenDota (`/heroes/{id}/matches`, then `/matches/{id}`: pro matches are parsed
there). Results go to data/topgames/<source>/<hero>.json as they arrive, so the tab fills up while
loading and opening it again is instant; a list older than REFRESH_AFTER is refreshed in the
background. Nothing here looks at the user's current match.

Field names beyond those the app already uses (match players' kills, net worth, per-minute curves,
final items) are not checked against Stratz's live schema from here, so they come in optional
groups: if Stratz rejects a field, the query is sent again without its group.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from . import config
from .data import constants, stratz
from .data.constants import _load as load_const
from .data.http import OpenDota, RateLimited

SOURCES = {
    "immortal": {"brackets": ["IMMORTAL"], "min_rank": 80, "label": "Immortal"},
    "divine": {"brackets": ["DIVINE", "IMMORTAL"], "min_rank": 70, "label": "Divine+"},
    "pro": {"label": "Про-матчи"},
}
TARGET = 60                 # matches per hero and source
STRATZ_MAX_REQUESTS = 16    # one leaderboard + players
MATCHES_PER_PLAYER = 6
PRO_MAX_DETAILS = 24
REFRESH_AFTER = 6 * 3600
BUDGET_FLOOR = 60           # Stratz requests per hour left to the rest of the app

ROOT = config.DATA / "topgames"

# Stratz query parts: the core is what the app already fetches per match (lane and build data);
# the groups are optional (see the module's doc)
_CORE_PLAYER = "heroId steamAccountId isVictory position stats { itemPurchases { time itemId } } abilities { abilityId time level }"
_GROUPS: dict[str, tuple[str, str]] = {
    # name: (where, fields)
    "score": ("player", "isRadiant kills deaths assists numLastHits numDenies goldPerMinute experiencePerMinute networth heroDamage"),
    "final": ("player", "item0Id item1Id item2Id item3Id item4Id item5Id neutral0Id"),
    "curve": ("stats", "networthPerMinute"),
    "result": ("match", "didRadiantWin"),
}
_working: dict[str, bool] = {g: True for g in _GROUPS}
_states: dict[tuple[int, str], dict] = {}
_lock = threading.Lock()


def _path(source: str, hero_id: int) -> Path:
    return ROOT / source / f"{hero_id}.json"


def _read(source: str, hero_id: int) -> dict:
    try:
        return json.loads(_path(source, hero_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"fetched": 0, "matches": []}


def _write(source: str, hero_id: int, data: dict) -> None:
    p = _path(source, hero_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def _maps() -> tuple[dict[int, str], dict[int, str]]:
    item_ids = {int(k): v for k, v in load_const("item_ids").items() if k.isdigit()}
    ability_ids = {int(i): v for k, v in load_const("ability_ids").items() for i in k.split(",") if i.isdigit()}
    return item_ids, ability_ids


def patch_start() -> int:
    return int(constants.current_patch()["ts"])


# ---------- Stratz -----------------------------------------------------------------------------

def _match_fields() -> str:
    player = _CORE_PLAYER
    stats_extra = " ".join(f for g, (where, f) in _GROUPS.items() if where == "stats" and _working[g])
    if stats_extra:
        player = player.replace("stats { itemPurchases { time itemId } }", f"stats {{ itemPurchases {{ time itemId }} {stats_extra} }}")
    player += "".join(f" {f}" for g, (where, f) in _GROUPS.items() if where == "player" and _working[g])
    match = "id startDateTime durationSeconds rank" + "".join(f" {f}" for g, (where, f) in _GROUPS.items() if where == "match" and _working[g])
    return f"{match} players {{ {player} }}"


def _query_player(sz: stratz.Stratz, account: int, hero_id: int) -> list[dict]:
    """A player's recent matches on the hero; drops an optional group Stratz does not know and retries."""
    for _ in range(len(_GROUPS) + 1):
        q = "{ player(steamAccountId: %d) { matches(request: {heroIds: [%d], take: %d}) { %s } } }" % (
            account, hero_id, MATCHES_PER_PLAYER, _match_fields())
        try:
            return (sz.q(q).get("player") or {}).get("matches") or []
        except RuntimeError as e:
            text = str(e)
            bad = [g for g, (_, fields) in _GROUPS.items() if _working[g] and any(re.search(rf"\b{f}\b", text) for f in fields.split())]
            if not bad or "Cannot query field" not in text and "does not exist" not in text and "Unknown" not in text:
                raise
            for g in bad:
                _working[g] = False
    return []


def _normalize_stratz(m: dict, hero_id: int, item_ids: dict, ability_ids: dict) -> dict | None:
    players = m.get("players") or []
    me = next((p for p in players if p.get("heroId") == hero_id), None)
    purchases = ((me or {}).get("stats") or {}).get("itemPurchases")
    if not me or not purchases:
        return None  # not parsed (yet)
    radiant = me.get("isRadiant")
    if radiant is None:  # without the «score» group: Stratz lists Radiant first
        radiant = players.index(me) < 5
    team = [p for p in players if (p.get("isRadiant") if p.get("isRadiant") is not None else players.index(p) < 5) == radiant]
    foes = [p for p in players if p not in team]
    pos = me.get("position")
    item = lambda i: item_ids.get(i) if i else None  # noqa: E731
    return {
        "m": m["id"], "t": m.get("startDateTime"), "dur": m.get("durationSeconds"), "rank": m.get("rank"), "src": "stratz",
        "acc": me.get("steamAccountId"), "name": None, "league": None,
        "w": bool(me.get("isVictory")), "pos": int(pos[-1]) if pos and str(pos).startswith("POSITION_") else None,
        "radiant": bool(radiant),
        "k": me.get("kills"), "d": me.get("deaths"), "a": me.get("assists"), "lh": me.get("numLastHits"), "dn": me.get("numDenies"),
        "gpm": me.get("goldPerMinute"), "xpm": me.get("experiencePerMinute"), "nw": me.get("networth"), "dmg": me.get("heroDamage"),
        "final": [item(me.get(f"item{i}Id")) for i in range(6)] if "item0Id" in me else None,
        "neutral": item(me.get("neutral0Id")),
        "items": [[x["time"], item_ids.get(x["itemId"], str(x["itemId"]))] for x in purchases],
        "skills": [ability_ids.get(a["abilityId"], str(a["abilityId"])) for a in sorted(me.get("abilities") or [], key=lambda a: a.get("time") or 0)],
        "curve": (me.get("stats") or {}).get("networthPerMinute"), "curve_kind": "networth",
        "allies": [p["heroId"] for p in team if p is not me], "enemies": [p["heroId"] for p in foes],
    }


def _fill_stratz(hero_id: int, source: str, state: dict) -> None:
    spec = SOURCES[source]
    since = patch_start()
    item_ids, ability_ids = _maps()
    data = _read(source, hero_id)
    have = {r["m"] for r in data["matches"]}
    fresh: list[dict] = []
    sz = stratz.Stratz(min_interval=0.45)
    try:
        board = sz.q("""{ leaderboard { hero(request: {heroIds: [%d], bracketIds: [%s], take: 100}) { steamAccountId position wins losses } } }"""
                     % (hero_id, ", ".join(spec["brackets"])))["leaderboard"]["hero"] or []
        board.sort(key=lambda r: -((r.get("wins") or 0) + (r.get("losses") or 0)))
        state["players"] = len(board)
        requests = 1
        for row in board:
            if requests >= STRATZ_MAX_REQUESTS or len(have) + len(fresh) >= TARGET or state.get("stop"):
                break
            left = stratz.limits.get("hour")
            if left is not None and left <= BUDGET_FLOOR:
                state["note"] = f"остановился, чтобы оставить запас запросов Stratz (осталось {left} в час)"
                break
            try:
                ms = _query_player(sz, row["steamAccountId"], hero_id)
            except RuntimeError as e:
                if "403" in str(e) or "private" in str(e).lower():
                    continue  # a private profile
                raise
            requests += 1
            for m in ms:
                if m["id"] in have or (m.get("startDateTime") or 0) < since or (m.get("rank") or 0) < spec["min_rank"]:
                    continue
                rec = _normalize_stratz(m, hero_id, item_ids, ability_ids)
                if rec:
                    fresh.append(rec)
                    have.add(rec["m"])
            if fresh:
                data["matches"] = sorted(data["matches"] + fresh, key=lambda r: -(r["t"] or 0))
                fresh = []
                _write(source, hero_id, data)
            state["requests"] = requests
    finally:
        sz.close()


# ---------- OpenDota (pro) ---------------------------------------------------------------------

def _pro_position(me: dict, team: list[dict]) -> int | None:
    """OpenDota gives the lane (1 safe, 2 mid, 3 off, 4 jungle), not the role: the richer of a lane's
    two is the core."""
    lane = me.get("lane_role")
    if lane == 2:
        return 2
    if lane not in (1, 3):
        return None
    mates = [p for p in team if p.get("lane_role") == lane]
    richest = max(mates, key=lambda p: p.get("net_worth") or 0)
    if lane == 1:
        return 1 if richest is me else 5
    return 3 if richest is me else 4


def _normalize_pro(m: dict, hero_id: int, ability_ids: dict) -> dict | None:
    players = m.get("players") or []
    me = next((p for p in players if p.get("hero_id") == hero_id), None)
    if not me or not me.get("purchase_log"):
        return None
    radiant = me.get("isRadiant", me.get("player_slot", 0) < 128)
    team = [p for p in players if p.get("isRadiant", p.get("player_slot", 0) < 128) == radiant]
    foes = [p for p in players if p not in team]
    upgrades = me.get("ability_upgrades_arr") or []
    teams = (m.get("radiant_team") or {}, m.get("dire_team") or {})
    return {
        "m": m["match_id"], "t": m.get("start_time"), "dur": m.get("duration"), "rank": None, "src": "pro",
        "acc": me.get("account_id"), "name": me.get("name") or me.get("personaname"),
        "team": (teams[0] if radiant else teams[1]).get("name"), "league": (m.get("league") or {}).get("name"),
        "w": bool(m.get("radiant_win")) == bool(radiant), "pos": _pro_position(me, team), "radiant": bool(radiant),
        "k": me.get("kills"), "d": me.get("deaths"), "a": me.get("assists"), "lh": me.get("last_hits"), "dn": me.get("denies"),
        "gpm": me.get("gold_per_min"), "xpm": me.get("xp_per_min"), "nw": me.get("net_worth"), "dmg": me.get("hero_damage"),
        "final": [None if not me.get(f"item_{i}") else _item_key(me.get(f"item_{i}")) for i in range(6)],
        "neutral": _item_key(me.get("item_neutral")) if me.get("item_neutral") else None,
        "items": [[x["time"], x["key"]] for x in me["purchase_log"]],
        "skills": [ability_ids.get(a, str(a)) for a in upgrades],
        "curve": me.get("gold_t"), "curve_kind": "gold",
        "allies": [p["hero_id"] for p in team if p is not me], "enemies": [p["hero_id"] for p in foes],
    }


def _item_key(item_id: int) -> str | None:
    item_ids, _ = _maps()
    return item_ids.get(int(item_id))


def _fill_pro(hero_id: int, state: dict) -> None:
    since = patch_start()
    _, ability_ids = _maps()
    data = _read("pro", hero_id)
    have = {r["m"] for r in data["matches"]}
    od = OpenDota()
    try:
        recent = od.get(f"/heroes/{hero_id}/matches") or []
        ids = [r["match_id"] for r in recent if (r.get("start_time") or 0) >= since and r["match_id"] not in have]
        state["players"] = len(recent)
        for n, mid in enumerate(ids[:PRO_MAX_DETAILS], 1):
            if len(have) >= TARGET or state.get("stop"):
                break
            rec = _normalize_pro(od.get(f"/matches/{mid}"), hero_id, ability_ids)
            state["requests"] = n
            if rec:
                data["matches"] = sorted(data["matches"] + [rec], key=lambda r: -(r["t"] or 0))
                have.add(rec["m"])
                _write("pro", hero_id, data)
    finally:
        od.close()


# ---------- the service ------------------------------------------------------------------------

def _run(hero_id: int, source: str, state: dict) -> None:
    try:
        if source == "pro":
            _fill_pro(hero_id, state)
        else:
            _fill_stratz(hero_id, source, state)
        data = _read(source, hero_id)
        data["fetched"] = time.time()
        _write(source, hero_id, data)
    except RateLimited:
        state["error"] = "дневной лимит OpenDota исчерпан — попробуй завтра"
    except RuntimeError as e:
        text = str(e)
        if "STRATZ_TOKEN" in text:
            state["error"] = "нет токена Stratz: укажи его в «Настройки → Аккаунт» (stratz.com/api, вход через Steam)"
        elif "429" in text or "limit" in text.lower():
            state["error"] = "Stratz просит подождать: лимит запросов токена на сейчас исчерпан"
        elif "401" in text or "403" in text:
            state["error"] = "Stratz не принял токен: проверь его в «Настройки → Аккаунт»"
        else:
            state["error"] = f"не удалось загрузить: {text[:300]}"
    except Exception as e:  # network and the like: shown, never raised into the API
        state["error"] = f"не удалось загрузить: {e}"
    finally:
        state["loading"] = False
        state["done"] = time.time()


def _item_name(key: str, items: dict) -> str:
    ru = _ru_items().get(key, {}).get("ru")
    return ru[0] if ru else (items.get(key) or {}).get("dname") or key


_ru_cache: dict = {}


def _ru_items() -> dict:
    if not _ru_cache:
        try:
            _ru_cache.update(json.loads((config.SHARED / "item_names.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return _ru_cache


def get(hero_id: int, source: str, refresh: bool = False) -> dict:
    """What is cached now; starts a background load when there is nothing, the list is stale, or
    `refresh`. Poll while `loading`."""
    if source not in SOURCES:
        raise ValueError("неизвестный источник")
    key = (hero_id, source)
    data = _read(source, hero_id)
    since = patch_start()
    matches = [r for r in data["matches"] if (r.get("t") or 0) >= since]
    with _lock:
        state = _states.get(key)
        busy = bool(state and state.get("loading"))
        stale = time.time() - data.get("fetched", 0) > REFRESH_AFTER
        recently_failed = state and state.get("error") and time.time() - state.get("done", 0) < 60
        if not busy and (refresh or stale or not matches) and not (recently_failed and not refresh):
            state = {"loading": True, "requests": 0, "players": 0, "error": None, "note": None}
            _states[key] = state
            threading.Thread(target=_run, args=(hero_id, source, state), daemon=True, name=f"topgames-{hero_id}-{source}").start()
    state = _states.get(key) or {}
    items = load_const("items")
    keys = {k for r in matches for _, k in r["items"]} | {k for r in matches for k in (r.get("final") or []) if k}
    skills = {k for r in matches for k in r["skills"]}
    from .builds.standard import talent_text
    from .data import abilities
    return {
        "hero_id": hero_id, "source": source, "label": SOURCES[source]["label"], "patch": constants.current_patch()["name"],
        "matches": matches, "fetched": data.get("fetched") or None,
        "loading": bool(state.get("loading")), "requests": state.get("requests", 0), "error": state.get("error"), "note": state.get("note"),
        "item_cost": {k: (items.get(k) or {}).get("cost") or 0 for k in keys},
        "item_names": {k: _item_name(k, items) for k in keys},
        # finished items worth a timing (assembled, 1400+ gold), Blink and the Shard too
        "core": sorted(k for k in keys if k in ("blink", "aghanims_shard")
                       or ((items.get(k) or {}).get("components") and ((items.get(k) or {}).get("cost") or 0) >= 1400)),
        "abilities": abilities.hero_abilities(hero_id, {k for k in skills if not k.startswith("special_bonus")}),
        "talents": {k: talent_text(k, hero_id) for k in skills if k.startswith("special_bonus")},
        "fields": {g: on for g, on in _working.items()},
        "limits": dict(stratz.limits),
    }
