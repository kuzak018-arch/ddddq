"""Command line entry point: `python -m drafter.cli <command>` from the backend folder."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version

import httpx

from . import config, dota_paths

RANKS = ["", "Herald", "Guardian", "Crusader", "Archon", "Legend", "Ancient", "Divine", "Immortal"]


def rank_name(rank_tier: int | None) -> str:
    if not rank_tier:
        return "нет данных"
    tier, star = divmod(rank_tier, 10)
    return f"{RANKS[tier]} {star}" if 0 < tier < len(RANKS) else str(rank_tier)


def _tool_version(cmd: list[str]) -> str:
    if shutil.which(cmd[0]) is None:
        return "НЕ НАЙДЕН"
    out = subprocess.run(cmd, capture_output=True, text=True)
    return (out.stdout or out.stderr).strip().splitlines()[0]


def doctor() -> int:
    s = config.settings()
    problems: list[str] = []

    def line(name: str, value: object, ok: bool = True) -> None:
        print(f"  {'✓' if ok else '✗'} {name:<22} {value}")
        if not ok:
            problems.append(f"{name}: {value}")

    print("Инструменты")
    line("python", sys.version.split()[0])
    for pkg in ("fastapi", "duckdb", "polars", "lightgbm", "scikit-learn", "opencv-python", "windows-capture"):
        line(pkg, version(pkg))
    for cmd in (["node", "--version"], ["cargo", "--version"]):
        v = _tool_version(cmd)
        line(cmd[0], v, v != "НЕ НАЙДЕН")

    print("Данные")
    with httpx.Client(timeout=20, headers={"User-Agent": config.USER_AGENT}) as http:
        try:
            r = http.get(f"{config.OPENDOTA}/constants/patch")
            day_left = r.headers.get("X-Rate-Limit-Remaining-Day", "?")
            line("OpenDota", f"HTTP {r.status_code}, осталось запросов на сегодня: {day_left}", r.is_success)
        except httpx.HTTPError as e:
            line("OpenDota", e, False)

        try:
            patches = http.get(config.VALVE_PATCHES).json()["patches"]
            last = patches[-1]
            date = datetime.fromtimestamp(last["patch_timestamp"], timezone.utc).date()
            line("патч", f"{last['patch_name']} от {date}")
        except (httpx.HTTPError, KeyError, ValueError) as e:
            line("патч", e, False)

        if s.stratz_token:
            try:
                r = http.post(
                    config.STRATZ,
                    json={"query": "{ constants { gameVersions(take: 1) { name asOfDateTime } } }"},
                    headers={"Authorization": f"Bearer {s.stratz_token}", "User-Agent": "STRATZ_API"},
                )
                ok = r.is_success and "errors" not in r.json()
                line("Stratz", "токен работает" if ok else f"HTTP {r.status_code}: {r.text[:120]}", ok)
            except (httpx.HTTPError, ValueError) as e:
                line("Stratz", e, False)
        else:
            line("Stratz", "токена нет: впиши STRATZ_TOKEN в .env", False)

        if s.account_id:
            try:
                p = http.get(f"{config.OPENDOTA}/players/{s.account_id}").json()
                prof = p.get("profile") or {}
                name = prof.get("personaname", "?")
                line("аккаунт", f"{s.account_id} ({name}), ранг: {rank_name(p.get('rank_tier'))}")
                wl = http.get(f"{config.OPENDOTA}/players/{s.account_id}/wl", params={"date": 30}).json()
                games = wl.get("win", 0) + wl.get("lose", 0)
                line("матчи за 30 дней", games if games else "0: включи Expose Public Match Data в Доте", games > 0)
            except (httpx.HTTPError, ValueError) as e:
                line("аккаунт", e, False)
        else:
            line("аккаунт", "впиши DOTA_ACCOUNT_ID в .env", False)

    print("Dota 2")
    dota = dota_paths.dota_path()
    line("установка", dota or "не найдена", dota is not None)
    if dota:
        gsi = dota_paths.gsi_dir(dota)
        cfgs = sorted(p.name for p in gsi.glob("*.cfg")) if gsi.is_dir() else []
        line("конфиги GSI", ", ".join(cfgs) or "нет")
    if s.account_id:
        vm = dota_paths.video_mode(s.account_id)
        if vm:
            line("режим окна", f"{vm.width}×{vm.height}, {vm.label}", not vm.fullscreen)
        else:
            line("режим окна", "video.txt не найден", False)

    print()
    if problems:
        print(f"Проблем: {len(problems)}")
        return 1
    print("Всё готово.")
    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="drafter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="проверить окружение, доступ к данным и настройки Доты")
    args = ap.parse_args()
    if args.cmd == "doctor":
        sys.exit(doctor())


if __name__ == "__main__":
    main()
