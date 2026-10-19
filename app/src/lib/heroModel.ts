/**
 * Is a decoded frame a real cut-out (the hero model alone on a transparent background)? The same
 * rule as the backend's renders.transparent: clear border, a solid model in the middle.
 */
export function isCutOut(rgba: Uint8ClampedArray | Uint8Array, w: number, h: number): boolean {
  if (w < 8 || h < 8 || rgba.length < w * h * 4) return false;
  const b = Math.max(2, Math.floor(Math.min(w, h) / 40));
  let border = 0;
  let borderN = 0;
  let opaque = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const a = rgba[(y * w + x) * 4 + 3]! / 255;
      if (a > 0.9) opaque++;
      if (y < b || y >= h - b || x < b || x >= w - b) {
        border += a;
        borderN++;
      }
    }
  }
  const share = opaque / (w * h);
  return border / borderN < 0.03 && share > 0.03 && share < 0.9;
}

export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * The still is the render's frame with its empty margins cut off (crop: the kept box as fractions
 * of the frame), shown contained in a W×H box, centred and standing on the bottom edge. Where must
 * the whole video frame go so that its model lands exactly on the still?
 */
export function placeStill(W: number, H: number, crop: [number, number, number, number], frame: [number, number]): { still: Box; video: Box } {
  const [cx, cy, cw, ch] = crop;
  const sw = cw * frame[0];
  const sh = ch * frame[1];
  const s = Math.min(W / sw, H / sh);
  const still = { width: sw * s, height: sh * s, left: (W - sw * s) / 2, top: H - sh * s };
  const video = {
    width: frame[0] * s,
    height: frame[1] * s,
    left: still.left - cx * frame[0] * s,
    top: still.top - cy * frame[1] * s,
  };
  return { still, video };
}
