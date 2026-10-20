/**
 * The browser side of grid art: a text or a picture drawn on a small canvas, read back as cells.
 */
import { artSize, cellsToRows, drawLight, toneCells, type Cells } from './art.ts';
import type { ImageArtSource, TextArtSource } from './doc.ts';

/** Default line step: Radiance's capitals take about 12 units of a label. */
export const ART_STEP = 12;

export interface ArtResult {
  rows: { dx: number; text: string }[];
  step: number;
  w: number;
  h: number;
  cells: Cells;
}

function finish(cells: Cells, pitch: number, step: number): ArtResult {
  return { rows: cellsToRows(cells, pitch), step, cells, ...artSize(cells, pitch, step) };
}

/** Rendered at K× and averaged per cell: thin strokes still light their cells, edges stay clean. */
const K = 6;

/** Big letters: the text in a bold font, `size` symbols tall, each lit cell one glyph. */
export function textArt(s: TextArtSource): ArtResult {
  const size = Math.max(3, Math.min(48, Math.round(s.size)));
  const font = `${s.bold ? 800 : 600} ${size * K}px Onest Variable, Onest, Arial, sans-serif`;
  // a little air between letters, or bold capitals melt together at a few symbols tall
  const spacing = `${Math.max(1, Math.round(size * 0.12)) * K}px`;
  const probe = document.createElement('canvas').getContext('2d')!;
  probe.font = font;
  probe.letterSpacing = spacing;
  const lines = s.text.split('\n');
  const lineH = Math.round(size * 1.25);
  // cells are pitch wide and step tall: squeeze the text across so letters keep their shape
  const sx = s.step / Math.max(1, s.pitch);
  const widest = Math.max(...lines.map((l) => probe.measureText(l).width));
  const cols = Math.max(1, Math.ceil((widest * sx) / K) + 1);
  const rows = Math.max(1, lineH * lines.length + Math.ceil(size * 0.3));
  const canvas = document.createElement('canvas');
  canvas.width = cols * K;
  canvas.height = rows * K;
  const g = canvas.getContext('2d', { willReadFrequently: true })!;
  g.font = font;
  g.letterSpacing = spacing;
  g.textBaseline = 'alphabetic';
  g.fillStyle = '#000';
  g.scale(sx, 1);
  lines.forEach((l, i) => g.fillText(l, 0, (i * lineH + size) * K));
  const px = g.getImageData(0, 0, cols * K, rows * K).data;
  const data: string[] = [];
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) {
      let sum = 0;
      for (let y = 0; y < K; y++) for (let x = 0; x < K; x++) sum += px[((r * K + y) * cols * K + c * K + x) * 4 + 3];
      data.push(sum / (K * K * 255) > 0.38 ? s.glyph : ' ');
    }
  return finish(trim({ cols, rows, data }), s.pitch, s.step);
}

/** Empty columns and rows around the art taken off. */
function trim(c: Cells): Cells {
  let [left, top, right, bottom] = [c.cols, c.rows, 0, 0];
  for (let r = 0; r < c.rows; r++)
    for (let k = 0; k < c.cols; k++)
      if (c.data[r * c.cols + k] !== ' ') {
        left = Math.min(left, k);
        top = Math.min(top, r);
        right = Math.max(right, k + 1);
        bottom = Math.max(bottom, r + 1);
      }
  if (right <= left) return { cols: 1, rows: 1, data: [' '] };
  const data: string[] = [];
  for (let r = top; r < bottom; r++) data.push(...c.data.slice(r * c.cols + left, r * c.cols + right));
  return { cols: right - left, rows: bottom - top, data };
}

/** A picture in symbols: `cols` across, as many lines as its proportions need. */
export function imageArt(bmp: ImageBitmap, s: ImageArtSource): ArtResult {
  const cols = Math.max(4, Math.min(220, Math.round(s.cols)));
  // a cell is pitch wide and step tall: fewer lines than columns for the same proportions
  const rows = Math.max(1, Math.round((cols * s.pitch * bmp.height) / (bmp.width * s.step)));
  const canvas = document.createElement('canvas');
  canvas.width = cols;
  canvas.height = rows;
  const g = canvas.getContext('2d', { willReadFrequently: true })!;
  g.fillStyle = '#fff';
  g.fillRect(0, 0, cols, rows);
  g.imageSmoothingQuality = 'high';
  g.drawImage(bmp, 0, 0, cols, rows);
  const px = g.getImageData(0, 0, cols, rows).data;
  const tones = new Float32Array(cols * rows);
  for (let i = 0; i < tones.length; i++) tones[i] = 1 - (0.299 * px[i * 4] + 0.587 * px[i * 4 + 1] + 0.114 * px[i * 4 + 2]) / 255;
  // the user's «invert» flips the automatic choice of what to draw
  const light = drawLight(tones, cols, rows) !== s.invert;
  return finish(toneCells(tones, cols, rows, { ...s, invert: light }), s.pitch, s.step);
}

/** Symbols across for a picture to fit the grid with a margin. */
export function fitCols(bmp: { width: number; height: number }, pitch: number): number {
  const byWidth = 1100 / pitch;
  const byHeight = (560 * bmp.width) / (bmp.height * pitch);
  return Math.max(10, Math.min(200, Math.floor(Math.min(byWidth, byHeight))));
}
