"""Dota 2 Game State Integration.

Dota POSTs JSON to the URI from cfg/gamestate_integration/*.cfg, so the receiver needs a fixed
port; the API itself runs on a random per-launch port. A tiny stdlib HTTP server on 127.0.0.1
handles only these POSTs and checks the auth token written into our cfg.

What a *player* gets (Valve exposes only the local player's data): map.game_state, the match id,
player.team_name, and hero.id/name once picked. The "draft" block is documented for spectators;
we parse it if it ever arrives and log every payload so this can be checked on a real match.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, dota_paths, ingame, kv
from .data import constants

PORT = 47831
CFG_NAME = "gamestate_integration_dotadrafter.cfg"
OLD_CFGS = ["gamestate_integration_drafthelper.cfg"]  # the user's earlier attempt (approved for removal)
STATE_FILE = config.DATA / "gsi.json"
LOG_DIR = config.DATA / "gsi"  # one JSONL file per day, auth token stripped

DRAFT_STATES = {"DOTA_GAMERULES_STATE_HERO_SELECTION", "DOTA_GAMERULES_STATE_STRATEGY_TIME"}
GAME_STATES = {"DOTA_GAMERULES_STATE_TEAM_SHOWCASE", "DOTA_GAMERULES_STATE_WAIT_FOR_MAP_TO_LOAD",
               "DOTA_GAMERULES_STATE_PRE_GAME", "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"}


# ---------- config file ----------------------------------------------------------------------

def _token() -> str:
    try:
        t = json.loads(STATE_FILE.read_text()).get("token") if STATE_FILE.exists() else None
    except (OSError, ValueError, AttributeError):
        t = None   # an empty or broken file (power loss mid-write): a new token, the config is rewritten with it
    if t:
        return t
    t = secrets.token_hex(16)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"token": t}))
    os.replace(tmp, STATE_FILE)
    return t


def cfg_text(port: int = PORT) -> str:
    return kv.dumps({"Dota Drafter": {
        "uri": f"http://127.0.0.1:{port}/",
        "timeout": "5.0", "buffer": "0.1", "throttle": "0.25", "heartbeat": "10.0",
        "data": {"provider": "1", "map": "1", "player": "1", "hero": "1", "items": "1", "draft": "1"},
        "auth": {"token": _token()},
    }})


def install() -> dict:
    """Write our cfg into Dota's gamestate_integration folder and remove the old helper's cfg.
    Dota reads these files at start, so it has to be restarted afterwards."""
    dota = dota_paths.dota_path()
    if not dota:
        raise FileNotFoundError("не нашёл установку Dota 2")
    folder = dota_paths.gsi_dir(dota)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / CFG_NAME).write_text(cfg_text(), encoding="utf-8")
    removed = []
    for name in OLD_CFGS:
        p = folder / name
        if p.exists():
            p.unlink()
            removed.append(name)
    return {"path": str(folder / CFG_NAME), "removed": removed}


def installed() -> dict:
    dota = dota_paths.dota_path()
    if not dota:
        return {"dota_found": False, "installed": False}
    folder = dota_paths.gsi_dir(dota)
    p = folder / CFG_NAME
    ok = p.exists() and f"127.0.0.1:{PORT}" in p.read_text(encoding="utf-8", errors="replace") \
        and _token() in p.read_text(encoding="utf-8", errors="replace")
    others = sorted(x.name for x in folder.glob("*.cfg") if x.name != CFG_NAME) if folder.is_dir() else []
    # an older cfg of ours without the items block: the in-game hints need it
    outdated = ok and '"items"' not in p.read_text(encoding="utf-8", errors="replace")
    return {"dota_found": True, "installed": ok, "outdated": outdated, "path": str(p), "other_cfgs": others}


def upgrade() -> bool:
    """Rewrites our own cfg when it is an older version (same port and token, fewer data blocks).
    Only our file is touched; Dota picks it up at its next start."""
    try:
        st = installed()
        if st.get("installed") and st.get("outdated"):
            install()
            return True
    except OSError:
        pass
    return False


# ---------- payload -> session ---------------------------------------------------------------

def _hero_id(value) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.startswith("npc_dota_hero_"):
        key = value.removeprefix("npc_dota_hero_")
        return next((h["id"] for h in constants.hero_index() if h["key"] == key), None)
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None


def parse_draft(draft: dict) -> dict[str, list[int]]:
    """Spectator-style draft block: team2 = Radiant, team3 = Dire; pickN_id / banN_id."""
    out = {"radiant": [], "dire": [], "bans": []}
    for team, side in (("team2", "radiant"), ("team3", "dire")):
        t = draft.get(team) or {}
        for i in range(10):
            h = _hero_id(t.get(f"pick{i}_id")) or _hero_id(t.get(f"pick{i}_class"))
            if h:
                out[side].append(h)
            b = _hero_id(t.get(f"ban{i}_id")) or _hero_id(t.get(f"ban{i}_class"))
            if b:
                out["bans"].append(b)
    return out


def merge_slots(slots: list, heroes: list[int], taken: set[int]) -> list:
    """The board's slots with the heroes Dota reported for that team added: each into the first
    empty slot, in Dota's order. Nothing is removed: a slot Dota says nothing about keeps what the
    screen reader or the user put there. A hero reported for the other team leaves this one."""
    out = [h if h not in taken or h in heroes else None for h in slots]
    for h in heroes:
        if h in out:
            continue
        if None not in out:
            break
        out[out.index(None)] = h
    return out


class Tracker:
    """Turns the GSI stream into session updates. Kept separate from HTTP for tests."""

    def __init__(self, apply):
        self.apply = apply          # callable(**changes) -> patches the shared session
        self.match_id: str | None = None
        self.last: dict = {}
        self.last_ts = 0.0
        self.has_draft_block = False
        self.live: dict | None = None  # the in-game part of the last message (ingame.py), during a match

    def status(self) -> dict:
        return {"last_seen": self.last_ts or None, "match_id": self.match_id, "has_draft_block": self.has_draft_block,
                **{k: self.last.get(k) for k in ("game_state", "team", "hero_id", "phase")}}

    def handle(self, payload: dict, current: dict) -> dict | None:
        """current: the session as a dict. Returns the applied changes (or None)."""
        self.last_ts = time.time()
        m = payload.get("map") or {}
        player = payload.get("player") or {}
        hero = payload.get("hero") or {}
        state = m.get("game_state")
        phase = "draft" if state in DRAFT_STATES else "game" if state in GAME_STATES else "idle"
        side = {"radiant": "radiant", "dire": "dire"}.get(str(player.get("team_name", "")).lower())
        hero_id = _hero_id(hero.get("id")) or _hero_id(hero.get("name"))
        self.last = {"game_state": state, "team": side, "hero_id": hero_id, "phase": phase}
        self.live = ingame.live_from_payload(payload) if phase == "game" else None

        changes: dict = {}
        match_id = m.get("matchid")
        if match_id and match_id != self.match_id and phase != "idle":
            # a new match: start from an empty draft (my position and comfort setting stay)
            self.match_id = match_id
            changes.update(allies=[None] * 5, enemies=[None] * 5, bans=[], my_hero=None)
            current = {**current, **changes}
        if phase != current.get("phase"):
            changes["phase"] = phase
        if side and side != current.get("side"):
            changes["side"] = side
        if hero_id and hero_id != current.get("my_hero"):
            changes["my_hero"] = hero_id
            allies = list(changes.get("allies", current.get("allies") or [None] * 5))
            enemies = changes.get("enemies", current.get("enemies") or [None] * 5)
            bans = changes.get("bans", current.get("bans") or [])
            if hero_id not in allies and hero_id not in enemies and hero_id not in bans and None in allies:
                allies[allies.index(None)] = hero_id
                changes["allies"] = allies

        draft = payload.get("draft")
        if isinstance(draft, dict) and (draft.get("team2") or draft.get("team3")):
            self.has_draft_block = True
            d = parse_draft(draft)
            mine = side or current.get("side")
            if mine:
                ours, theirs = (d["radiant"], d["dire"]) if mine == "radiant" else (d["dire"], d["radiant"])
                # the block only adds what it knows: a player's GSI carries their own team, and
                # an empty enemy side used to wipe the enemies read from the screen on every tick
                # (the reader then took the cleared slots for the user's edits and stopped)
                base = {**current, **changes}
                for key, heroes in (("allies", ours), ("enemies", theirs)):
                    merged = merge_slots(base.get(key) or [None] * 5, heroes, taken=set(ours) | set(theirs))
                    if merged != list(base.get(key) or [None] * 5):
                        changes[key] = merged
                bans = list(base.get("bans") or [])
                new_bans = [b for b in d["bans"] if b not in bans]
                if new_bans:
                    changes["bans"] = (bans + new_bans)[:16]
        if changes:
            self.apply(**changes)
            return changes
        return None


# ---------- HTTP receiver --------------------------------------------------------------------

LOG_DAYS = 7               # days of GSI messages kept (a match sends several a second)
LOG_DAY_MAX = 20_000_000   # bytes per day; past that the day is not logged any further


class _Log:
    def __init__(self):
        self.lock = threading.Lock()
        self.day = ""

    def _prune(self) -> None:
        for old in sorted(LOG_DIR.glob("*.jsonl"))[:-LOG_DAYS]:
            old.unlink(missing_ok=True)

    def write(self, payload: dict) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        day = time.strftime("%Y-%m-%d")
        path = LOG_DIR / f"{day}.jsonl"
        safe = {k: v for k, v in payload.items() if k != "auth"}
        with self.lock:
            if not (path.exists() and path.stat().st_size > LOG_DAY_MAX):
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": time.time(), **safe}, ensure_ascii=False) + "\n")
            if day != self.day:   # once a day (and on start): older days go, today's file included in the count
                self.day = day
                self._prune()


def serve(on_payload, port: int = PORT) -> ThreadingHTTPServer:
    """Start the receiver in a daemon thread. on_payload(dict) is called for authenticated POSTs."""
    token = _token()
    log = _Log()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                self.send_response(400)
                self.end_headers()
                return
            if (payload.get("auth") or {}).get("token") != token:
                self.send_response(401)
                self.end_headers()
                return
            log.write(payload)
            try:
                on_payload(payload)
            finally:
                self.send_response(200)
                self.end_headers()

        def log_message(self, *args):  # keep the console quiet: Dota posts several times a second
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, name="gsi", daemon=True).start()
    return server
