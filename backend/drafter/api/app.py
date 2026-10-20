"""Local HTTP API for the desktop app. Listens on 127.0.0.1 only; when DRAFTER_TOKEN is set
(the Tauri shell generates one per launch) every request except /health and /icons must carry it
in the X-Drafter-Token header (or ?token= for WebSocket)."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, Field, model_validator

from .. import config, dota_paths, gsi, hero_grid, ingame, keybinds, pace, search, updates
from .. import settings as user_settings
from ..builds import counter, standard
from ..builds import service as build_service
from ..data import constants, gridstudio, matches, me, my_matches, patchnotes, players, ranks, renders, stratz
from ..lane import bulk as lane_bulk
from ..lane import service as lane_service
from ..model import draft, explain, meta, predictor, train
from ..model import grids as grid_builder
from ..vision import auto as vauto
from ..vision import autocal as vautocal
from ..vision import calibration as vcal
from ..vision import capture as vcap
from ..vision import collector as vcollect
from ..vision import evaluate as veval
from ..vision import layout as vlayout
from ..vision import matcher as vmatch
from ..vision import reader as vread
from ..vision import runner
from . import refresh, session
from .events import bus, jobs

ORIGINS = ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
           "http://localhost:1420", "http://127.0.0.1:1420"]
OPEN_PATHS = ("/health", "/icons/", "/mod-fonts/", "/workshop-media/", "/docs", "/openapi.json")


def token() -> str | None:
    return os.environ.get("DRAFTER_TOKEN") or None


tracker = gsi.Tracker(lambda **changes: session.patch("gsi", **changes))
vision_runner = runner.Runner(
    get_session=lambda: session.get().model_dump(),
    patch_session=lambda **changes: session.patch("vision", **changes),
    publish=lambda data: bus.publish("vision", **data),
)


def _set_vision(on: bool) -> None:
    s = user_settings.load()
    user_settings.save(s.model_copy(update={"vision_off": not on}))
    vision_runner.set_enabled(on)


def _vision_wanted() -> bool:
    """Reading is on from the first draft unless the user switched it off (now or, before this
    setting existed, in the wizard: auto.json's manual_off)."""
    return not user_settings.load().vision_off and not vauto.state().get("manual_off")


def _set_cautious(on: bool) -> None:
    vision_runner.cautious = on


def _after_draft(d: dict) -> None:
    out = vauto.finalize(d, _set_cautious)
    bus.publish("vision", status=vision_runner.status(), auto=out)


vision_collector = vcollect.Collector(
    get_session=lambda: session.get().model_dump(),
    get_game_state=lambda: tracker.last.get("game_state"),
    get_settings=user_settings.load,
    on_finalize=_after_draft,
)
vision_runner.on_frame = vision_collector.offer


def _on_gsi(payload: dict) -> None:
    changes = tracker.handle(payload, session.get().model_dump())
    vision_runner.new_match(tracker.match_id)
    bus.publish("gsi", status=tracker.status(), changes=changes)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bus.bind(asyncio.get_running_loop())
    if copied := config.ensure_seed():
        print(f"стартовые данные: скопировано {copied}", flush=True)
    server = None
    if os.environ.get("DRAFTER_NO_GSI") != "1":
        try:
            server = gsi.serve(_on_gsi)
        except OSError as e:  # port taken (another copy running): the app still works without GSI
            print(f"GSI-приёмник не запущен: порт {gsi.PORT} занят ({e})", flush=True)
        if gsi.upgrade():
            print("конфиг GSI обновлён (добавлены предметы для подсказок в игре): перезапусти Доту", flush=True)
    vision_runner.cautious = not vauto.proven()
    if _vision_wanted():
        vision_runner.set_enabled(True)
    if os.environ.get("DRAFTER_NO_GSI") != "1":   # without GSI there is never a draft phase to collect
        vision_collector.start()
    build_service.publish = lambda **data: bus.publish("builds", **data)
    if os.environ.get("DRAFTER_NO_PREFETCH") != "1":
        def _hero_art():
            time.sleep(20)   # after the app is up; at most once a week
            try:
                with httpx.Client(timeout=30, headers={"User-Agent": config.USER_AGENT}) as http:
                    if constants.refresh_hero_art(http):
                        vmatch.reload()   # the draft reader picks the new art up
            except Exception:  # noqa: BLE001 - never a reason to disturb the app
                pass
        threading.Thread(target=_hero_art, name="hero-art", daemon=True).start()
        try:
            build_service.start_prefetch(_pred().pos_mat)
        except HTTPException:
            pass  # no model yet
        lane_bulk.resume_later(lambda: _pred().pos_mat)  # an unfinished lane download goes on by itself
    yield
    build_service.stop_all()
    lane_service.stop_all()
    lane_bulk.shutdown()
    vision_runner.set_enabled(False)
    vision_collector.stop()
    if server:
        server.shutdown()


app = FastAPI(title="Dota Drafter API", version="0.2", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def auth(request: Request, call_next):
    t = token()
    if t and request.method != "OPTIONS" and not request.url.path.startswith(OPEN_PATHS):
        got = request.headers.get("x-drafter-token", "")
        if not hmac.compare_digest(got, t):
            return JSONResponse({"detail": "нужен токен X-Drafter-Token"}, status_code=401)
    return await call_next(request)


class IconFiles(StaticFiles):
    """Icons from the local cache; a hero or item icon that is not there yet is downloaded once."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code != 404 or not await run_in_threadpool(constants.fetch_icon, path):
                raise
            return await super().get_response(path, scope)


(config.DATA / "icons").mkdir(parents=True, exist_ok=True)
app.mount("/icons", IconFiles(directory=config.DATA / "icons"), name="icons")
# the free fonts of «Оформление игры» (SIL OFL), for the preview in the UI
app.mount("/mod-fonts", StaticFiles(directory=config.SHARED / "dota-fonts", check_dir=False), name="mod-fonts")


# ---------- context ----------------------------------------------------------------------

def _pred() -> predictor.Predictor:
    try:
        return predictor.get()
    except FileNotFoundError:
        raise HTTPException(503, "модель ещё не обучена: запусти обновление данных")


def _rank(rank_tier: int | None) -> int:
    return rank_tier or user_settings.load().rank_tier or me.rank_tier() or 50


def _pool(use_comfort: bool | None):
    s = user_settings.load()
    on = s.use_comfort if use_comfort is None else use_comfort
    return me.hero_pool() if on else None


def _hero_or_404(hero_id: int) -> dict:
    h = constants.hero_by_id().get(hero_id)
    if not h:
        raise HTTPException(404, f"нет героя с id {hero_id}")
    return h


def _term(t) -> dict:
    return {"kind": t.kind, "heroes": [int(h) for h in t.heroes], "value": round(float(t.value), 4),
            "pct": round(float(explain.expit(t.value) - 0.5) * 100, 2), "text": explain.term_text(t), "note": t.note}


# ---------- basics ----------------------------------------------------------------------

@app.get("/health")
def health():
    meta_path = train.ART / "meta.json"
    trained = None
    if meta_path.exists():
        import json
        trained = json.loads(meta_path.read_text(encoding="utf-8")).get("trained")
    try:
        patch = constants.current_patch()["name"]
    except FileNotFoundError:
        patch = None
    return {"ok": True, "patch": patch, "model_trained": trained, "matches": matches.summary().get("after_filters", 0),
            "stratz": bool(config.settings().stratz_token), "account_id": config.settings().account_id}


@app.get("/settings", response_model=user_settings.Settings)
def get_settings():
    return user_settings.load()


@app.put("/settings", response_model=user_settings.Settings)
def put_settings(s: user_settings.Settings):
    """Only the fields sent change: a client that doesn't know a newer setting can't reset it."""
    cur = user_settings.load()
    return user_settings.save(cur.model_copy(update=s.model_dump(include=s.model_fields_set)))


@app.get("/heroes")
def heroes():
    pr = _pred()
    out = []
    for h in constants.hero_index():
        shares = [round(float(x), 4) for x in pr.pos_mat[h["id"]]]
        out.append({"id": h["id"], "key": h["key"], "name": h["name"], "ru": h["ru"], "alias": h["alias"],
                    "attr": h["attr"], "attack": h["attack"], "roles": h["roles"],
                    "icon": f"/icons/heroes/{h['key']}.png", "positions": shares,
                    "main_pos": int(max(range(5), key=lambda i: shares[i])) + 1})
    return {"positions_source": pr.positions_source, "heroes": out}


@app.get("/heroes/search")
def hero_search(q: str = Query(..., min_length=1, max_length=40)):
    return {"ids": search.find(q)}


@app.get("/items")
def items():
    out = []
    for key, it in constants._load("items").items():
        if it.get("cost") and it.get("img"):
            out.append({"key": key, "name": it["dname"], "cost": it["cost"], "icon": f"/icons/items/{key}.png"})
    return out


@app.get("/heroes/{hero_id}")
def hero_page(hero_id: int, rank_tier: int | None = None):
    h = _hero_or_404(hero_id)
    pr = _pred()
    rank = _rank(rank_tier)
    group = int(draft.rank_group(rank))
    pool = me.hero_pool()
    mine = (pool or {}).get("heroes", {}).get(hero_id)
    bracket = stratz.bracket_for(rank)
    # positions with builds: wherever the hero is played in >= 10% of games (loaded on demand)
    builds = [p for p in range(1, 6) if pr.pos_mat[hero_id, p - 1] >= build_service.OFFROLE_SHARE]
    return {
        "hero": {**h, "icon": f"/icons/heroes/{h['key']}.png"},
        "rank_tier": rank, "bracket": bracket,
        "positions": [round(float(x), 4) for x in pr.pos_mat[hero_id]],
        "meta_wr": float(explain.expit(pr.lw[group, hero_id])), "pick_rate": float(pr.pick_rate[group, hero_id]),
        "bans": meta.ban_place(hero_id, bracket),
        "matchups": meta.matchups(hero_id, pr.S, pr.C, pr.pair_games, pr.cal_a),
        "builds_for_positions": builds,
        "me": None if not mine else {"games": mine["games"], "wins": mine["wins"], "edge": round(mine["edge"], 4),
                                     "experience": round(mine["experience"], 4)},
    }


@app.get("/meta/tierlist")
def tierlist(pos: int | None = Query(None, ge=1, le=5), tiers: str | None = None,
             days: int | None = Query(None, ge=1, le=60), rank_tier: int | None = None):
    rank = _rank(rank_tier)
    tier_list = [int(t) for t in tiers.split(",")] if tiers else [rank // 10]
    if not all(1 <= t <= 8 for t in tier_list):
        raise HTTPException(422, "tiers: числа 1..8 через запятую")
    return meta.tierlist(tier_list, pos, _pred().pos_mat, stratz.bracket_for(rank), days or user_settings.load().tier_days)


# ---------- draft ----------------------------------------------------------------------

class DraftIn(BaseModel):
    allies: list[int] = Field(default_factory=list, max_length=5)
    enemies: list[int] = Field(default_factory=list, max_length=5)
    bans: list[int] = Field(default_factory=list, max_length=24)
    pos: int | None = Field(None, ge=1, le=5)
    side: Literal["radiant", "dire"] | None = None
    rank_tier: int | None = Field(None, ge=11, le=80)
    use_comfort: bool | None = None
    comfort_weight: float | None = Field(None, ge=0, le=1)

    @model_validator(mode="after")
    def check(self):
        ids = self.allies + self.enemies + self.bans
        if len(ids) != len(set(ids)):
            raise ValueError("один и тот же герой указан дважды")
        known = constants.hero_by_id()
        if bad := [i for i in ids if i not in known]:
            raise ValueError(f"неизвестные id героев: {bad}")
        return self


def _ctx(d: DraftIn):
    rank = _rank(d.rank_tier)
    return rank, int(draft.rank_group(rank))


@app.post("/draft/evaluate")
def draft_evaluate(d: DraftIn):
    pr = _pred()
    rank, group = _ctx(d)
    ev = pr.evaluate(d.allies, d.enemies, group, d.side)
    return {"p_win": ev.p_win, "rank_tier": rank, "terms": [_term(t) for t in ev.terms[:15]]}


@app.post("/draft/suggest")
def draft_suggest(d: DraftIn):
    pr = _pred()
    rank, group = _ctx(d)
    s = user_settings.load()
    pos = d.pos or s.pos
    weight = s.comfort_weight if d.comfort_weight is None else d.comfort_weight
    res = pr.suggest(d.allies, d.enemies, d.bans, pos, group, d.side, _pool(d.use_comfort), comfort_weight=weight)
    row = lambda r: {**{k: v for k, v in r.items() if k != "terms"}, "terms": [_term(t) for t in r["terms"][:6]]}
    return {"pos": pos, "rank_tier": rank, "positions_source": pr.positions_source,
            "p_win_now": pr.evaluate(d.allies, d.enemies, group, d.side).p_win,
            "main": [row(r) for r in res["main"]], "offrole": [row(r) for r in res["offrole"]]}


@app.post("/draft/bans")
def draft_bans(d: DraftIn):
    pr = _pred()
    rank, group = _ctx(d)
    pos = d.pos or user_settings.load().pos
    res = pr.bans(d.allies, d.enemies, d.bans, pos, group, me.hero_pool())
    return {"pos": pos, "bans": [{**{k: v for k, v in r.items() if k != "terms"},
                                   "terms": [_term(t) for t in r["terms"][:4]]} for r in res]}


# ---------- builds ----------------------------------------------------------------------

def _builds(hero_id: int, pos: int, mode: str, rank_tier: int | None, fallback: bool) -> dict:
    _hero_or_404(hero_id)
    if mode not in ("all", "specialists"):
        raise HTTPException(422, "mode: all или specialists")
    return build_service.get(hero_id, pos, mode, stratz.bracket_for(_rank(rank_tier)), _pred().pos_mat, fallback)


@app.get("/builds/{hero_id}")
def build(hero_id: int, pos: int = Query(..., ge=1, le=5), mode: str = "all", rank_tier: int | None = None,
          fallback: bool = False):
    """Whole builds from real purchase sequences (loads matches in the background if needed:
    poll while status == "loading"); below the minimum, the aggregated build marked approximate."""
    return _builds(hero_id, pos, mode, rank_tier, fallback)


class VsIn(BaseModel):
    enemies: list[int] = Field(..., min_length=1, max_length=5)
    pos: int = Field(..., ge=1, le=5)
    mode: str = "all"
    rank_tier: int | None = None
    fallback: bool = False


@app.post("/builds/{hero_id}/vs")
def build_vs(hero_id: int, body: VsIn):
    known = constants.hero_by_id()
    if bad := [e for e in body.enemies if e not in known]:
        raise HTTPException(422, f"неизвестные id героев: {bad}")
    b = _builds(hero_id, body.pos, body.mode, body.rank_tier, body.fallback)
    recs = counter.against(body.enemies, b["pos"], _pred().pos_mat, hero_items=b["item_share"])
    base = b["builds"][0] if b["builds"] else b["approximate"]
    have = set()
    if base:
        have = {x["key"] for x in base["core"] + base["early"]} | {a["key"] for x in base["core"] for a in x["alternatives"]}
        if base.get("boots"):
            have.add(base["boots"]["key"])
    for r in recs:
        r["in_build"] = r["item"] in have
        r["rare_on_hero"] = r["hero_share"] is not None and r["hero_share"] < counter.RARE_ON_HERO
        r["icon"] = f"/icons/items/{r['item']}.png"
    return {"build": b, "vs": recs}


# ---------- lane ----------------------------------------------------------------------

@app.get("/lane")
def lane(hero: int, enemy: int, pos: int = Query(..., ge=1, le=5), enemy_pos: int | None = Query(None, ge=1, le=5),
         rank_tier: int | None = None, fallback: bool = True):
    """Who wins the lane (Stratz lane outcomes) and how it goes minute by minute in real matches of the
    pair (loads them in the background: poll while status == "loading").
    With fallback, a position the hero almost never plays is replaced by its usual one. Without
    enemy_pos, where the enemy would stand on that lane; if it plays none of the facing positions,
    `off_lane` is set and nothing is loaded."""
    _hero_or_404(hero)
    _hero_or_404(enemy)
    if hero == enemy:
        raise HTTPException(422, "герой не может стоять против себя")
    pos_mat = _pred().pos_mat
    requested = pos
    if fallback:
        pos = lane_service.effective_pos(hero, pos, pos_mat)
    if enemy_pos is None:
        enemy_pos = lane_service.lane_position(enemy, pos, pos_mat)
    if enemy_pos is None:
        return {"hero": hero, "pos": pos, "requested_pos": requested if requested != pos else None, "enemy": enemy,
                "enemy_pos": None, "off_lane": True, "status": "ready"}
    out = lane_service.get(hero, pos, enemy, enemy_pos, stratz.bracket_for(_rank(rank_tier)))
    out.update(requested_pos=requested if requested != pos else None, off_lane=False)
    return out


class LaneOpponentsIn(BaseModel):
    pos: int = Field(..., ge=1, le=5)
    enemies: list[int] = Field(..., min_length=1, max_length=5)
    hero: int | None = None   # my hero: a position it almost never plays is replaced by its usual one


@app.post("/lane/opponents")
def lane_opponents(body: LaneOpponentsIn):
    """Enemies with their likely positions in this draft, the ones on my lane first."""
    known = constants.hero_by_id()
    if bad := [e for e in body.enemies + ([body.hero] if body.hero else []) if e not in known]:
        raise HTTPException(422, f"неизвестные id героев: {bad}")
    pos_mat = _pred().pos_mat
    pos = lane_service.effective_pos(body.hero, body.pos, pos_mat) if body.hero else body.pos
    enemies = [e for e in dict.fromkeys(body.enemies) if e != body.hero]
    return {"pos": pos, "requested_pos": body.pos if body.pos != pos else None,
            "opponents": lane_service.opponents(pos, enemies, pos_mat) if enemies else []}


@app.get("/lane/bulk")
def lane_bulk_status():
    """Background download of lane data (pool heroes first, then frequent core pairs)."""
    return lane_bulk.status()


class LaneBulkIn(BaseModel):
    action: Literal["start", "stop"]


@app.post("/lane/bulk")
def lane_bulk_action(body: LaneBulkIn):
    if body.action == "stop":
        return lane_bulk.stop()
    try:
        return lane_bulk.start(_pred().pos_mat)
    except RuntimeError as e:
        raise HTTPException(409, str(e))


# ---------- me ----------------------------------------------------------------------

@app.get("/me")
def my_profile():
    data = me.load()
    if not data:
        raise HTTPException(404, "истории ещё нет: нажми «Обновить историю»")
    pool = me.hero_pool(data)
    prof = data["profile"].get("profile") or {}
    heroes = sorted(pool["heroes"].items(), key=lambda kv: -kv[1]["games"])[:30]
    return {"account_id": data["account_id"], "name": prof.get("personaname"),
            "avatar": "/me/avatar" if me.AVATAR.exists() else None,
            "rank_tier": me.rank_tier(data), "leaderboard": data["profile"].get("leaderboard_rank"),
            "rank_progress": ranks.progress(me.rank_tier(data), (data["profile"].get("mmr_estimate") or {}).get("estimate")),
            "plus": bool(prof.get("plus")), "fetched": data["fetched"], "overall": pool["overall"],
            "experience": pool["experience"],
            "heroes": [{"hero": h, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()}}
                       for h, s in heroes]}


@app.get("/me/avatar")
def my_avatar():
    from fastapi.responses import FileResponse
    if not me.AVATAR.exists():
        raise HTTPException(404, "аватар ещё не загружен: обнови историю")
    return FileResponse(me.AVATAR, media_type="image/jpeg")


# ---------- patch notes (data/patchnotes.py) ---------------------------------------------------

def _my_heroes() -> set[int]:
    """The heroes the user plays (5+ games, the 20 most played): their changes come first."""
    try:
        pool = me.hero_pool()
    except Exception:  # noqa: BLE001 - no history yet: nothing is «mine»
        return set()
    ranked = sorted(pool["heroes"].items(), key=lambda kv: -kv[1]["games"])[:20]
    return {int(h) for h, st in ranked if st["games"] >= 5}


@app.get("/patches")
def patches_list(refresh: bool = False):
    try:
        if refresh:
            patchnotes.ensure(refresh=True)
        return patchnotes.patch_list(_my_heroes())
    except patchnotes.PatchNotesError as e:
        raise HTTPException(502, str(e))


@app.get("/patches/{version}")
def patch_notes(version: str):
    if not re.fullmatch(r"\d+\.\d+[a-z]?", version):
        raise HTTPException(422, "неверный номер патча")
    try:
        return patchnotes.patch(version, _my_heroes())
    except patchnotes.PatchNotesError as e:
        raise HTTPException(404 if "нет патча" in str(e) else 502, str(e))


# ---------- GridStudio's workshop (data/gridstudio.py) ----------------------------------------

def _workshop(fn, *a, **kw):
    if os.environ.get("DRAFTER_NO_BUILD_LOAD") == "1":   # tests: never hit the network
        raise HTTPException(503, "мастерская выключена в тестах")
    try:
        return fn(*a, **kw)
    except gridstudio.WorkshopError as e:
        raise HTTPException(404 if "больше нет" in str(e) else 502, str(e))


@app.get("/workshop/meta")
def workshop_meta():
    return gridstudio.meta()


@app.get("/workshop/grids")
def workshop_grids(q: str = "", tag: str = "", sort: str = "popular", page: int = 0):
    return _workshop(gridstudio.grids, q, tag, sort, page)


@app.get("/workshop/grids/{work_id}")
def workshop_grid(work_id: str):
    return _workshop(gridstudio.grid_file, work_id)


@app.get("/workshop/backgrounds")
def workshop_backgrounds(q: str = "", tag: str = "", aspect: str = "", sort: str = "popular", page: int = 0):
    return _workshop(gridstudio.backgrounds, q, tag, aspect, sort, page)


@app.get("/workshop/arts")
def workshop_arts():
    return _workshop(gridstudio.arts)


@app.get("/workshop-media/grid/{work_id}.jpg")
def workshop_grid_preview(work_id: str, rev: str = ""):
    from fastapi.responses import FileResponse
    return FileResponse(_workshop(gridstudio.grid_preview, work_id, rev), media_type="image/jpeg")


@app.get("/workshop-media/bg/{bg_id}/{name}")
def workshop_background_file(bg_id: str, name: str):
    from fastapi.responses import FileResponse
    path, kind = _workshop(gridstudio.background_file, bg_id, name)
    return FileResponse(path, media_type=kind)


# ---------- links to the sites the app shows data from ------------------------------------------
# The app window has no browser of its own: a link opens in the default browser, for these
# sites only (a page can't make the backend open anything else).

LINK_HOSTS = ("stratz.com", "www.dotabuff.com", "dotabuff.com", "www.opendota.com", "opendota.com",
              "steamcommunity.com", "gridstudio.me", "github.com", "t.me")


class OpenUrlIn(BaseModel):
    url: str = Field(..., max_length=500)


@app.post("/open-url")
def open_url(body: OpenUrlIn):
    from urllib.parse import urlparse
    u = urlparse(body.url)
    if u.scheme != "https" or (u.hostname or "") not in LINK_HOSTS:
        raise HTTPException(422, "эту ссылку программа не открывает")
    if os.environ.get("DRAFTER_NO_BUILD_LOAD") != "1":   # tests: nothing opens
        import webbrowser
        webbrowser.open(body.url)
    return {"opened": body.url}


# ---------- any player, searched by hand (data/players.py) --------------------------------------
# Only what the user typed: players of the current match are never looked up by themselves.

@app.get("/players/lookup")
def player_lookup(q: str = Query(..., max_length=300), refresh: bool = False):
    if os.environ.get("DRAFTER_NO_BUILD_LOAD") == "1":   # tests: never hit the network
        raise HTTPException(503, "поиск игроков выключен в тестах")
    try:
        return players.lookup(q, refresh)
    except players.PlayerError as e:
        raise HTTPException(422, str(e))


# ---------- hero models on a transparent background (data/renders.py) -------------------------
# The files themselves are served from /icons/renders/ (open, like every icon).

def _render_call(fn, *a):
    try:
        return fn(*a)
    except renders.RenderError as e:
        raise HTTPException(422, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"CDN Valve не ответил: {e}")


@app.get("/hero-render/{key}")
def hero_render_info(key: str):
    return _render_call(renders.info, key)


@app.post("/hero-render/{key}/video")
def hero_render_video(key: str):
    """Download the animated render once (about 5-10 MB); the app takes its first frame."""
    _render_call(renders.video, key)
    return renders.info(key)


@app.post("/hero-render/{key}/still")
async def hero_render_still(key: str, request: Request):
    """The first frame of the render as PNG with alpha, drawn by the app (raw bytes in the body)."""
    data = await request.body()
    return await run_in_threadpool(_render_call, renders.save_still, key, data)


@app.post("/hero-render/{key}/segment")
def hero_render_segment(key: str):
    """No transparent render: remove the background locally, once."""
    return _render_call(renders.segment, key)


@app.get("/me/summary")
def my_summary():
    return me.summary(_pred().pos_mat)


@app.get("/me/matches")
def my_matches_list(refresh: bool = False):
    """Recent ranked matches with an estimate of how I played. Answers from the cache at once and
    refreshes from Stratz in the background when it is stale: poll while job.status == "loading"."""
    if not config.settings().account_id:
        raise HTTPException(409, "не указан аккаунт: укажи Steam ID в «Настройки → Аккаунт»")
    if os.environ.get("DRAFTER_NO_BUILD_LOAD") != "1":   # tests: never hit the network
        my_matches.ensure_fresh(force=refresh)
    return my_matches.history()


@app.post("/me/refresh")
def my_refresh():
    if not config.settings().account_id:
        raise HTTPException(409, "не указан аккаунт: укажи Steam ID в «Настройки → Аккаунт»")
    d = me.refresh()
    my_matches.ensure_fresh(force=True)
    return {"matches": len(d["matches"]), "rank_tier": me.rank_tier(d)}


# ---------- first-run setup ----------------------------------------------------------------

@app.get("/setup")
def get_setup():
    s = config.settings()
    return {"account_id": s.account_id, "has_stratz_token": bool(s.stratz_token), "env_file": str(config.ENV_FILE),
            "installed": config.FROZEN, "has_matches": matches.summary().get("matches", 0) > 0}


class SetupIn(BaseModel):
    account_id: int | None = Field(None, gt=0, lt=2**32)
    stratz_token: str | None = Field(None, max_length=2000)


@app.put("/setup")
def put_setup(body: SetupIn):
    """Saves the user's own Steam32 id and (optionally) their Stratz token to .env."""
    values = {}
    if body.account_id:
        values["DOTA_ACCOUNT_ID"] = str(body.account_id)
    if body.stratz_token is not None:
        token = body.stratz_token.strip()
        if token and not re.fullmatch(r"[A-Za-z0-9._\-]+", token):
            raise HTTPException(422, "токен Stratz выглядит неправильно")
        values["STRATZ_TOKEN"] = token
    if values:
        config.write_env(**values)
    return get_setup()


@app.get("/setup/dota")
def get_setup_dota():
    """The Dota folder in use: picked by hand in the setup, or found through Steam."""
    manual = user_settings.load().dota_dir
    auto = dota_paths.auto_dota_path()
    used = dota_paths.dota_path()
    return {"path": str(used) if used else None, "auto": str(auto) if auto else None, "manual": manual,
            "manual_ok": bool(manual) and dota_paths.is_dota_dir(Path(manual))}


class DotaDirIn(BaseModel):
    path: str | None = Field(None, max_length=1000)


@app.put("/setup/dota")
def put_setup_dota(body: DotaDirIn):
    """A folder picked by hand (anything inside «dota 2 beta» will do); null goes back to Steam's."""
    root = None
    if body.path and body.path.strip():
        root = dota_paths.find_dota_root(Path(body.path.strip().strip('"')))
        if root is None:
            raise HTTPException(422, "в этой папке нет Доты: нужна «dota 2 beta» (Steam → steamapps → common)")
    s = user_settings.load()
    user_settings.save(s.model_copy(update={"dota_dir": str(root) if root else None}))
    return get_setup_dota()


@app.post("/setup/dota/browse")
def browse_dota_dir():
    """Windows' own folder picker (the app window has no file dialog of its own); null if cancelled."""
    import subprocess
    script = ("Add-Type -AssemblyName System.Windows.Forms;"
              "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
              "$d.Description='Папка Доты: dota 2 beta';$d.ShowNewFolderButton=$false;"
              "if($d.ShowDialog() -eq 'OK'){[Console]::OutputEncoding=[Text.Encoding]::UTF8;$d.SelectedPath}")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", script], capture_output=True,
                           timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HTTPException(503, f"окно выбора папки не открылось: {e}")
    picked = r.stdout.decode("utf-8", errors="replace").strip()
    return {"path": picked or None}


@app.get("/setup/accounts")
def setup_accounts():
    """Steam accounts that signed in on this PC, the last one first (to fill the Friend ID)."""
    return {"accounts": dota_paths.steam_accounts()}


class StratzCheckIn(BaseModel):
    token: str = Field(..., max_length=2000)


@app.post("/setup/stratz-check")
def stratz_check(body: StratzCheckIn):
    """Whether a Stratz token works, before it is saved: one tiny query with it."""
    token = body.token.strip()
    if not token or not re.fullmatch(r"[A-Za-z0-9._\-]+", token):
        return {"ok": False, "error": "токен выглядит неправильно: это длинная строка с сайта stratz.com/api"}
    try:
        r = httpx.post(config.STRATZ, json={"query": "{ player(steamAccountId: 86745912) { steamAccountId } }"}, timeout=20,
                       headers={"Authorization": f"Bearer {token}", "User-Agent": "STRATZ_API"})
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"Stratz не ответил: {e}"}
    if r.status_code in (401, 403):
        return {"ok": False, "error": "Stratz не принял токен: скопируй его заново (stratz.com/api → API Token)"}
    if r.status_code == 429:
        return {"ok": True, "error": None, "note": "токен верный, но Stratz просит подождать: лимит запросов"}
    if r.status_code >= 400:
        return {"ok": False, "error": f"Stratz ответил {r.status_code}"}
    return {"ok": True, "error": None}


# ---------- shared live draft ----------------------------------------------------------------

@app.get("/session", response_model=session.Session)
def get_session():
    return session.get()


@app.put("/session", response_model=session.Session)
def put_session(s: session.Session):
    return session.put(s)


# ---------- Dota install: display mode and key bindings (read-only) -----------------------------

@app.get("/dota/display")
def dota_display():
    acc = config.settings().account_id
    vm = dota_paths.video_mode(acc) if acc else None
    if not vm:
        return {"found": False}
    return {"found": True, "width": vm.width, "height": vm.height, "fullscreen": vm.fullscreen,
            "borderless": vm.borderless, "label": vm.label}


@app.get("/dota/keybinds")
def dota_keybinds():
    acc = config.settings().account_id
    return {"keys": sorted(keybinds.bound_keys(acc)) if acc else []}


# ---------- Hero grids: the user's hero_grid_config.json ----------------------------------------
# The one Dota file we write besides the GSI config: it is the user's own grid file in Steam's
# userdata. Only with Dota closed, with a backup, and only our own "Драфтер · …" grids (hero_grid.py).

GridId = Literal["roles", "meta", "pool", "counters"]


class GridWriteIn(BaseModel):
    grids: list[GridId] = Field(min_length=1)


class GridRestoreIn(BaseModel):
    name: str = Field(max_length=120)


class GridConfigsIn(BaseModel):
    """Grids from the editor, in the file's own shape (config_name, categories)."""
    configs: list[dict] = Field(min_length=1, max_length=hero_grid.MAX_CONFIGS)


def _grid_args() -> tuple[int | None, int, str | None, int]:
    rank = _rank(None)
    return config.settings().account_id, rank, stratz.bracket_for(rank), user_settings.load().tier_days


def _grid_call(fn, *args):
    try:
        return fn(*args)
    except hero_grid.DotaRunning as e:
        raise HTTPException(409, str(e))
    except hero_grid.GridError as e:
        raise HTTPException(422, str(e))


@app.get("/hero-grids")
def hero_grids():
    """The grids we would write, built from the current data (for the preview)."""
    _, rank, bracket, days = _grid_args()
    built = _grid_call(grid_builder.build, _pred(), list(grid_builder.GRIDS), rank, bracket, days)
    out = []
    for gid, (name, desc) in grid_builder.GRIDS.items():
        cfg = built.get(gid)
        cats = [{"name": c["category_name"], "heroes": c["hero_ids"]} for c in cfg["categories"]] if cfg else []
        out.append({"id": gid, "name": name, "description": desc, "config_name": hero_grid.PREFIX + name,
                    "categories": cats, "heroes": sum(len(c["heroes"]) for c in cats)})
    return {"rank_tier": rank, "bracket": bracket, "days": days, "prefix": hero_grid.PREFIX, "grids": out}


@app.get("/hero-grids/state")
def hero_grids_state():
    """File, backups and whether Dota runs: cheap, the settings card polls it."""
    account = config.settings().account_id
    try:
        running, check_error = hero_grid.dota_running(), None
    except hero_grid.GridError as e:
        running, check_error = None, str(e)
    return {"account_id": account, "dota_running": running, "check_error": check_error, **hero_grid.status(account)}


@app.post("/hero-grids/write")
def hero_grids_write(body: GridWriteIn):
    account, rank, bracket, days = _grid_args()
    built = _grid_call(grid_builder.build, _pred(), list(dict.fromkeys(body.grids)), rank, bracket, days)
    if not built:
        raise HTTPException(422, "по этим данным сетки получились пустыми: нечего записывать")
    return _grid_call(hero_grid.apply, account, list(built.values()))


@app.get("/hero-grids/file")
def hero_grids_file():
    """Every grid of the user's file, for the editor's import (read only)."""
    return {"prefix": hero_grid.PREFIX, **_grid_call(hero_grid.read_configs, config.settings().account_id)}


@app.post("/hero-grids/write-configs")
def hero_grids_write_configs(body: GridConfigsIn):
    """The editor's grids into Dota: each gets our prefix, so only our grids are added or replaced;
    our grids that are not among them leave the file. Same checks as /hero-grids/write."""
    ours = _grid_call(hero_grid.clean_configs, body.configs)
    return _grid_call(hero_grid.apply, config.settings().account_id, ours)


@app.post("/hero-grids/export")
def hero_grids_export(body: GridConfigsIn):
    """A hero_grid_config.json of the editor's grids (names as they are), saved in exports/."""
    configs = _grid_call(hero_grid.clean_configs, body.configs, False)
    text = hero_grid.export_text(configs)
    folder = config.ROOT / "exports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"hero_grid_config-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(text, encoding="utf-8", newline="")
    return {"path": str(path), "folder": str(folder), "text": text}


@app.post("/hero-grids/open-exports")
def hero_grids_open_exports():
    folder = config.ROOT / "exports"
    folder.mkdir(parents=True, exist_ok=True)
    if not hasattr(os, "startfile"):
        raise HTTPException(501, "открыть папку можно только в Windows")
    os.startfile(folder)  # Explorer on our own folder
    return {"folder": str(folder)}


@app.post("/hero-grids/remove")
def hero_grids_remove():
    return _grid_call(hero_grid.remove_ours, config.settings().account_id)


@app.post("/hero-grids/restore")
def hero_grids_restore(body: GridRestoreIn):
    return _grid_call(hero_grid.restore, config.settings().account_id, body.name)


# ---------- Game State Integration ---------------------------------------------------------------

@app.get("/gsi/status")
def gsi_status():
    return {"port": gsi.PORT, **gsi.installed(), **tracker.status()}


@app.get("/game/live")
def game_live(targets: str = "", pos: int | None = Query(None, ge=1, le=5)):
    """In-game hints for the overlay (ingame.py): timers, the next item of the build, buyback.
    `targets` is the build's item order, comma-separated. null live: no match or GSI silent."""
    live = tracker.live
    if live and time.time() - live["ts"] > 15:
        live = None  # Dota closed or the match ended without a final message
    keys = [k for k in targets.split(",") if re.fullmatch(r"[a-z0-9_]{1,60}", k)][:30]
    out = ingame.hints(live, keys)
    out["pace"] = pace.pace(live, (live or {}).get("hero_id"), pos)
    return out


@app.post("/gsi/install")
def gsi_install():
    try:
        return gsi.install()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


# ---------- screen reading (experimental) ---------------------------------------------------------

SNAPSHOTS = vcollect.SNAPSHOTS


def _snapshot_path(snap_id: str):
    """Snapshots from the wizard are PNG; frames collected during drafts (auto-...) are JPEG."""
    if not re.fullmatch(r"[0-9a-z_\-]{1,40}", snap_id):
        raise HTTPException(422, "неверный id снимка")
    for ext in (".png", ".jpg"):
        p = SNAPSHOTS / f"{snap_id}{ext}"
        if p.exists():
            return p
    raise HTTPException(404, "снимок не найден")


def _save_snapshot(img) -> dict:
    import cv2
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    snap_id = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
    cv2.imencode(".png", img)[1].tofile(str(SNAPSHOTS / f"{snap_id}.png"))
    h, w = img.shape[:2]
    return {"id": snap_id, "width": w, "height": h}


@app.get("/vision/status")
def vision_status():
    labeled = len(list(veval.LABELED.glob("*.json"))) if veval.LABELED.exists() else 0
    report = veval.REPORT.read_text(encoding="utf-8") if veval.REPORT.exists() else None
    cal = vcal.load()
    auto_state = vauto.state()
    return {**vision_runner.status(), "calibrated": vcal.PATH.exists(), "calibration_auto": cal.auto,
            "layout_base": vlayout.base()[1], "fits": sorted(vlayout._detected()),
            "labeled_frames": labeled, "required_precision": veval.REQUIRED_PRECISION, "report": report,
            "dota_window": vcap.find_window() is not None, "collect": vision_collector.status(),
            "auto": {"last": auto_state.get("last"), "proven": bool(auto_state.get("proven")),
                     "proven_at": auto_state.get("proven_at"),
                     "rule": {"drafts": vauto.AUTO_MIN_DRAFTS, "frames": vauto.AUTO_MIN_FRAMES,
                              "filled": vauto.AUTO_MIN_FILLED}}}


@app.post("/vision/snapshot")
def vision_snapshot():
    try:
        return _save_snapshot(vcap.grab())
    except vcap.CaptureError as e:
        raise HTTPException(409, str(e))


@app.post("/vision/upload")
async def vision_upload(request: Request):
    """Raw image bytes in the body (a screenshot saved with F12 in Steam, for example)."""
    import cv2
    import numpy as np
    data = await request.body()
    if len(data) > 40_000_000:
        raise HTTPException(413, "файл больше 40 МБ")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(422, "это не картинка (нужен PNG или JPG)")
    return _save_snapshot(img)


@app.get("/vision/snapshots")
def vision_snapshots():
    files = sorted(SNAPSHOTS.glob("*.png"), reverse=True)[:30] if SNAPSHOTS.exists() else []
    return [p.stem for p in files]


@app.get("/vision/snapshots/{snap_id}.png")
def vision_snapshot_file(snap_id: str):
    from fastapi.responses import FileResponse
    p = _snapshot_path(snap_id)
    return FileResponse(p, media_type="image/jpeg" if p.suffix == ".jpg" else "image/png")


@app.get("/vision/collected")
def vision_collected():
    """Drafts collected by themselves (newest first): frames, labels from the draft board."""
    return vcollect.drafts()


class AutocalIn(BaseModel):
    snapshot: str
    radiant: list[int] | None = None   # teams on this frame; default: the labels of its draft
    dire: list[int] | None = None


@app.post("/vision/autocal")
def vision_autocal(body: AutocalIn):
    """Fit the rects to a frame with known heroes. Not saved: the wizard shows it for a check first."""
    frame = vmatch._read(_snapshot_path(body.snapshot))
    radiant, dire = body.radiant, body.dire
    if radiant is None or dire is None:
        draft_id = body.snapshot.removeprefix("auto-").rsplit("-", 1)[0] if body.snapshot.startswith("auto-") else None
        lab = ((vcollect.load_draft(draft_id) or {}).get("labels") if draft_id else None) or {}
        radiant, dire = radiant or lab.get("radiant"), dire or lab.get("dire")
    if not radiant or not dire:
        raise HTTPException(409, "для автокалибровки нужны составы обеих команд на этом кадре")
    cal, info = vautocal.locate(frame, radiant, dire)
    return {"calibration": cal, "info": info}


@app.get("/vision/calibration", response_model=vcal.Calibration)
def vision_get_calibration(width: int | None = None, height: int | None = None):
    """The rects the reader uses on a frame of this size (saved, detected or built-in)."""
    if width and height:
        return vlayout.for_frame(width, height)
    return vcal.load()


@app.put("/vision/calibration", response_model=vcal.Calibration)
def vision_put_calibration(c: vcal.Calibration):
    """Rects the user placed or approved: they win over everything automatic for this aspect."""
    return vcal.save(c.model_copy(update={"preset": False, "auto": False, "source": "manual"}))


@app.delete("/vision/calibration")
def vision_reset_calibration():
    """Back to reading without calibration: the saved rects and the detected fits are dropped."""
    had = vcal.PATH.exists()
    vcal.PATH.unlink(missing_ok=True)
    vlayout.forget_fits()
    return {"removed": had}


@app.get("/vision/calibration/preset", response_model=vcal.Calibration)
def vision_preset(width: int = 1920, height: int = 1080):
    return vlayout.profile(width, height)


@app.get("/vision/layout")
def vision_layout():
    """What reading without calibration knows: the built-in resolutions, the fits found on frames."""
    _, origin = vlayout.base()
    fits = vlayout._detected()
    return {"base": origin,
            "profiles": [{"width": w, "height": h, "aspect": vlayout.aspect_label(w, h),
                          "source": vlayout.for_frame(w, h).source} for w, h in vlayout.PROFILES],
            "fits": [{"size": k, **{f: v.get(f) for f in ("scale", "score", "portraits", "at", "base")}} for k, v in fits.items()],
            "last_fit": vision_runner.autofit.last_info}


class DetectIn(BaseModel):
    snapshot: str
    save: bool = False


@app.post("/vision/detect")
def vision_detect(body: DetectIn):
    """Fit the layout to this frame by the portraits on it (no heroes need to be known)."""
    frame = vmatch._read(_snapshot_path(body.snapshot))
    h, w = frame.shape[:2]
    fit, info = vlayout.detect(frame)
    if fit and body.save:
        vlayout.save_fit(w, h, fit)
    cal = vlayout._make(vlayout.base()[0], w, h, "detected", fit) if fit else None
    return {"calibration": cal, "info": info, "saved": bool(fit and body.save)}


class ReadIn(BaseModel):
    snapshot: str
    calibration: vcal.Calibration | None = None   # try unsaved rects from the wizard


@app.post("/vision/read")
def vision_read(body: ReadIn):
    frame = vmatch._read(_snapshot_path(body.snapshot))
    return vread.as_json(vread.read(frame, body.calibration))


class CropsIn(BaseModel):
    snapshot: str
    calibration: vcal.Calibration


@app.post("/vision/crops")
def vision_crops(body: CropsIn):
    """Exactly what the reader cuts out of this frame with these rectangles (the same crop code),
    as small PNGs: the wizard shows them under the frame right after a rectangle moves."""
    import base64
    import cv2
    frame = vmatch._read(_snapshot_path(body.snapshot))
    h, w = frame.shape[:2]
    out: dict = {"width": w, "height": h, "warnings": []}
    if abs(w / h - body.calibration.aspect) > 0.02:
        out["warnings"].append(f"соотношение сторон кадра {w}×{h} не совпадает с этими рамками: "
                               "нажми «Встроенный профиль» или «Найти рамки по кадру»")
    for group, items in vread.crops(frame, body.calibration).items():
        out[group] = []
        for crop in items:
            if crop.size == 0:
                out[group].append(None)
                continue
            scale = min(1.0, 96 / max(crop.shape[1], 1))
            small = cv2.resize(crop, (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale))),
                               interpolation=cv2.INTER_AREA) if scale < 1 else crop
            ok, buf = cv2.imencode(".png", small)
            out[group].append("data:image/png;base64," + base64.b64encode(buf.tobytes()).decode() if ok else None)
    return out


