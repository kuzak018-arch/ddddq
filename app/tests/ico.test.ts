import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildIco, readIco } from '../src/lib/ico.ts';

const png = (n: number, fill: number) => new Uint8Array([0x89, 0x50, 0x4e, 0x47, ...new Array(n).fill(fill)]);

test('ico header and entries point at each PNG', () => {
  const images = [
    { size: 16, png: png(10, 1) },
    { size: 48, png: png(20, 2) },
    { size: 256, png: png(30, 3) },
  ];
  const ico = buildIco(images);
  assert.deepEqual([...ico.slice(0, 6)], [0, 0, 1, 0, 3, 0]);
  const entries = readIco(ico);
  assert.deepEqual(entries.map((e) => e.size), [16, 48, 256]);
  assert.equal(entries[0].offset, 6 + 16 * 3);
  entries.forEach((e, i) => {
    assert.equal(e.length, images[i].png.length);
    assert.deepEqual([...ico.slice(e.offset, e.offset + e.length)], [...images[i].png]);
  });
  assert.equal(ico.length, entries[2].offset + entries[2].length);
});

test('256 is written as 0 in the one-byte size fields', () => {
  const ico = buildIco([{ size: 256, png: png(4, 0) }]);
  assert.equal(ico[6], 0);
  assert.equal(ico[7], 0);
  assert.equal(ico[6 + 6], 32); // bits per pixel
});
