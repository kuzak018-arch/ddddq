import assert from 'node:assert/strict';
import { test } from 'node:test';

import { advances, cleanName, glyphWarnings, glyphXs, heroLayout, lineWidth, typesetRow } from '../src/lib/grid/dota.ts';

const near = (a: number, b: number, tol: number) => assert.ok(Math.abs(a - b) <= tol, `${a} vs ${b}`);

test('line widths match rows measured in the game (1920 × 1080 screenshot, published by GridStudio)', () => {
  const rows: [string, number][] = [
    ['WWWWWWWWWWWWWWWWWWWW', 335],
    ['IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII', 240.6],
    ['.........................................', 259.1],
    ['Ж Ш Щ Ж Ш Щ Ж Ш Щ Ж Ш Щ', 260.8],
    ['@  @  @  @  @  @  @  @', 197],
    ['·                                        ', 224.4],
    ['AVAVAVAVAVAVAVAVAV TATATATA', 282.8],
    ['/\\/\\/\\/\\/\\/\\/\\/\\/\\ ()()()', 177.9],
    ["LT.LT.LT.LT.'Y'Y'Y'Y P.P.P.", 235.3],
    ['%@$·•‹›0123456789 ;:-=+*^~!?', 260.8],
    ['.:-=+*%@ ЁЁЁ ЙЙЙ ЫЫЫ ЮЮЮ ЯЯЯ ...:::', 354.6],
  ];
  for (const [text, game] of rows) near(lineWidth(text), game, 1.5);
});

test('lower case is drawn as capitals', () => {
  assert.deepEqual(advances('abc'), advances('ABC'));
});

test('hero cards: the game fits them into the list with one scale', () => {
  // a game screenshot at 115 %: 74 × 129 portraits, 88 px pitch
  const l = heroLayout(488.695648, 132.17392, 5);
  assert.equal(l.cols, 5);
  assert.equal(l.rows, 1);
  near(l.cardW * 1.15, 74, 0.2);
  near(l.cardH * 1.15, 129, 0.1);
  near(l.stepX * 1.15, 88, 0.3);
  const tall = heroLayout(250, 340, 36);
  assert.equal(tall.cols, 7);
  assert.equal(tall.rows, 6);
});

test('a typeset row puts every glyph near its wanted place', () => {
  const want = [0, 20, 40, 60, 100, 160].map((x) => ({ ch: '#', x: 200 + x }));
  const row = typesetRow(want);
  assert.equal(row.x, 196);
  const xs = glyphXs(row.text).map((x) => x + row.x);
  const placed = Array.from(row.text).flatMap((c, i) => (c === ' ' ? [] : [xs[i]]));
  assert.equal(placed.length, want.length);
  placed.forEach((x, i) => near(x, want[i].x, 3));
  assert.ok(row.error <= 3);
});

test('names Dota cannot take are cleaned, invisible glyphs reported', () => {
  assert.equal(cleanName('#a<b>&c\nd'), 'abcd');
  assert.deepEqual(glyphWarnings('a█⠿★'), { invisible: ['█', '⠿'], foreign: ['★'] });
});

test('art cells become one line per row with symbols at their cells', async () => {
  const { cellsToRows, toneCells } = await import('../src/lib/grid/art.ts');
  const cells = { cols: 5, rows: 3, data: ['#', ' ', '#', ' ', '#', ' ', ' ', ' ', ' ', ' ', ' ', '#', ' ', ' ', ' '] };
  const rows = cellsToRows(cells, 12);
  assert.equal(rows.length, 3);
  assert.equal(rows[1].text, '');
  assert.equal(rows[2].dx, 12 - 4);
  const xs = glyphXs(rows[0].text).map((x) => x + rows[0].dx);
  const placed = Array.from(rows[0].text).flatMap((c, i) => (c === ' ' ? [] : [xs[i]]));
  placed.forEach((x, i) => near(x, i * 24, 3));
  const tones = toneCells([0, 0.5, 1, 1], 2, 2, { contrast: 1, brightness: 0, invert: false, ramp: ' .#' });
  assert.deepEqual(tones.data, [' ', '.', '#', '#']);
  assert.deepEqual(toneCells([0, 1], 2, 1, { contrast: 1, brightness: 0, invert: true, ramp: ' #' }).data, ['#', ' ']);
});

test('import keeps unknown fields and tells groups from captions; export gives them back', async () => {
  const { fromDota, parseFile, toDota } = await import('../src/lib/grid/doc.ts');
  const file = JSON.stringify({
    version: 3,
    configs: [
      {
        config_name: 'Драфтер · Моя',
        categories: [
          { category_name: 'Керри', x_position: 10, y_position: 20, width: 300, height: 90, hero_ids: [1, 2], hidden: false },
          { category_name: '##', x_position: 5, y_position: 400, width: 30, height: 30, hero_ids: [] },
        ],
        extra_field: 7,
      },
    ],
  });
  const [cfg] = parseFile('﻿' + file);
  const grid = fromDota(cfg, 'Драфтер · ');
  assert.equal(grid.name, 'Моя');
  assert.deepEqual(grid.items.map((i) => i.type), ['group', 'text']);
  const back = toDota(grid, 'Драфтер · ');
  assert.equal(back.config_name, 'Драфтер · Моя');
  assert.equal(back.extra_field, 7);
  assert.deepEqual(back.categories[0], cfg.categories[0]);
  // a leading # would be a localisation key in Dota: the caption is left out
  assert.equal(back.categories.length, 1);
  assert.throws(() => parseFile('{"version": 4, "configs": []}'));
});

test('a template is laid out on the canvas without overlaps', async () => {
  const { layoutGroups } = await import('../src/lib/grid/layout.ts');
  const { CANVAS_H, CANVAS_W, HEADER } = await import('../src/lib/grid/dota.ts');
  const ids = (n: number) => Array.from({ length: n }, (_, i) => i + 1);
  for (const cats of [
    [1, 2, 3, 4, 5].map((r) => ({ name: `Роль ${r}`, heroes: ids(18) })),
    ['S', 'A', 'B', 'C', 'D'].map((t) => ({ name: t, heroes: ids(26) })),
    [{ name: 'один', heroes: ids(1) }],
  ]) {
    const g = layoutGroups(cats);
    assert.equal(g.length, cats.length);
    for (const a of g) {
      assert.ok(a.x >= 0 && a.y >= 0 && a.x + a.w <= CANVAS_W && a.y + a.h + HEADER <= CANVAS_H, `${a.name} outside`);
      for (const b of g)
        if (a !== b) assert.ok(a.x + a.w <= b.x || b.x + b.w <= a.x || a.y + a.h + HEADER <= b.y || b.y + b.h + HEADER <= a.y, `${a.name} overlaps ${b.name}`);
    }
  }
});
