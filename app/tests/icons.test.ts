import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { test } from 'node:test';

import { LEAVE_MS, PAGE_ANIMS, slideDir } from '../src/lib/pageAnim.ts';
import { medalFor } from '../src/lib/ranks.ts';

const pub = (p: string) => new URL(`../public/dota-icons/${p}`, import.meta.url);

test('a rank tier picks its medal and stars, Immortals by leaderboard place', () => {
  assert.deepEqual(medalFor(54), { medal: '5', stars: 4 });
  assert.deepEqual(medalFor(71), { medal: '7', stars: 1 });
  assert.deepEqual(medalFor(null), { medal: '0', stars: 0 });
  assert.deepEqual(medalFor(80), { medal: '8', stars: 0 });
  assert.deepEqual(medalFor(80, 1500), { medal: '8', stars: 0 });
  assert.deepEqual(medalFor(80, 57), { medal: '8b', stars: 0 });
  assert.deepEqual(medalFor(80, 3), { medal: '8c', stars: 0 });
});

test('every medal, star row, position and attribute icon the UI asks for is shipped', () => {
  for (let t = 0; t <= 8; t++) assert.ok(existsSync(pub(`ranks/medal_${t}.webp`)), `medal ${t}`);
  for (const m of ['8b', '8c']) assert.ok(existsSync(pub(`ranks/medal_${m}.webp`)));
  for (let s = 1; s <= 7; s++) assert.ok(existsSync(pub(`ranks/stars_${s}.webp`)), `stars ${s}`);
  for (let p = 1; p <= 5; p++) assert.ok(existsSync(pub(`roles/pos${p}.webp`)), `pos ${p}`);
  for (const a of ['str', 'agi', 'int', 'all']) assert.ok(existsSync(pub(`attr/${a}.png`)), a);
  assert.ok(existsSync(pub('plus.webp')));
});

test('a slide goes the way of the tab clicked', () => {
  assert.equal(slideDir('draft', 'meta'), 'fwd');
  assert.equal(slideDir('profile', 'meta'), 'back');
  assert.equal(slideDir('settings', 'draft'), 'back');
  assert.equal(slideDir('hero', 'builds'), 'fwd');    // the same tab: builds open «forward»
  assert.equal(slideDir('builds', 'hero'), 'back');
  assert.equal(slideDir('vision', 'profile'), 'back'); // the screen reader sits under the settings
  assert.equal(slideDir(null, 'meta'), 'fwd');
});

test('five animations and «off», each with its leave time', () => {
  assert.equal(PAGE_ANIMS.length, 6);
  assert.equal(PAGE_ANIMS.filter((a) => a.value !== 'none').length, 5);
  for (const a of PAGE_ANIMS) assert.ok(a.value in LEAVE_MS);
  assert.equal(LEAVE_MS.none, 0);
});
