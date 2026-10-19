/**
 * A template's categories (name + heroes) placed on the canvas: groups flow left to right and
 * wrap, all with one card scale — the largest at which everything fits on the 1193 × 593 canvas.
 */
import { CANVAS_H, CANVAS_W, CELL_W, HEADER, listSize } from './dota.ts';
import { newId, type GroupItem } from './doc.ts';

const MARGIN = 12;
const GAP = 10;

export function layoutGroups(cats: { name: string; heroes: number[] }[]): GroupItem[] {
  const usable = CANVAS_W - 2 * MARGIN;
  for (let scale = 1; scale >= 0.3; scale -= 0.02) {
    const placed: GroupItem[] = [];
    let x = MARGIN;
    let y = MARGIN;
    let rowH = 0;
    let fits = true;
    for (const c of cats) {
      const maxCols = Math.max(1, Math.floor((usable - 8) / (CELL_W * scale)));
      const { w, h } = listSize(c.heroes.length, Math.min(maxCols, Math.max(1, c.heroes.length)), scale);
      if (x + w > CANVAS_W - MARGIN + 0.01) {
        x = MARGIN;
        y += rowH + GAP;
        rowH = 0;
      }
      placed.push({ id: newId(), type: 'group', name: c.name, x, y, w, h, heroes: [...c.heroes] });
      x += w + GAP;
      rowH = Math.max(rowH, HEADER + h);
      if (y + HEADER + h > CANVAS_H - MARGIN + 0.01) {
        fits = false;
        break;
      }
    }
    if (fits) return placed;
  }
  throw new Error('шаблон не помещается на сетку');
}
