/**
 * Grid art: a picture of symbols, one empty category per line. A bitmap of cells (a symbol or
 * nothing in each) is turned into lines of symbols and spaces with dota.ts `typesetRow`, so every
 * symbol stands where its cell is, as close as the game's glyph widths allow.
 *
 * Only Radiance's own glyphs are offered: their widths in the game are known. Others are drawn by
 * a fallback font of unknown width, block elements and Braille are not drawn at all.
 */
import { advances, typesetRow } from './dota.ts';

export interface Cells {
  cols: number;
  rows: number;
  /** cols × rows symbols, '' or ' ' for an empty cell. */
  data: string[];
}

export interface Ramp {
  id: string;
  label: string;
  /** From light to dark; the first one is nothing. */
  chars: string;
}

export const RAMPS: Ramp[] = [
  { id: 'signs', label: 'Знаки', chars: ' .:-=+*%8@' },
  { id: 'dots', label: 'Точки', chars: ' .' },
  { id: 'letters', label: 'Буквы', chars: ' .:IVXЖШ' },
  { id: 'solid', label: 'Сплошной', chars: ' @' },
];

/**
 * Symbols a text art can be drawn with (all Radiance glyphs, dense first). No #: a name starting
 * with it is a localisation key in Dota, and an art line may start with any of its symbols.
 */
export const FILL_GLYPHS = ['@', 'Ж', 'Ш', 'W', 'M', '%', '8', 'O', '*', '+', 'X', '=', '•', '.'];

/** The game's advance of one glyph standing alone: a cell narrower than it makes glyphs touch. */
export const glyphAdvance = (ch: string) => advances(ch)[0] ?? 0;

/** Lines of the art: each line's category x offset (from the art's corner) and name. */
export function cellsToRows(cells: Cells, pitch: number): { dx: number; text: string }[] {
  const out: { dx: number; text: string }[] = [];
  for (let r = 0; r < cells.rows; r++) {
    const glyphs = [];
    for (let c = 0; c < cells.cols; c++) {
      const ch = cells.data[r * cells.cols + c];
      if (ch && ch !== ' ') glyphs.push({ ch, x: c * pitch });
    }
    const row = typesetRow(glyphs);
    out.push({ dx: row.x, text: row.text });
  }
  // empty lines at the end carry nothing
  while (out.length && !out[out.length - 1].text.trim()) out.pop();
  return out;
}

/**
 * Symbols are light on Dota's dark grid, so they should stand for the subject: the light parts of
 * a picture on a dark background, the dark parts of one on a light background (told by its border).
 * Tones in: 0 = white … 1 = black. Returns true when the light parts are to be drawn.
 */
export function drawLight(tones: ArrayLike<number>, cols: number, rows: number): boolean {
  let sum = 0;
  let n = 0;
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++)
      if (r === 0 || c === 0 || r === rows - 1 || c === cols - 1) {
        sum += tones[r * cols + c];
        n++;
      }
  return n > 0 && sum / n > 0.5;
}

export interface ToneOptions {
  /** 1 = as is; 2 = twice the contrast. */
  contrast: number;
  /** -1..1 added to the tone. */
  brightness: number;
  /** Draw the light parts with symbols instead of the dark ones. */
  invert: boolean;
  ramp: string;
}

/**
 * Tones (0 = white … 1 = black per cell) → symbols of the ramp. Levels are stretched first (1st
 * to 99th percentile), so a dull photo still uses the whole ramp.
 */
export function toneCells(tones: Float32Array | number[], cols: number, rows: number, o: ToneOptions): Cells {
  const sorted = Array.from(tones).sort((a, b) => a - b);
  const lo = sorted[Math.floor(sorted.length * 0.01)] ?? 0;
  const hi = sorted[Math.ceil(sorted.length * 0.99) - 1] ?? 1;
  const span = hi - lo > 1e-6 ? hi - lo : 1;
  const n = o.ramp.length;
  const data = Array.from(tones, (t) => {
    let v = (t - lo) / span;
    if (o.invert) v = 1 - v;
    v = (v - 0.5) * o.contrast + 0.5 + o.brightness;
    const k = Math.min(n - 1, Math.max(0, Math.floor(v * n)));
    return o.ramp[k];
  });
  return { cols, rows, data };
}

/** Art size in units for its cells (the last column's glyph and the last line's letters included). */
export const artSize = (cells: Cells, pitch: number, step: number) => ({
  w: Math.max(0, cells.cols - 1) * pitch + 16,
  h: Math.max(0, cells.rows - 1) * step + 16,
});
