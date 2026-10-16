"""Local HTTP API for the desktop app. Listens on 127.0.0.1 only; when DRAFTER_TOKEN is set
(the Tauri shell generates one per launch) every request except /health and /icons must carry it
in the X-Drafter-Token header (or ?token= for WebSocket)."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .. import config, dota_paths, gsi, keybinds, search
from .. import settings as user_settings
from ..builds import counter, standard
from ..data import constants, matches, me, stratz
from ..model import draft, explain, meta, predictor, train
from ..vision import calibration as vcal
from ..vision import capture as vcap
from ..vision import evaluate as veval
from ..vision import matcher as vmatch
from ..vision import reader as vread
from ..vision import runner
from . import refresh, session
from .events import bus, jobs

ORIGINS = ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
           "http://localhost:1420", "http://127.0.0.1:1420"]
OPEN_PATHS = ("/health", "/icons/", "/docs", "/openapi.json")


def token() -> str | None:
    return os.environ.get("DRAFTER_TOKEN") or None


tracker = gsi.Tracker(lambda **changes: session.patch("gsi", **changes))
vision_runner = runner.Runner(
    get_session=lambda: session.get().model_dump(),
    patch_session=lambda **changes: session.patch("vision", **changes),
    publish=lambda data: bus.publish("vision", **data),
)


def _on_gsi(payload: dict) -> None:
    changes = tracker.handle(payload, session.get().model_dump())
    vision_runner.new_match(tracker.match_id)
    bus.publish("gsi", status=tracker.status(), changes=changes)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bus.bind(asyncio.get_running_loop())
    server = None
    if os.environ.get("DRAFTER_NO_GSI") != "1":
        try:
            server = gsi.serve(_on_gsi)
        except OSError as e:  # port taken (another copy running): the app still works without GSI
            print(f"GSI-приёмник не запущен: порт {gsi.PORT} занят ({e})", flush=True)
    if user_settings.load().vision_enabled:
        vision_runner.set_enabled(True)
    yield
    vision_runner.set_enabled(False)
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


(config.DATA / "icons").mkdir(parents=True, exist_ok=True)
app.mount("/icons", StaticFiles(directory=config.DATA / "icons"), name="icons")


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
    return user_settings.save(s)


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
    builds = [p for p in range(1, 6) if standard.build(hero_id, p, bracket)]
    return {
        "hero": {**h, "icon": f"/icons/heroes/{h['key']}.png"},
        "rank_tier": rank, "bracket": bracket,
        "positions": [round(float(x), 4) for x in pr.pos_mat[hero_id]],
        "meta_wr": float(explain.expit(pr.lw[group, hero_id])), "pick_rate": float(pr.pick_rate[group, hero_id]),
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

def _build_or_404(hero_id: int, pos: int, rank_tier: int | None, fallback: bool = False) -> dict:
    """The build for (hero, pos). With fallback, a position the hero is barely played on is replaced
    by its most played one (overlay: my position from the draft may not suit the hero I ended up on)."""
    h = _hero_or_404(hero_id)
    bracket = stratz.bracket_for(_rank(rank_tier))
    b = standard.build(hero_id, pos, bracket)
    if not b and fallback:
        shares = _pred().pos_mat[hero_id]
        for p in sorted(range(1, 6), key=lambda p: -shares[p - 1]):
            if b := standard.build(hero_id, p, bracket):
                b["requested_pos"] = pos
                break
    if not b:
        raise HTTPException(404, f"нет данных Stratz для {h['name']} на позиции {pos} ({bracket})")
    return b


@app.get("/builds/{hero_id}")
def build(hero_id: int, pos: int = Query(..., ge=1, le=5), rank_tier: int | None = None, fallback: bool = False):
    return _build_or_404(hero_id, pos, rank_tier, fallback)


class VsIn(BaseModel):
    enemies: list[int] = Field(..., min_length=1, max_length=5)
    pos: int = Field(..., ge=1, le=5)
    rank_tier: int | None = None
    fallback: bool = False


@app.post("/builds/{hero_id}/vs")
def build_vs(hero_id: int, body: VsIn):
    known = constants.hero_by_id()
    if bad := [e for e in body.enemies if e not in known]:
        raise HTTPException(422, f"неизвестные id героев: {bad}")
    b = _build_or_404(hero_id, body.pos, body.rank_tier, body.fallback)
    recs = counter.against(body.enemies, b["pos"], _pred().pos_mat, hero_items=b["item_share"])
    have = {x["key"] for x in b["core"] + b["early"]}
    for r in recs:
        r["in_build"] = r["item"] in have
        r["rare_on_hero"] = r["hero_share"] is not None and r["hero_share"] < counter.RARE_ON_HERO
        r["icon"] = f"/icons/items/{r['item']}.png"
    return {"build": b, "vs": recs}


# ---------- me ----------------------------------------------------------------------

@app.get("/me")
def my_profile():
    data = me.load()
    if not data:
        raise HTTPException(404, "истории ещё нет: POST /me/refresh")
    pool = me.hero_pool(data)
    prof = data["profile"].get("profile") or {}
    heroes = sorted(pool["heroes"].items(), key=lambda kv: -kv[1]["games"])[:30]
    return {"account_id": data["account_id"], "name": prof.get("personaname"), "avatar": prof.get("avatarfull"),
            "rank_tier": me.rank_tier(data), "fetched": data["fetched"], "overall": pool["overall"],
            "experience": pool["experience"],
            "heroes": [{"hero": h, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()}}
                       for h, s in heroes]}


@app.post("/me/refresh")
def my_refresh():
    d = me.refresh()
    return {"matches": len(d["matches"]), "rank_tier": me.rank_tier(d)}


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


# ---------- Game State Integration ---------------------------------------------------------------

@app.get("/gsi/status")
def gsi_status():
    return {"port": gsi.PORT, **gsi.installed(), **tracker.status()}


@app.post("/gsi/install")
def gsi_install():
    try:
        return gsi.install()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


# ---------- screen reading (experimental) ---------------------------------------------------------

SNAPSHOTS = config.DATA / "vision" / "snapshots"


def _snapshot_path(snap_id: str):
    if not re.fullmatch(r"[0-9a-z_\-]{1,40}", snap_id):
        raise HTTPException(422, "неверный id снимка")
    p = SNAPSHOTS / f"{snap_id}.png"
    if not p.exists():
        raise HTTPException(404, "снимок не найден")
    return p


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
    return {**vision_runner.status(), "calibrated": vcal.PATH.exists(), "labeled_frames": labeled,
            "required_precision": veval.REQUIRED_PRECISION, "report": report,
            "dota_window": vcap.find_window() is not None}


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
    return FileResponse(_snapshot_path(snap_id), media_type="image/png")


@app.get("/vision/calibration", response_model=vcal.Calibration)
def vision_get_calibration():
    return vcal.load()


@app.put("/vision/calibration", response_model=vcal.Calibration)
def vision_put_calibration(c: vcal.Calibration):
    return vcal.save(c.model_copy(update={"preset": False}))


@app.get("/vision/calibration/preset", response_model=vcal.Calibration)
def vision_preset():
    return vcal.preset_16_9()


class ReadIn(BaseModel):
    snapshot: str
    calibration: vcal.Calibration | None = None   # try unsaved rects from the wizard


@app.post("/vision/read")
def vision_read(body: ReadIn):
    frame = vmatch._read(_snapshot_path(body.snapshot))
    return vread.as_json(vread.read(frame, body.calibration))


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
            if hero and crop.size:
                vmatch.learn(hero, crop)
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
    return {"results": [{k: v for k, v in r.items() if k != "groups"} for r in results]}


class EnableIn(BaseModel):
    on: bool


@app.post("/vision/enable")
def vision_enable(body: EnableIn):
    if body.on:
        ev = veval.evaluate(veval.LABELED) if veval.LABELED.exists() else {"precision": None, "frames": 0}
        if ev["frames"] < 3:
            raise HTTPException(409, "сначала откалибруй и подтверди хотя бы 3 настоящих кадра драфта")
        if ev["precision"] is None or ev["precision"] < veval.REQUIRED_PRECISION:
            got = "—" if ev["precision"] is None else f"{ev['precision']:.0%}"
            raise HTTPException(409, f"точность на подтверждённых кадрах {got}, нужно не ниже "
                                     f"{veval.REQUIRED_PRECISION:.0%}: подтверди ещё кадры или подними порог")
    s = user_settings.load()
    user_settings.save(s.model_copy(update={"vision_enabled": body.on}))
    vision_runner.set_enabled(body.on)
    return vision_runner.status()


# ---------- jobs & events ----------------------------------------------------------------

@app.post("/data/refresh")
def data_refresh():
    return jobs.start("refresh", refresh.run).public()


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
