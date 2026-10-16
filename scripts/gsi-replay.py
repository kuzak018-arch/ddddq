"""Replay a Dota match to the GSI receiver without the game (dev check).

Usage (backend running):  ..\\.venv\\Scripts\\python ..\\scripts\\gsi-replay.py [log.jsonl] [--speed 10]
Without a log file it sends a short synthetic match: hero selection -> pick -> game -> post game.
With a log from data/gsi/*.jsonl it replays a real recorded match.
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from drafter import gsi  # noqa: E402


def post(payload: dict, port: int) -> int:
    body = json.dumps({**payload, "auth": {"token": gsi._token()}}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/", data=body, method="POST")
    return urllib.request.urlopen(req, timeout=5).status


def synthetic():
    base = {"provider": {"name": "Dota 2", "appid": 570}, "player": {"team_name": "dire", "activity": "playing"}}
    m = lambda state: {"matchid": "9999000001", "game_state": state}
    yield {**base, "map": m("DOTA_GAMERULES_STATE_HERO_SELECTION"), "hero": {"id": 0}}
    yield {**base, "map": m("DOTA_GAMERULES_STATE_HERO_SELECTION"), "hero": {"id": 4, "name": "npc_dota_hero_bloodseeker"}}
    yield {**base, "map": m("DOTA_GAMERULES_STATE_STRATEGY_TIME"), "hero": {"id": 4, "name": "npc_dota_hero_bloodseeker"}}
    yield {**base, "map": m("DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"), "hero": {"id": 4, "name": "npc_dota_hero_bloodseeker"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", nargs="?")
    ap.add_argument("--port", type=int, default=gsi.PORT)
    ap.add_argument("--speed", type=float, default=10.0, help="во сколько раз быстрее реального времени")
    ap.add_argument("--pause", type=float, default=1.0, help="пауза между шагами синтетического матча, с")
    args = ap.parse_args()
    if args.log:
        rows = [json.loads(line) for line in Path(args.log).read_text(encoding="utf-8").splitlines() if line.strip()]
        t0 = rows[0]["ts"]
        start = time.time()
        for r in rows:
            time.sleep(max(0.0, (r["ts"] - t0) / args.speed - (time.time() - start)))
            post({k: v for k, v in r.items() if k != "ts"}, args.port)
        print(f"отправлено {len(rows)} сообщений")
    else:
        for p in synthetic():
            print(p["map"]["game_state"], "->", post(p, args.port))
            time.sleep(args.pause)


if __name__ == "__main__":
    main()
