# Dota Drafter

Помощник драфта Dota 2 для Windows: вероятность победы по драфту с объяснением, подбор героя под твою роль, баны, мета по рангу, билды и предметы против вражеского драфта, оверлей поверх игры, Game State Integration и (экспериментально) чтение драфта с экрана.

> Фанатский некоммерческий проект, не связан с Valve. Память игры не читается и файлы игры не меняются. Добавляется только официальный конфиг GSI в `cfg/gamestate_integration`; по твоей кнопке приложение ещё записывает свои сетки героев в твой файл сеток в Steam (при закрытой Доте и с резервной копией). Данные: OpenDota, Stratz, Valve.

## Установка (для игры)

1. Скачай `Dota.Drafter_x.y.z_x64-setup.exe` из Releases репозитория (или собери сам, см. ниже) и запусти. Автообновления нет: новую версию ставь тем же способом поверх старой, данные сохраняются.
2. При первом запуске введи Steam ID (Friend ID из профиля Доты) и, по желанию, токен Stratz.
3. Перезапусти Доту, чтобы она подхватила конфиг GSI.
4. В Доте: «Окно без рамки». Ctrl+Shift+M показывает и скрывает оверлей, Ctrl+Shift+N включает сквозные клики. Клавиши меняются в настройках.

Данные пользователя хранятся в `%LOCALAPPDATA%\DotaDrafter` (`.env`, `data/`, `logs/`).

## Разработка

Нужны Python 3.13, Node 22+, Rust (MSVC), WebView2.

```
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
cd app
npm install
npm run tauri dev
```

`tauri dev` сам поднимает бэкенд из `.venv` на свободном порту со случайным токеном. Только бэкенд, со Swagger на http://127.0.0.1:47900/docs:

```
cd backend
..\.venv\Scripts\python -m drafter.api
```

| Команда (`cd backend`, `..\.venv\Scripts\python -m drafter.cli …`) | Что делает |
|---|---|
| `doctor` | проверка окружения, доступа к данным и настроек Доты |
| `constants` | герои, предметы, способности, патчи, иконки, русские описания Valve |
| `collect` | ранговые матчи All Pick текущего патча (OpenDota Explorer, можно прерывать) |
| `positions` / `train` | позиции героев (EM) и обучение модели с отчётом `reports/model.md` |
| `stratz` | позиции, баны, билды из Stratz для твоего брекета |
| `suggest`, `build`, `counter` | подсказки драфта и билды в консоли |
| `vision-synth`, `vision-eval` | проверка распознавания экрана, отчёт `reports/vision.md` |

Тесты: `cd backend` и `..\.venv\Scripts\python -m pytest -q`.

## Сборка установщика

```
.venv\Scripts\python -m PyInstaller backend\drafter-backend.spec --distpath build\backend\dist --workpath build\backend\work --noconfirm
cd app
npm run tauri build
```

PyInstaller собирает бэкенд в `build/backend/dist/drafter-backend/` вместе со стартовыми данными (константы, иконки, модель, Stratz). Tauri кладёт его в ресурсы и собирает установщик NSIS. Сырые матчи в установщик не входят: «Настройки → Обновить данные после патча» докачает их и переобучит модель.

На GitHub установщик собирает `.github/workflows/release.yml` по тегу `vX.Y.Z`: артефакт сборки и файл в GitHub Release `vX.Y.Z` этого (приватного) репозитория.

## Как устроено

- `backend/drafter`:
  - `data/` — OpenDota, Stratz, Valve, личная история;
  - `model/` — модель, подсказки, мета;
  - `builds/` — билды и правила против драфта;
  - `gsi.py`, `vision/` — интеграция с игрой и чтение экрана;
  - `hero_grid.py` — файл сеток героев Доты: чтение для импорта, безопасная запись наших сеток («Драфтер · »), копии;
  - `api/` — FastAPI и общий драфт для всех окон.
- `app/` — Tauri 2 (Rust: запуск бэкенда, окно-оверлей, Acrylic, глобальные клавиши, свой значок окон, трея и ярлыков) и React + TypeScript (Liquid Glass).
  - `src/lib/grid/` — модель сетки Доты для редактора «Сетки»: холст 1193×593, раскладка карточек, ширины символов шрифта Radiance (`radiance.json`, делает `scripts/radiance-metrics.mjs`), арт из текста и картинок.
- `shared/` — русские имена и сленг, теги героев, правила предметов.
- Сторонние части (GridStudio, GPL-3.0; ресурсы Valve) и что откуда взято — [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- Подробный план и журнал этапов — [PLAN.md](PLAN.md), исследование API — [RESEARCH.md](RESEARCH.md).
