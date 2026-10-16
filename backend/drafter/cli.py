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
    c = sub.add_parser("constants", help="скачать героев, предметы, способности, патчи и иконки")
    c.add_argument("--no-icons", action="store_true")
    m = sub.add_parser("collect", help="собрать ранговые матчи All Pick текущего патча (можно прерывать)")
    m.add_argument("--days", type=int, help="вместо начала патча взять последние N дней")
    sub.add_parser("status", help="сколько матчей собрано")
    sub.add_parser("me", help="обновить мою историю матчей из OpenDota")
    sub.add_parser("positions", help="оценить позиции героев по составам команд (EM)")
    t = sub.add_parser("train", help="обучить и проверить модели, записать отчёт")
    t.add_argument("--max-train", type=int, default=4_000_000)
    sg = sub.add_parser("suggest", help="вероятность победы, подбор героя и баны для драфта")
    sg.add_argument("--allies", default="", help="союзники через запятую: 'ам, пудж'")
    sg.add_argument("--enemies", default="")
    sg.add_argument("--bans", default="")
    sg.add_argument("--pos", type=int, required=True, choices=range(1, 6))
    sg.add_argument("--side", choices=["radiant", "dire"])
    sg.add_argument("--rank", type=int, help="rank_tier, например 61; по умолчанию из профиля")
    sg.add_argument("--no-comfort", action="store_true", help="не учитывать мой опыт на героях")
    sg.add_argument("--comfort-weight", type=float, default=0.5,
                    help="доля личной кривой опыта в оценке (0..1), по умолчанию 0.5")
    sub.add_parser("tags", help="пересобрать теги героев (shared/hero_tags.json)")
    vs = sub.add_parser("vision-synth", help="сгенерировать синтетические кадры драфта для проверки распознавания")
    vs.add_argument("--frames", type=int, default=40)
    sub.add_parser("vision-eval", help="точность распознавания на подтверждённых и синтетических кадрах -> reports/vision.md")
    st = sub.add_parser("stratz", help="скачать позиции, баны и билды из Stratz для брекета")
    st.add_argument("--bracket", choices=["HERALD_GUARDIAN", "CRUSADER_ARCHON", "LEGEND_ANCIENT", "DIVINE_IMMORTAL"])
    bd = sub.add_parser("build", help="билд героя на позицию, при --enemies с правками против драфта")
    bd.add_argument("--hero", required=True)
    bd.add_argument("--pos", type=int, required=True, choices=range(1, 6))
    bd.add_argument("--enemies", default="")
    b = sub.add_parser("counter", help="ситуативные предметы против вражеского драфта")
    b.add_argument("--enemies", required=True)
    b.add_argument("--pos", type=int, required=True, choices=range(1, 6))
    args = ap.parse_args()

    if args.cmd == "doctor":
        sys.exit(doctor())
    elif args.cmd == "constants":
        from .data import constants
        constants.refresh(icons=not args.no_icons)
    elif args.cmd == "collect":
        import time
        from .data import constants, matches
        since = int(time.time()) - args.days * 86400 if args.days else constants.current_patch()["ts"]
        matches.collect(since, log=lambda s: print(s, flush=True))
    elif args.cmd == "status":
        from .data import matches
        for k, v in matches.summary().items():
            print(f"  {k:<14} {v:,}" if isinstance(v, int) and not isinstance(v, bool) else f"  {k:<14} {v}")
    elif args.cmd == "me":
        from .data import me
        d = me.refresh()
        print(f"  матчей: {len(d['matches'])}, ранг: {rank_name(me.rank_tier(d))}")
    elif args.cmd == "positions":
        from .model import positions
        positions.run(log=lambda s: print(s, flush=True))
    elif args.cmd == "train":
        from .model import report, train
        meta = train.run(max_train=args.max_train, log=lambda s: print(s, flush=True))
        print(f"  отчёт: {report.write(meta)}")
    elif args.cmd == "suggest":
        suggest_cmd(args)
    elif args.cmd == "stratz":
        from .data import me, stratz
        stratz.fetch(args.bracket or stratz.bracket_for(me.rank_tier()), log=lambda s: print(s, flush=True))
    elif args.cmd == "build":
        build_cmd(args)
    elif args.cmd == "vision-synth":
        from .vision import evaluate
        print(f"  кадры: {evaluate.synthetic(args.frames)}")
    elif args.cmd == "vision-eval":
        from .vision import evaluate
        results = [evaluate.evaluate(f) for f in (evaluate.LABELED, evaluate.SYNTH) if f.exists() and any(f.glob("*.json"))]
        for r in results:
            p = "—" if r["precision"] is None else f"{r['precision']:.1%}"
            rc = "—" if r["recall"] is None else f"{r['recall']:.1%}"
            print(f"  {r['folder']}: кадров {r['frames']}, точность {p}, полнота {rc}")
        print(f"  отчёт: {evaluate.write_report(results)}")
    elif args.cmd == "tags":
        from .builds import tags
        print(f"  героев с тегами: {len(tags.build())}")
    elif args.cmd == "counter":
        from . import search
        from .builds import counter
        from .model import positions
        import numpy as np
        enemies = [search.resolve(x) for x in args.enemies.split(",") if x.strip()]
        pos = positions.load()
        pos_mat = np.zeros((max(pos) + 1, 5))
        for h, v in pos.items():
            pos_mat[h] = v
        for r in counter.against(enemies, args.pos, pos_mat):
            print(f"  {r['name']:<22} {r['cost']:>5}  ({r['score']})")
            for why in r["reasons"]:
                print(f"      · {why['text']}")