class LabelIn(BaseModel):
    snapshot: str
    calibration: vcal.Calibration | None = None
    radiant: list[int | None] = Field(..., min_length=5, max_length=5)
    dire: list[int | None] = Field(..., min_length=5, max_length=5)
    bans: list[int | None] = Field(default_factory=list)


@app.post("/vision/label")
def vision_label(body: LabelIn):
    """The user confirmed what is really on this frame: every filled slot becomes a learned template,
    and the frame joins the labelled set used to measure accuracy."""
    import shutil
    known = constants.hero_by_id()
    if bad := [h for h in body.radiant + body.dire + body.bans if h and h not in known]:
        raise HTTPException(422, f"неизвестные id героев: {bad}")
    src = _snapshot_path(body.snapshot)
    frame = vmatch._read(src)
    cal = body.calibration or vcal.load()
    crops = vread.crops(frame, cal)
    learned = 0
    for group in ("radiant", "dire", "bans"):
        for crop, hero in zip(crops[group], getattr(body, group)):
            if hero and crop.size and vmatch.learn(hero, crop):
                learned += 1
    veval.LABELED.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, veval.LABELED / src.name)
    (veval.LABELED / f"{src.stem}.json").write_text(
        json.dumps({"radiant": body.radiant, "dire": body.dire, "bans": body.bans}), encoding="utf-8")
    return {"learned": learned}


