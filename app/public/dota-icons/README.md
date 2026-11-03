Значки из клиента Dota 2 (© Valve Corporation), без изменений, кроме размера медалей:

- `attr/{str,agi,int,all}.png` — значки атрибутов, из github.com/linsisss/dota2-grid-toolkit (assets/attributes).
  (Позиции показываются цифрой с подписью роли, значки позиций больше не нужны.)
- `plus.webp` — логотип Dota Plus, оттуда же (`panorama/images/dota_plus/dotaplus_logo_png`).
- `ranks/medal_N.webp` и `ranks/stars_N.webp` — медали рангов и звёзды поверх них (медаль 8b — топ-100
  таблицы лидеров, 8c — топ-10), из github.com/odota/web (public/assets/images/dota2/rank_icons),
  уменьшены с 256 до 128 px.

Значки позиций белые и ставятся маской (`mask-image`), поэтому берут цвет текста.
