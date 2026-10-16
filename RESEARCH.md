# Результаты исследования (16.10.2026)

Всё ниже проверено живыми запросами или найдено в источниках, ссылки в конце. Если начинаешь новую сессию, читай этот файл, а не исследуй заново.

## Патч

- Текущий патч **7.41f**, вышел 15.09.2026 (timestamp `1789455600`). 7.42 ещё не вышел, даты нет.
- OpenDota `/constants/patch` знает только `7.41` (24.03.2026), буквенные патчи не различает.
- Буквенные патчи есть в фиде Valve: `https://www.dota2.com/datafeed/patchnoteslist?language=english` (поле `patch_timestamp`). Используем его для определения начала патча.

## OpenDota

Лимиты без ключа (из заголовков ответа): 60 запросов в минуту, около 3000 в день (`X-Rate-Limit-Remaining-Day: 2967`).

| Эндпоинт | Что даёт | Годится? |
|---|---|---|
| `/explorer?sql=` по таблице `public_matches` | Все публичные матчи: `match_id, start_time, duration, lobby_type, game_mode, avg_rank_tier, num_rank_tier, radiant_win, radiant_team[], dire_team[]` | **Основной источник матчей.** 50 000 ранговых матчей за запрос: 0,8 с, 9 МБ JSON |
| `/publicMatches` | 100 матчей за запрос, все типы лобби вперемешку (ранговых около 27%) | Хуже explorer в сотни раз |
| `/heroStats` | Пики и победы по брекетам 1–8, тренд пабов за 7 дней (`pub_pick_trend`, `pub_win_trend`), баны **только про** | Для быстрого тир-листа и проверки |
| `/heroes/{id}/matchups` | Матчапы, но **только по про-матчам** (у Anti-Mage около 3,5 тыс. игр) | Нет, считаем сами |
| `/heroes/{id}/itemPopularity` | Предметы по фазам игры, малые выборки, без ранга | Только как запасной вариант |
| `/scenarios/laneRoles` | Линии, только разобранные матчи, малые выборки | Нет |
| `/constants/heroes`, `items`, `hero_abilities`, `abilities` | Герои, предметы, способности, таланты, facets | Да |
| `/players/{id}`, `/players/{id}/heroes`, `/players/{id}/matches` | Профиль, ранг, статистика по героям, история | Да, для личных данных (профиль должен быть открыт) |

Что выяснилось про explorer:
- Таймаут запроса около 15 с. `count(*)` за месяц не проходит, поэтому выгружаем страницами по `match_id` (`WHERE match_id < X ORDER BY match_id DESC LIMIT 50000`), это быстро.
- За последние сутки около **476 тыс.** ранговых матчей, у всех заполнены герои. С 7.41f накопилось порядка 14 млн.
- У самых свежих матчей (последние минуты) герои ещё нули, их отбрасываем.
- В выборке 50 тыс. ранговых All Pick нет ни одного матча с `avg_rank_tier` 80+ (Immortal). В `/heroStats` `8_pick = 0`. Immortal-брекета в открытых данных нет, для него берём Divine.
- Таблица `matches` (разобранные матчи) за 7 дней содержит **0** ранговых матчей, там только про-матчи. Поэтому позиций, покупок и порядка прокачки по пабам у OpenDota **нет**.
- Банов в пабах в `public_matches` нет.
- Распределение среднего ранга в выборке 50 тыс. (тир: матчей): 1: 707, 2: 2612, 3: 5599, 4: 10068, 5: 13232, 6: 8623, 7: 6717.

Facets: в `hero_abilities` 339 facets, из них 289 помечены `deprecated`. Активные facets остались у 20 героев. Показываем только активные.

## Stratz

- GraphQL `https://api.stratz.com/graphql`. Без токена ответ 403: «A bearer token is required». Токен бесплатный, его выдают на stratz.com/api после входа через Steam.
- По старому посту Stratz: обычный токен даёт около 2000 запросов в час, «Individual» вдвое больше (4000 в час, 20 000 в день). Пост без даты, лимиты нужно проверить.
- Чем Stratz лучше OpenDota для нас: статистика героев **по позициям 1–5** и брекетам, матчапы и синергии по брекетам, покупки предметов (стартовые, сапоги, полные предметы, нейтралки), таланты, порядок прокачки. У OpenDota по пабам этого нет вообще.
- Схему (точные имена полей) проверим интроспекцией, когда будет токен. Документация docs.stratz.com без браузера отдаёт 403.

**Позиции героев.** Надёжный источник — Stratz (позиции он определяет сам по каждому разобранному матчу). Запасной вариант без Stratz: EM-оценка `P(позиция | герой)` по нашим матчам. Каждая команда из 5 героев раскладывается на позиции 1–5 перестановкой, всего 120 вариантов. Начальное приближение берём из ролей героев OpenDota. Сравним оба источника между собой.

## Правила Valve

- Февраль 2024: Valve закрыла просмотр профилей игроков на стадии драфта и отключила `record` и консольные команды, через которые читалось состояние клиента. Overwolf-помощник драфта после этого убрал данные во время драфта. Его разработчик сказал, что смысл действий Valve ясен: «no more draft stage information».
- Вывод для нас: **никаких данных о конкретных игроках соперника во время драфта** (профили, их винрейты на героях). Используем только общую статистику по героям (как подсказки Dota Plus) и то, что видно на экране. Память игры не читаем, ничего не внедряем, файлы игры не меняем.
- Официального правила о банах за такие программы не нашёл. Чтение экрана — серая зона, поэтому оно экспериментальное и отключаемое.