@app.post("/vision/evaluate")
def vision_evaluate():
    results = []
    if veval.LABELED.exists() and any(veval.LABELED.glob("*.json")):
        results.append(veval.evaluate(veval.LABELED))
    if veval.SYNTH.exists() and any(veval.SYNTH.glob("*.json")):
        results.append(veval.evaluate(veval.SYNTH))
    veval.write_report(results)
    total = vauto.evaluate_all()
    return {"results": [{k: v for k, v in r.items() if k != "groups"} for r in results],
            "collected": total["collected"], "total": {k: total[k] for k in ("drafts", "frames", "filled", "correct",
                                                                          "precision", "required", "auto_rule")}}


class EnableIn(BaseModel):
    on: bool


@app.post("/vision/enable")
def vision_enable(body: EnableIn):
    """On or off by hand, at any time. While the accuracy is unproven the reader is cautious
    (only confident reads), so switching it on early fills fewer slots, not wrong ones."""
    _set_vision(body.on)
    st = vauto.state()
    st["manual_off"] = not body.on
    st.pop("auto_enabled", None)
    vauto._save_state(st)
    return vision_runner.status()


# ---------- jobs & events ----------------------------------------------------------------

class DebugLogIn(BaseModel):
    lines: list[str] = Field(..., max_length=500)


