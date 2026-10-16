"""The "refresh data after a patch" pipeline, run as a background job."""

from __future__ import annotations

import shutil

from .. import config
from ..data import constants, matches, me, stratz
from ..model import aggregates, positions, predictor, train

MIN_MATCHES_TO_TRAIN = 500_000


def clear_caches():
    predictor.get.cache_clear()
    constants.hero_index.cache_clear()
    from .. import search
    from ..builds import standard
    search._haystacks.cache_clear()
    standard._maps.cache_clear()


def run(log) -> None:
    log("1/7 константы, патчи, иконки, описания Valve…")
    constants.refresh(icons=True)
    clear_caches()
    patch = constants.current_patch()
    state = matches._state()
    if state and state.get("since_ts") != patch["ts"]:
        old = config.DATA / f"matches_before_{patch['name']}"
        log(f"новый патч {patch['name']}: старые матчи перенесены в {old.name}")
        if old.exists():
            shutil.rmtree(old)
        matches.DIR.rename(old)

    log(f"2/7 матчи с начала {patch['name']}…")
    matches.collect(patch["ts"], log=log)
    n = matches.summary().get("after_filters", 0)
    retrain = n >= MIN_MATCHES_TO_TRAIN
    if not retrain:
        log(f"⚠ матчей нового патча пока {n:,} (нужно от {MIN_MATCHES_TO_TRAIN:,}): модель не переобучаю, "
            "подсказки идут по старой. Запусти обновление через день-два.")

    log("3/7 дневные агрегаты для тир-листа…")
    aggregates.build(log=log)
    if retrain:
        log("4/7 позиции героев (EM)…")
        positions.run(log=log)
        log("5/7 обучение модели (около 10 минут)…")
        meta = train.run(log=log)
        from ..model import report
        report.write(meta)
        r = meta["results"]["stages"]["5v5"]
        log(f"   AUC регрессии {r['lr']['auc']:.3f} против бейзлайна {r['baseline']['auc']:.3f}")
    if config.settings().stratz_token:
        log("6/7 Stratz: позиции, баны, билды…")
        stratz.fetch(stratz.bracket_for(me.rank_tier()), log=log)
    else:
        log("6/7 Stratz пропущен: нет токена")
    if config.settings().account_id:
        log("7/7 моя история матчей…")
        me.refresh()
    else:
        log("7/7 история пропущена: не указан аккаунт")
    clear_caches()
    log("готово")
