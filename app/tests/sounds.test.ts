import assert from 'node:assert/strict';
import { test } from 'node:test';

import { boardSound, SOUNDS, soundLength } from '../src/lib/sounds.ts';

const b = (allies: (number | null)[], enemies: (number | null)[] = [], bans: number[] = []) => ({ allies, enemies, bans });

test('the board tells which sound to play', () => {
  assert.equal(boardSound(b([null]), b([1])), 'pick');
  assert.equal(boardSound(b([], [null]), b([], [7])), 'pick');
  assert.equal(boardSound(b([1]), b([1], [], [5])), 'ban');
  assert.equal(boardSound(b([1, 2]), b([1, null])), 'remove');
  assert.equal(boardSound(b([1, 2], [3], [4]), b([null, null], [null], [])), null); // a new match
  assert.equal(boardSound(b([1]), b([1])), null);
  assert.equal(boardSound(b([1, null]), b([null, 1])), null);                      // moved, not added
});

test('every sound is short and its notes are quiet enough', () => {
  for (const [name, notes] of Object.entries(SOUNDS)) {
    assert.ok(soundLength(name as keyof typeof SOUNDS) <= 0.8, name);
    for (const n of notes) assert.ok((n.gain ?? 0.3) <= 0.6 && n.freq > 50 && n.freq < 5000, name);
  }
});