UI_DEBUG_MAX = 2_000_000


# ---------- «Игры топов» ----------------------------------------------------------------------

@app.get("/top-games/{hero_id}")
def top_games(hero_id: int, source: Literal["immortal", "divine", "pro"] = "immortal", refresh: bool = False):
    """Recent current-patch matches of the hero by Immortal / Divine+ players or pros; starts a
    background load when needed (poll while `loading`)."""
    from .. import topgames
    if hero_id not in constants.hero_by_id():
        raise HTTPException(404, "нет такого героя")
    return topgames.get(hero_id, source, refresh)


class TopVsIn(BaseModel):
    hero: int
    enemies: list[int] = Field(default_factory=list, max_length=5)
    pos: int | None = Field(default=None, ge=1, le=5)


@app.post("/top-games/vs")
def top_games_vs(body: TopVsIn):
    """The build of top players on the hero in games where the enemy team had this draft (the
    overlay's Build mode); {found: false} when there is no such game. Loads in the background."""
    from .. import topgames
    if body.hero not in constants.hero_by_id():
        raise HTTPException(404, "нет такого героя")
    return topgames.vs_draft(body.hero, body.enemies, body.pos)


# ---------- «Оформление игры»: the menu background and fonts (off by default) -----------------

MOD_BUNDLE_MAX = 80_000_000


