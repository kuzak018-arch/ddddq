import assert from 'node:assert/strict';
import { test } from 'node:test';

import { isCutOut } from '../src/lib/heroModel.ts';

function frame(w: number, h: number, alphaAt: (x: number, y: number) => number) {
  const d = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) d[(y * w + x) * 4 + 3] = alphaAt(x, y);
  return d;
}

test('a model on a transparent background is a cut-out, a full frame is not', () => {
  const w = 120;
  const h = 160;
  const model = frame(w, h, (x, y) => ((x - 60) ** 2 / 900 + (y - 90) ** 2 / 2500 < 1 ? 255 : 0));
  assert.equal(isCutOut(model, w, h), true);
  assert.equal(isCutOut(frame(w, h, () => 255), w, h), false); // a scene behind the model
  assert.equal(isCutOut(frame(w, h, () => 0), w, h), false); // nothing decoded (black, no alpha)
  // the model touching the border (a scene in the corners) is not a cut-out
  assert.equal(isCutOut(frame(w, h, (x, y) => (x < 10 || y < 10 ? 255 : (x - 60) ** 2 / 900 + (y - 90) ** 2 / 2500 < 1 ? 255 : 0)), w, h), false);
});

test('the video frame is placed so its model lands on the still', async () => {
  const { placeStill } = await import('../src/lib/heroModel.ts');
  // a 600x800 frame whose model sits in [150..450] x [100..800]
  const crop: [number, number, number, number] = [0.25, 0.125, 0.5, 0.875];
  const { still, video } = placeStill(190, 240, crop, [600, 800]);
  assert.ok(Math.abs(still.top + still.height - 240) < 1e-9); // stands on the bottom edge
  assert.ok(Math.abs(still.left + still.width / 2 - 95) < 1e-9); // centred
  const s = still.height / 700;
  // the model's box inside the placed video is exactly the still
  assert.ok(Math.abs(video.left + 150 * s - still.left) < 1e-9);
  assert.ok(Math.abs(video.top + 100 * s - still.top) < 1e-9);
  assert.ok(Math.abs(video.width - 600 * s) < 1e-9);
});
