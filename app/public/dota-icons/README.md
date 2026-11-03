Значки из клиента Dota 2 (© Valve Corporation), без изменений, кроме размера медалей:

- `roles/pos1…5.webp` — значки позиций (керри, мид, оффлейн, четвёрка, пятёрка), из клиента:
  `panorama/images/rank_tier_icons/handicap/{safelane,midlane,offlane,softsupport,hardsupport}icon_psd`.
  Взяты из github.com/linsisss/dota2-grid-toolkit (assets/dota-menu-ui).
- `attr/{str,agi,int,all}.png` — значки атрибутов, оттуда же (assets/attributes).
- `plus.webp` — логотип Dota Plus, оттуда же (`panorama/images/dota_plus/dotaplus_logo_png`).
- `ranks/medal_N.webp` и `ranks/stars_N.webp` — медали рангов и звёзды поверх них (медаль 8b — топ-100
  таблицы лидеров, 8c — топ-10), из github.com/odota/web (public/assets/images/dota2/rank_icons),
  уменьшены с 256 до 128 px.

Значки позиций белые и ставятся маской (`mask-image`), поэтому берут цвет текста.