def _unbundle(body: bytes) -> tuple[dict, list[bytes]]:
    """The UI's upload: 4-byte length + JSON, then 4-byte length + data for each file (no
    multipart parser in the bundled backend)."""
    import struct as _struct
    if len(body) > MOD_BUNDLE_MAX:
        raise HTTPException(413, "слишком большой файл")
    try:
        n = _struct.unpack_from("<I", body, 0)[0]
        meta = json.loads(body[4:4 + n].decode("utf-8"))
        at, blobs = 4 + n, []
        while at < len(body):
            size = _struct.unpack_from("<I", body, at)[0]
            blobs.append(body[at + 4:at + 4 + size])
            at += 4 + size
    except (ValueError, _struct.error, UnicodeDecodeError):
        raise HTTPException(400, "повреждённая отправка") from None
    if not isinstance(meta, dict):
        raise HTTPException(400, "повреждённая отправка")
    return meta, blobs


def _mods_call(fn, *args):
    from ..game_mods import fonts as mod_fonts, install as mod_install, menu as mod_menu
    try:
        return fn(*args)
    except (mod_install.ModError, mod_menu.PackError, mod_fonts.FontError) as e:
        raise HTTPException(422, str(e))
    except hero_grid.GridError as e:
        raise HTTPException(422, str(e))


