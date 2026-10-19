// Values checked against GridStudio's scripts/menu-background.mjs (the original of this port).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { fitPiece, framePlacement, mediaKind, menuLook, screenAspect } from '../src/lib/mods/frame.ts';

const near = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} vs ${b}`);

test('cover fills the screen, contain shows the whole picture', () => {
  // a square picture on 16:9: cover is screen-wide, contain screen-high
  const cover = framePlacement(16 / 9, 1, 'cover');
  near(cover.w, 1);
  near(cover.x, 0);
  assert.ok(cover.h > 1);
  const contain = framePlacement(16 / 9, 1, 'contain');
  near(contain.h, 1);
  near(contain.y, 0);
  near(contain.x, (1 - contain.w) / 2);
  // x = 0 puts the picture's left edge at the screen's
  near(framePlacement(16 / 9, 3, 'cover', 1, { x: 0, y: 0.5, zoom: 1 }).x, 0);
});

test('blur enlarges the picture and dims are capped', () => {
  const look = menuLook({ blur: 1, dim: 1 });
  near(look.sigma, 24);
  near(look.veil, 0.8);
  near(look.zoom, 1 + 120 / 1080);
  assert.deepEqual(menuLook({}), { sigma: 0, veil: 0, zoom: 1 });
});

test('a piece stays inside the video and under 30 seconds', () => {
  assert.deepEqual(fitPiece({ start: 0, end: 100 }, 100, 'end'), { start: 70, end: 100 });
  assert.deepEqual(fitPiece({ start: 5, end: 100 }, 100, 'start'), { start: 5, end: 35 });
  assert.deepEqual(fitPiece({ start: 9.8, end: 9.9 }, 10, 'end'), { start: 9, end: 10 });
});

test('files are told by their first bytes and screens by their shape', () => {
  assert.equal(mediaKind(new Uint8Array([0x89, 0x50, 0x4e, 0x47]))?.label, 'PNG');
  assert.equal(mediaKind(new TextEncoder().encode('GIF89a'))?.type, 'image');
  assert.equal(mediaKind(new Uint8Array([0, 0, 0, 0x20, 0x66, 0x74, 0x79, 0x70]))?.label, 'MP4');
  assert.equal(mediaKind(new Uint8Array([1, 2, 3, 4])), null);
  assert.equal(screenAspect(2560, 1440), '16:9');
  assert.equal(screenAspect(1920, 1200), '16:10');
  assert.equal(screenAspect(3440, 1440), '21:9');
});
