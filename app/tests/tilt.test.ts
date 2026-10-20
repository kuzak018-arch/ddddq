import assert from 'node:assert/strict';
import { test } from 'node:test';

import { tiltAngles } from '../src/lib/tilt.ts';

test('a card leans towards the pointer, flat in the middle, at most max at the edges', () => {
  assert.deepEqual(tiltAngles(100, 50, 200, 100), { rx: 0, ry: 0 });
  assert.deepEqual(tiltAngles(200, 50, 200, 100, 8), { rx: 0, ry: 8 });   // right edge: right side goes down
  assert.deepEqual(tiltAngles(100, 0, 200, 100, 8), { rx: 8, ry: 0 });     // top edge: top tips back
  assert.deepEqual(tiltAngles(-50, 500, 200, 100, 8), { rx: -8, ry: -8 }); // outside: clamped
});