@app.get("/game-mods/status")
def game_mods_status():
    from ..game_mods import install as mod_install
    return mod_install.status(config.settings().account_id)


@app.get("/game-mods/fonts")
def game_mods_fonts():
    from ..game_mods import fonts as mod_fonts
    return {"fonts": mod_fonts.catalog(), "families": mod_fonts.FAMILIES, "base": "/mod-fonts"}


@app.post("/game-mods/font-check")
async def game_mods_font_check(request: Request):
    """A font of the user's: can Dota use it, which letters it lacks."""
    from ..game_mods import fonts as mod_fonts
    data = await request.body()
    if len(data) > 30_000_000:
        raise HTTPException(413, "файл шрифта больше 30 МБ")
    font = _mods_call(mod_fonts.read_font, data)
    return {"family": font.names.get(16) or font.names.get(1) or "", "style": font.names.get(17) or font.names.get(2) or "",
            "weight": font.weight, "italic": font.italic, "missing": font.missing()}


@app.post("/game-mods/background")
async def game_mods_background(request: Request):
    """meta: {clean, hero: off|menu|own, grid: menu|dim|own, grid_dim, has_menu, accept: true};
    files in order: the menu video (if has_menu), the hero's (hero=own), the grid's (grid=own)."""
    from ..game_mods import install as mod_install, menu as mod_menu
    meta, blobs = _unbundle(await request.body())
    if meta.get("accept") is not True:
        raise HTTPException(422, "сначала включи «Оформление игры» и прочитай предупреждение")
    queue = list(blobs)
    take = lambda: queue.pop(0) if queue else None  # noqa: E731
    video = take() if meta.get("has_menu") else None
    hero, grid = str(meta.get("hero", "off")), str(meta.get("grid", "menu"))
    hero_video = take() if hero == "own" else None
    grid_video = take() if grid == "own" else None
    pack = _mods_call(lambda: mod_menu.build_pack(video, clean=bool(meta.get("clean")), hero=hero, hero_video=hero_video,
                                                  grid=grid, grid_dim=float(meta.get("grid_dim", 0.5)), grid_video=grid_video))
    info = {"clean": bool(meta.get("clean")), "hero": hero, "grid": grid, "menu": video is not None, "label": str(meta.get("label", ""))[:120]}
    return await run_in_threadpool(_mods_call, mod_install.install_background, config.settings().account_id, pack, info)


