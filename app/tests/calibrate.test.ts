import assert from 'node:assert/strict';
import { test } from 'node:test';

import { moveRects, resizeRects, type Rect } from '../src/lib/calibrate.ts';

// five portraits in a row: 0.05 wide, 0.01 apart
const row: Rect[] = [0, 1, 2, 3, 4].map((k) => [0.3 + k * 0.06, 0.01, 0.05, 0.04] as Rect);
const close = (a: number, b: number) => Math.abs(a - b) < 1e-9;

test('resizing the group scales positions with sizes: no overlaps, same layout', () => {
  const out = resizeRects(row, 4, 0.01, 0.008, true); // the last corner, +20%
  for (let k = 0; k < 5; k++) {
    assert.ok(close(out[k]![2], 0.06) && close(out[k]![3], 0.048));
    if (k) assert.ok(out[k]![0] >= out[k - 1]![0] + out[k - 1]![2] - 1e-9, 'no overlap');
  }
  assert.ok(close(out[0]![0], 0.3) && close(out[0]![1], 0.01)); // anchored at the top-left
  assert.ok(close(out[1]![0] - out[0]![0], 0.072)); // the step grew by the same 20%
});

test('resizing alone changes one rectangle only', () => {
  const out = resizeRects(row, 2, 0.01, 0, false);
  assert.ok(close(out[2]![2], 0.06));
  assert.deepEqual(out[1], row[1]);
  assert.deepEqual(out[3], row[3]);
});

test('the group never leaves the frame', () => {
  const big = resizeRects(row, 4, 1, 1, true);
  const right = Math.max(...big.map((r) => r[0] + r[2]));
  const bottom = Math.max(...big.map((r) => r[1] + r[3]));
  assert.ok(right <= 1 + 1e-9 && bottom <= 1 + 1e-9);
  const moved = moveRects(row, 0, 2, -1, true);
  assert.ok(Math.max(...moved.map((r) => r[0] + r[2])) <= 1 + 1e-9 && Math.min(...moved.map((r) => r[1])) >= -1e-9);
  // the layout survives the clamp: steps stay equal
  assert.ok(close(moved[1]![0] - moved[0]![0], 0.06));
});

test('moving one rectangle leaves the others', () => {
  const out = moveRects(row, 1, 0.01, 0.01, false);
  assert.ok(close(out[1]![0], 0.37) && close(out[1]![1], 0.02));
  assert.deepEqual(out[0], row[0]);
});