def build_cmd(args) -> None:
    from . import search
    from .builds import counter, standard
    from .data import me, stratz
    from .model import predictor

    hero = search.resolve(args.hero)
    bracket = stratz.bracket_for(me.rank_tier())
    b = standard.build(hero, args.pos, bracket)
    name = predictor.constants.hero_by_id()[hero]["name"]
    if not b:
        print(f"Нет данных Stratz для {name} на позиции {args.pos} ({bracket}): запусти `drafter.cli stratz`")
        return
    wr = f", винрейт {b['hero_wr'] * 100:.1f}%" if b["hero_wr"] else ""
    print(f"{name}, позиция {args.pos}, {bracket}: {b['matches']:,} матчей за неделю {b['week']}{wr}")

    def items(xs, timing=True):
        return "; ".join(
            x["name"] + (f" ×{x['count']}" if x.get("count", 1) > 1 else "")
            + (f" (~{x['minute']:g} мин, {x['share'] * 100:.0f}%, WR {x['wr'] * 100:.0f}%)" if timing and "minute" in x
               else f" ({x['share'] * 100:.0f}%)")
            for x in xs) or "—"

    print(f"\nСтарт: {items(b['starting'], False)}")
    print(f"Сапоги: {items(b['boots'])}")
    print(f"Ранние: {items(b['early'])}")
    print(f"Коровые: {items(b['core'])}")
    print(f"Ситуативные: {items(b['situational'])}")
    print("\nПрокачка (сначала максится):")
    for s in b["skills"]:
        print(f"  · {s['name']}: первый уровень на {s['first_level']}, макс к {s['max_level']}")
    print("Таланты:")
    for t in b["talents"]:
        opts = "  |  ".join(f"{o['name']} {o['share'] * 100:.0f}%" for o in t["options"])
        print(f"  {t['level']}: {opts}")
    if b["facets"]:
        print("Facets: " + ", ".join(f["title"] or f["name"] for f in b["facets"]))

    enemies = [search.resolve(x) for x in args.enemies.split(",") if x.strip()]
    if enemies:
        pr = predictor.get()
        recs = counter.against(enemies, args.pos, pr.pos_mat, hero_items=b["item_share"])
        have = {x["key"] for x in b["core"] + b["early"]}
        print(f"\nПротив {', '.join(pr.heroes[e]['name'] for e in enemies)}:")
        for r in recs:
            if r["item"] in have:
                mark = "уже в билде, держи в приоритете"
            elif r["hero_share"] is not None and r["hero_share"] < counter.RARE_ON_HERO:
                mark = "на этом герое почти не собирают"
            else:
                mark = f"добавь, собирают в {r['hero_share'] * 100:.0f}% игр" if r["hero_share"] else "добавь"
            print(f"  + {r['name']} ({mark})")
            for why in r["reasons"]:
                print(f"      · {why['text']}")


def suggest_cmd(args) -> None:
    from . import search
    from .data import constants, me
    from .model import draft, explain, predictor

    heroes = lambda s: [search.resolve(x) for x in s.split(",") if x.strip()]
    allies, enemies, bans = heroes(args.allies), heroes(args.enemies), heroes(args.bans)
    rank = args.rank or me.rank_tier() or 50
    group = int(draft.rank_group(rank))
    pool = None if args.no_comfort else me.hero_pool()
    pr = predictor.get()
    n = explain.name
    print(f"Ранг {rank_name(rank)}, позиция {args.pos}")
    print(f"Союзники: {', '.join(map(n, allies)) or '—'} | Враги: {', '.join(map(n, enemies)) or '—'}"
          f" | Баны: {', '.join(map(n, bans)) or '—'}")
    ev = pr.evaluate(allies, enemies, group, args.side)
    print(f"\nВероятность победы: {ev.p_win * 100:.1f}%")
    for t in ev.terms[:6]:
        print(f"  · {explain.term_text(t)}")
    res = pr.suggest(allies, enemies, bans, args.pos, group, args.side, pool, comfort_weight=args.comfort_weight)
    comfort = "выключен" if pool is None else f"вес {args.comfort_weight:g}"
    blocks = [(f"Топ-10 на позицию {args.pos} (учёт опыта: {comfort})", res["main"]),
              (f"Нестандартные на позицию {args.pos} (играют на ней 10–40% игр)", res["offrole"])]
    for title, rows in blocks:
        print(f"\n{title}:")
        for i, r in enumerate(rows, 1):
            print(f"{i:>2}. {n(r['hero']):<18} {r['p_win'] * 100:5.1f}% ({r['delta'] * 100:+.1f})  "
                  f"мета {r['meta_wr'] * 100:.1f}%, на позиции {r['pos_share'] * 100:.0f}% игр"
                  + (f", ⚠ пикают в {r['pick_rate'] * 100:.1f}% игр: винрейт за счёт специалистов"
                     if r["specialist"] else ""))
            for t in r["terms"][:4]:
                print(f"      · {explain.term_text(t)}")
    print("\nБаны:")
    for r in pr.bans(allies, enemies, bans, args.pos, group, pool):
        vs = f" (против {', '.join(map(n, r['against']))})" if r["against"] else ""
        print(f"  · {n(r['hero']):<18} пикают в {r['pick_rate'] * 100:.0f}% игр, вред {explain.pct(r['harm'])}{vs}")


if __name__ == "__main__":
    main()
