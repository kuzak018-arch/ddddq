import assert from 'node:assert/strict';
import { test } from 'node:test';

import { CANVAS_W } from '../src/lib/grid/dota.ts';
import { ART_LINE_STEP, artRows, artToItems } from '../src/lib/workshop.ts';

test('a text art: one category per line, 20 units apart, empty lines skipped, centred', () => {
  const { items, w } = artToItems({ id: 1, name: 'Сердце', text: '  @@   @@\n@@@@@@@@@\n\n   @@@' });
  assert.equal(items.length, 3);
  assert.deepEqual(items.map((i) => i.y - items[0]!.y), [0, ART_LINE_STEP, 3 * ART_LINE_STEP]);
  assert.ok(Math.abs(items[0]!.x - (CANVAS_W - w) / 2) < 0.01);
  assert.ok(items.every((i) => i.type === 'text' && i.text.trim()));
});

test('an art from their editor keeps its rows where they were', () => {
  const rows = artRows({ id: 2, name: 'x', text: '', rows: [{ text: 'AB', x: 0, y: 0 }, { text: ' ', x: 5, y: 9 }, { text: 'C', x: 40, y: 30 }] });
  assert.deepEqual(rows, [{ text: 'AB', x: 0, y: 0 }, { text: 'C', x: 40, y: 30 }]);
  const { items } = artToItems({ id: 2, name: 'x', text: '', rows });
  assert.equal(Math.round((items[1]!.x - items[0]!.x) * 100) / 100, 40);
  assert.equal(items[1]!.y - items[0]!.y, 30);
});

test('nothing to place', () => {
  assert.deepEqual(artToItems({ id: 3, name: 'x', text: '\n  \n' }), { items: [], w: 0, h: 0 });
});

test('leading # (a translation key for Dota) are dropped without moving the rest of the line', () => {
  const { items } = artToItems({ id: 4, name: 'x', text: '@@@@\n##@@\n####' });
  assert.equal(items.length, 2);                      // a line of # only has nothing Dota would draw
  assert.equal(items[1]!.text, '@@');
  assert.ok(items[1]!.x > items[0]!.x);               // where the @@ were in the art
});