@app.post("/game-mods/fonts")
async def game_mods_install_fonts(request: Request):
    """meta: {catalog: id | null, families: [...], keep_grid, accept: true}; files: the user's own fonts."""
    from ..game_mods import fonts as mod_fonts, install as mod_install
    meta, blobs = _unbundle(await request.body())
    if meta.get("accept") is not True:
        raise HTTPException(422, "сначала включи «Оформление игры» и прочитай предупреждение")
    families = [f for f in meta.get("families", []) if f in mod_fonts.FAMILIES]
    if not families:
        raise HTTPException(422, "выбери, какой текст Доты заменить")
    if meta.get("catalog"):
        faces = _mods_call(mod_fonts.catalog_fonts, str(meta["catalog"]))
        label = str(meta["catalog"])
    else:
        if not blobs:
            raise HTTPException(422, "нет файла шрифта")
        faces = [_mods_call(mod_fonts.read_font, b) for b in blobs]
        label = "свой шрифт"
    keep = [mod_fonts.GRID_FONT_FILE] if meta.get("keep_grid") else []
    files = _mods_call(mod_fonts.font_pack, faces, families, keep)
    return await run_in_threadpool(_mods_call, mod_install.install_fonts, files, {"font": label, "families": families, "keep_grid": bool(keep)})


