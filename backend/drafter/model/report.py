"""Human-readable model report (reports/model.md) from data/model/meta.json."""

from __future__ import annotations

from .. import config

NAMES = {"baseline": "Бейзлайн (винрейты героев)", "lr": "Логистическая регрессия", "lgbm": "Бустинг (LightGBM)"}


def _row(name: str, m: dict, base: dict) -> str:
    d = base["logloss"] - m["logloss"]
    return (f"| {NAMES[name]} | {m['logloss']:.4f} | {d:+.4f} | {m['brier']:.4f} | {m['auc']:.4f} | "
            f"{m['acc'] * 100:.2f}% | {m['ece'] * 100:.2f}% |")


def write(meta: dict) -> str:
    r, d = meta["results"], meta["data"]
    lines = [
        "# Модель вероятности победы: отчёт",
        "",
        f"Обучено {meta['trained']}, патч {meta['patch']}, за {meta['seconds']} с.",
        "",
        f"Данные: {d['matches']:,} ранговых матчей All Pick (не короче 15 минут).",
        f"- обучение: {d['train']:,} ({d['train_period'][0]} — {d['train_period'][1]})",
        f"- валидация: {d['valid']:,} ({d['valid_period'][0]} — {d['valid_period'][1]})",
        f"- тест: {d['test']:,} ({d['test_period'][0]} — {d['test_period'][1]})",
        "",
        f"Винрейт Radiant на тесте: {r['radiant_wr_test'] * 100:.2f}%. "
        f"Синергии и контрпики посчитаны только на обучении (сглаживание k={meta['pair_k']:g}), "
        f"веса в регрессии: синергия {meta['lr_weights']['syn']:.2f}, контрпики {meta['lr_weights']['cnt']:.2f}. "
        f"Бустинг: {meta['gbm_trees']} деревьев. Все модели откалиброваны (Platt) на валидации.",
        "",
        "Как читать: **logloss** и **Brier** — меньше лучше; «Δ к бейзлайну» — насколько logloss лучше бейзлайна; "
        "**AUC** 0,5 — монетка; **ECE** — средняя ошибка калибровки (обещали 55% — выиграли 55%?).",
        "",
    ]
    hdr = ["| Модель | logloss | Δ к бейзлайну | Brier | AUC | Точность | ECE |", "|---|---|---|---|---|---|---|"]
    for stage, res in r["stages"].items():
        lines += [f"## Драфт {stage}", "", *hdr]
        lines += [_row(n, m, res["baseline"]) for n, m in res.items()]
        lines.append("")
    if r["ranks"]:
        lines += ["## Полный драфт по рангу", "", "| Ранг | Матчей | AUC бейзлайн | AUC регрессия | AUC бустинг | Точность регрессии |",
                  "|---|---|---|---|---|---|"]
        for rank, m in r["ranks"].items():
            lines.append(f"| {rank} | {m['n']:,} | {m['baseline']['auc']:.4f} | {m['lr']['auc']:.4f} | "
                         f"{m['lgbm']['auc']:.4f} | {m['lr']['acc'] * 100:.2f}% |")
        lines.append("")
    lines += ["## Калибровка регрессии (полный драфт, тест)", "", "| Обещано | Реально | Матчей |", "|---|---|---|"]
    lines += [f"| {c['pred'] * 100:.1f}% | {c['real'] * 100:.1f}% | {c['n']:,} |" for c in r["calibration_lr"]]
    lines.append("")
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    path = config.REPORTS / "model.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)
