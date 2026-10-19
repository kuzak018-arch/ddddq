// node --test --experimental-strip-types tests/  (npm test)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { assignPositions } from '../src/lib/positions.ts';

const SHARES: Record<number, number[]> = {
  26: [0, 0.01, 0.01, 0.2, 0.78], // Lion: support
  14: [0.01, 0.12, 0.07, 0.65, 0.15], // Pudge: roamer
  4: [0.9, 0.05, 0.03, 0.01, 0.01], // Bloodseeker: carry
  2: [0.01, 0.02, 0.92, 0.03, 0.02], // Axe: offlane
  1: [0.97, 0.02, 0.01, 0, 0], // Anti-Mage
};
const shares = (h: number) => SHARES[h];

test('picked heroes get their likely positions, empty slots the rest with mine first', () => {
  assert.deepEqual(assignPositions([26, 14, null, null, null], shares, { mine: 1 }), [5, 4, 1, 2, 3]);
  assert.deepEqual(assignPositions([26, 14, null, null, null], shares, { mine: 3 }), [5, 4, 3, 1, 2]);
});

test('positions are distinct even when two heroes want the same one', () => {
  const out = assignPositions([1, 4, null, null, null], shares, {});
  assert.equal(new Set(out).size, 5);
  assert.ok(out[0] === 1 || out[1] === 1);
});

test('a hero with a known position keeps it', () => {
  const out = assignPositions([4, 26, null, null, null], shares, { fixed: { hero: 26, pos: 4 }, mine: 4 });
  assert.equal(out[1], 4);
  assert.equal(out[0], 1);
  assert.equal(new Set(out).size, 5);
});

test('unknown heroes and a full team', () => {
  const out = assignPositions([4, 2, 26, 14, 999], shares, {});
  assert.deepEqual(out, [1, 3, 5, 4, 2]);
});
