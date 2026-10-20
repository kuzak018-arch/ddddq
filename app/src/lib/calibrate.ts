/**
 * Moving and resizing the slot rectangles of the screen-reading wizard (fractions of the frame).
 * Resizing a group scales the whole group from its top-left corner: positions spread with the
 * sizes, so neighbouring rectangles never slide over each other (resizing every rectangle in place
 * used to pile them up).
 */
export type Rect = [number, number, number, number];

const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
const MIN = 0.004;

/** Move rectangle `i` (or the whole group) by dx, dy; the group never leaves the frame. */
export function moveRects(start: Rect[], i: number, dx: number, dy: number, together: boolean): Rect[] {
  const idx = together ? start.map((_, k) => k) : [i];
  const minX = Math.min(...idx.map((k) => start[k]![0]));
  const minY = Math.min(...idx.map((k) => start[k]![1]));
  const maxX = Math.max(...idx.map((k) => start[k]![0] + start[k]![2]));
  const maxY = Math.max(...idx.map((k) => start[k]![1] + start[k]![3]));
  const ddx = clamp(dx, -minX, 1 - maxX);
  const ddy = clamp(dy, -minY, 1 - maxY);
  return start.map((r, k) => (idx.includes(k) ? ([r[0] + ddx, r[1] + ddy, r[2], r[3]] as Rect) : r));
}

/**
 * Resize by dragging the corner of rectangle `i` by dx, dy. Alone: that rectangle grows. Together:
 * the group scales by the same factor around its top-left corner, so its layout is kept.
 */
export function resizeRects(start: Rect[], i: number, dx: number, dy: number, together: boolean): Rect[] {
  const r0 = start[i]!;
  const w = Math.max(MIN, r0[2] + dx);
  const h = Math.max(MIN, r0[3] + dy);
  if (!together) return start.map((r, k) => (k === i ? ([r[0], r[1], w, h] as Rect) : r));
  let sx = w / r0[2];
  let sy = h / r0[3];
  const gx = Math.min(...start.map((r) => r[0]));
  const gy = Math.min(...start.map((r) => r[1]));
  const right = Math.max(...start.map((r) => r[0] + r[2]));
  const bottom = Math.max(...start.map((r) => r[1] + r[3]));
  // the scaled group must stay inside the frame
  sx = Math.min(sx, (1 - gx) / (right - gx));
  sy = Math.min(sy, (1 - gy) / (bottom - gy));
  return start.map((r) => [gx + (r[0] - gx) * sx, gy + (r[1] - gy) * sy, Math.max(MIN, r[2] * sx), Math.max(MIN, r[3] * sy)] as Rect);
}