@app.post("/game-mods/packs")
async def game_mods_install_pack(request: Request, name: str = Query("", max_length=200), accept: bool = False):
    """A VPK of the user's (raw body) into the voice language folder («Свои VPK»)."""
    from ..game_mods import install as mod_install
    if not accept:
        raise HTTPException(422, "сначала включи «Оформление игры» и прочитай предупреждение")
    size = int(request.headers.get("content-length") or 0)
    if size > mod_install.PACK_MAX:
        raise HTTPException(413, "VPK больше 1,5 ГБ")
    # streamed to a file: a pack can be a gigabyte, it is never held in memory whole
    folder = mod_install.incoming_dir()
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / f"upload-{os.getpid()}-{time.time_ns()}.vpk"
    try:
        written = 0
        with part.open("wb") as f:
            async for chunk in request.stream():
                written += len(chunk)
                if written > mod_install.PACK_MAX:
                    raise HTTPException(413, "VPK больше 1,5 ГБ")
                f.write(chunk)
        return await run_in_threadpool(_mods_call, mod_install.install_pack, config.settings().account_id, part, name)
    finally:
        part.unlink(missing_ok=True)


@app.post("/game-mods/remove")
def game_mods_remove(body: dict):
    from ..game_mods import install as mod_install
    what = body.get("what", "all")
    if what == "pack":
        return {"removed": _mods_call(mod_install.remove_pack, str(body.get("id", "")))}
    fn = {"all": mod_install.remove_all, "background": mod_install.remove_background, "fonts": mod_install.remove_fonts,
          "packs": mod_install.remove_packs}.get(what)
    if fn is None:
        raise HTTPException(422, "непонятно, что убрать")
    return {"removed": _mods_call(fn)}


@app.post("/debug/log")
def debug_log(body: DebugLogIn):
    """The UI's hidden debug mode (wheel events and the like) appends here: logs/ui-debug.log in
    the user's data folder. Kept under ~2 MB: the older half goes when it grows past that."""
    path = config.ROOT / "logs" / "ui-debug.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > UI_DEBUG_MAX:
        data = path.read_bytes()
        path.write_bytes(data[len(data) // 2:])
    with path.open("a", encoding="utf-8") as f:
        for line in body.lines:
            f.write(line[:4000].replace("\n", " ") + "\n")
    return {"ok": True, "path": str(path)}


@app.post("/data/refresh")
def data_refresh():
    return jobs.start("refresh", refresh.run).public()


# ---------- updates of the app (updates.py) ------------------------------------------------------

@app.get("/update/check")
def update_check(current: str = Query(..., max_length=20)):
    if os.environ.get("DRAFTER_NO_BUILD_LOAD") == "1":   # tests: never hit the network
        raise HTTPException(503, "проверка обновлений выключена в тестах")
    try:
        return updates.check(current)
    except updates.UpdateError as e:
        raise HTTPException(502, str(e)) from e


@app.post("/update/download")
def update_download():
    return jobs.start("update", updates.download).public()


@app.get("/update/ready")
def update_ready():
    return {"ready": updates.ready()}


@app.get("/jobs")
def job_list():
    return [j.public() for j in sorted(jobs.jobs.values(), key=lambda j: -j.started)]


@app.get("/jobs/{job_id}")
def job(job_id: str):
    j = jobs.jobs.get(job_id)
    if not j:
        raise HTTPException(404, "нет такой задачи")
    return j.public()


@app.websocket("/events")
async def events(ws: WebSocket):
    t = token()
    if t and not hmac.compare_digest(ws.query_params.get("token", ""), t):
        await ws.close(code=4401)
        return
    await ws.accept()
    q = bus.subscribe()
    try:
        await ws.send_json({"type": "hello"})
        while True:
            await ws.send_json(await q.get())
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(q)