## Game State Integration

- Игроку GSI отдаёт только данные **своего** игрока. Данные всех игроков приходят только зрителю.
- Дойдёт ли блок `draft` до игрока в его собственном драфте, документация не говорит. Скорее всего, нет (только зрителю). **Проверим логгером на реальном матче.** Надёжно ожидаем стадию игры (`map.game_state`), свою команду, своего героя после пика и время.
- У тебя уже лежит конфиг от прошлой попытки: `...\dota 2 beta\game\dota\cfg\gamestate_integration\gamestate_integration_drafthelper.cfg` (порт 47821, `draft "1"`). Рядом конфиг Logitech.

## Оверлей (Tauri 2)

- `window-vibrancy`: `apply_acrylic` работает на Windows 10/11. Тормоза при перетаскивании указаны для Windows 10 1903+ и Windows 11 build 22000. У тебя build 26200, это не тот случай. `apply_mica` есть только на Windows 11, и Mica окрашивается **по обоям рабочего стола, а не по окну под ним**. Значит, для размытия игры под оверлеем подходит только Acrylic.
- В конфиге окна нужен `transparent: true` и прозрачный `html, body`.
- Сквозные клики: `set_ignore_cursor_events(true)`. Когда они включены, окно не получает мышь, поэтому режим переключается горячей клавишей или опросом курсора из Rust.
- Глобальные клавиши: плагин `global-shortcut`. Выбранная комбинация перестаёт работать в игре, поэтому проверяем её по биндам Доты (файлы `user_keys_*_slot*.vcfg` в `Steam\userdata\<id>\570\local\cfg\`, только чтение).
- WebView2 построен на Chromium. `backdrop-filter` с SVG-фильтром (преломление) в нём работает, как в Chrome.

## Захват экрана

- `windows-capture` 2.0.1 (08.2026): Windows Graphics Capture, Python 3.9+, умеет захватывать **конкретное окно по имени**. В кадр попадает только окно Доты, а наш оверлей поверх неё нет. Это главное преимущество перед захватом монитора.
- Масштаб Windows 125% (логическое разрешение 2048×1152 при физическом 2560×1440). Бэкенду нужен per-monitor DPI awareness, иначе координаты зон съедут.

## Локальное окружение

- Windows 11 Home 10.0.26200. RTX 3060 Laptop. Монитор 2560×1440, 200 Гц, масштаб 125%.
- Python 3.13.3, Node 24.13.1, git, winget, Visual Studio Build Tools 2026 (C++), WebView2 155. **Rust не установлен** (нужен для Tauri).
- Dota 2: `D:\SteamLibrary\steamapps\common\dota 2 beta`. В `video.txt`: 2560×1440, `fullscreen 0`, `nowindowborder 1`, то есть уже «окно без рамки».
- Прошлый проект `C:\Users\kuzne\projects\dota2-tierlist` можно переиспользовать (копируем, оригинал не трогаем):
  - `scripts/data/hero-names.ts`: русские имена и сленг героев;
  - `scripts/data/item-meta.ts`: русские названия и сленг предметов;
  - `src/search.ts`: нормализация и исправление раскладки («згвпу» → Pudge);
  - `src/glass/refraction.ts`, `src/styles/glass.css`, `tokens.css`: Liquid Glass с преломлением через SDF-карту смещения;
  - `scripts/fetch-assets.ts`: иконки со Steam CDN в WebP.
- Русские описания способностей и предметов: локализация игры в репозитории SteamDatabase/GameTracking-Dota2 (`abilities_russian.txt`).

## Источники

- [Список патчей Dota 2](https://www.dota2.com/patches) и фид `dota2.com/datafeed/patchnoteslist`
- [timesaver.gg: статус 7.42](https://timesaver.gg/news/dota-2-next-patch-742-silent-update-september-29)
- [esports.gg: обновление, отключившее Overwolf](https://esports.gg/news/dota-2/dota-2-update-kills-third-party-applications-including-overwolf/)
- [game-tournaments: профили скрыты до конца драфта](https://game-tournaments.com/en/dota-2/news/44348-player-profiles-in-dota-2-now-cannot-be-seen-before-draft-ends-after-patch-to-make-overwolf-app-stop-working)
- [escorenews: разработчик закрыл помощь в драфте](https://escorenews.com/en/dota-2/news/44368-admiralbulldog-shows-on-stream-that-overwolf-still-works-on-same-day-it-was-patched-but-dev-announced-he-is-going-to-shut-draft-help-down-anyway)
- [Dota2GSI: данные игрока и зрителя](https://github.com/antonpup/Dota2GSI)
- [tauri-apps/window-vibrancy](https://github.com/tauri-apps/window-vibrancy)
- [Tauri issue #9250: сквозные клики](https://github.com/tauri-apps/tauri/issues/9250)
- [windows-capture на PyPI](https://pypi.org/project/windows-capture/)
- [Stratz: тарифы токенов](https://stratz.medium.com/stratz-api-major-update-5557335dbdfd)
