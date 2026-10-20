import assert from 'node:assert/strict';
import { test } from 'node:test';

import { LIVE_WALLS, liveSize } from '../src/lib/liveWalls.ts';

test('the live canvas is at most 1280 px across and keeps the window aspect', () => {
  assert.deepEqual(liveSize(1920, 1080), { w: 1280, h: 720 });
  assert.deepEqual(liveSize(1000, 700), { w: 1000, h: 700 });
  const s = liveSize(3440, 1440);
  assert.equal(s.w, 1280);
  assert.ok(Math.abs(s.w / s.h - 3440 / 1440) < 0.01);
  assert.deepEqual(liveSize(0, 0), { w: 2, h: 2 });
});

test('every live wallpaper has a unique id and a dark-enough luma', () => {
  assert.equal(new Set(LIVE_WALLS.map((w) => w.id)).size, LIVE_WALLS.length);
  for (const w of LIVE_WALLS) assert.ok(w.luma > 0 && w.luma < 0.3, w.id);
});
