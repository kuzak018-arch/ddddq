"""After every match: its «Кто заруинил» breakdown made by itself, and the user's rating kept.

GSI says when a match is over (the game state leaves the match for the post-game screen or the
menu). The match is not on OpenDota at once: the first breakdown is tried after FIRST_WAIT and
then every RETRY until LOOK_FOR; when it is there, the UI gets a "ruin" event (the app opens the
breakdown). OpenDota parses the replay a few minutes later (ruin.fetch asks for the parse), so
the breakdown is fetched again every PARSE_RETRY until it is parsed or PARSE_FOR has passed; the
final one is announced too.

The user's own rating of every breakdown (found by account id, else by the hero GSI reported) is
kept in data/ruin/mine.json: the profile draws it as a line over the games. `backfill` adds the
last ranked matches from the history the same way (one OpenDota request each).
"""

from __future__ import annotations

import json
import threading
import time

from . import config, ruin

PATH = config.DATA / "ruin" / "mine.json"
IN_MATCH = {"DOTA_GAMERULES_STATE_PRE_GAME", "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"}
FIRST_WAIT = 90
RETRY = 120
LOOK_FOR = 40 * 60
PARSE_RETRY = 5 * 60
PARSE_FOR = 3 * 3600
BACKFILL = 20
_lock = threading.Lock()


def load() -> dict:
    try:
        data = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PATH)


def entry(analysis: dict, account_id: int | None, hero: int | None) -> dict | None:
    """The user's line of a breakdown: rating, tag, result, and who the ruiner was."""
    players = analysis.get("players") or []
    me = next((p for p in players if account_id and p.get("acc") == account_id), None) \
        or next((p for p in players if hero and p.get("hero") == hero), None)
    if not me:
        return None
    v = analysis.get("verdict") or {}
    return {"match": analysis["id"], "t": analysis.get("start"), "hero": me["hero"], "pos": me.get("pos"),
            "rating": me["rating"], "win": me.get("win"), "tag": me.get("tag"), "kind": v.get("kind"),
            "ruiner": v.get("ruiner"), "mvp": v.get("mvp"), "parsed": bool(analysis.get("parsed")),
            "k": me.get("k"), "d": me.get("d"), "a": me.get("a")}


def record(analysis: dict, account_id: int | None, hero: int | None) -> dict | None:
    e = entry(analysis, account_id, hero)
    if e:
        with _lock:
            data = load()
            data[str(e["match"])] = e
            _save(data)
    return e


def history() -> list[dict]:
    return sorted(load().values(), key=lambda e: e.get("t") or 0)


class AfterMatch:
    def __init__(self, publish, account_id=lambda: config.settings().account_id, sleep=time.sleep, now=time.time):
        self.publish, self.account_id, self.sleep, self.now = publish, account_id, sleep, now
        self.running: set[str] = set()

    def on_state(self, before: str | None, after: str | None, match_id: str | None, hero: int | None) -> bool:
        """Called on every GSI message; starts the follow-up when a match has just ended."""
        if before not in IN_MATCH or after in IN_MATCH or not match_id or match_id in self.running:
            return False
        self.running.add(match_id)
        threading.Thread(target=self.follow, args=(int(match_id), hero), daemon=True, name=f"after-{match_id}").start()
        return True

    def follow(self, match_id: int, hero: int | None) -> None:
        try:
            self.sleep(FIRST_WAIT)
            start = self.now()
            raw = None
            while raw is None and self.now() - start < LOOK_FOR:
                try:
                    raw = ruin.fetch(match_id, refresh=True)
                except ruin.RuinError:
                    self.sleep(RETRY)
            if raw is None:
                return
            self._announce(raw, hero)
            start = self.now()
            while not ruin.analyze(raw).get("parsed") and self.now() - start < PARSE_FOR:
                if (raw.get("parse") or {}).get("state") == "unavailable":
                    break
                self.sleep(PARSE_RETRY)
                try:
                    raw = ruin.fetch(match_id, refresh=True)
                except ruin.RuinError:
                    continue
                if ruin.analyze(raw).get("parsed"):
                    self._announce(raw, hero)
        finally:
            self.running.discard(str(match_id))

    def _announce(self, raw: dict, hero: int | None) -> None:
        analysis = ruin.analyze(raw)
        e = record(analysis, self.account_id(), hero)
        self.publish("ruin", match_id=analysis["id"], entry=e, parsed=bool(analysis.get("parsed")),
                     verdict=analysis.get("verdict"))


def backfill(log, account_id: int | None = None) -> None:
    """The user's rating for the last BACKFILL ranked matches of the history (a job)."""
    from .data import me
    account_id = account_id or config.settings().account_id
    data = me.load()
    if not data or not account_id:
        raise RuntimeError("нет истории или аккаунта: укажи Steam ID и обнови историю")
    have = load()
    todo = [m for m in sorted(data["matches"], key=lambda m: -(m.get("start_time") or 0))[:BACKFILL]
            if str(m["match_id"]) not in have]
    log(f"Матчей разобрать: {len(todo)}")
    for n, m in enumerate(todo, 1):
        try:
            raw = ruin.fetch(int(m["match_id"]))
        except ruin.RuinError as e:
            log(f"{m['match_id']}: {e}")
            continue
        record(ruin.analyze(raw), account_id, m.get("hero_id"))
        log(f"{n} из {len(todo)}")
