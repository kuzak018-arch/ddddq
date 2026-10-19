/**
 * How Dota draws a hero grid (hero_grid_config.json), so the editor shows what the game shows.
 *
 * The file's coordinates are units of a 1193 × 593 canvas; the game scales it to the screen (the
 * «Герои» page and the hero pick screen show the same layout). A category is a name drawn at its
 * top-left corner plus a list of heroes below the 20-unit header: the stored height is the list's
 * height, the header is above it. Heroes are 51 × 83 cards, all scaled by one factor so they fill
 * the list best. A category without heroes is just its name: that is how grid art is made — every
 * line of symbols is one empty category whose name is the line.
 *
 * Names are drawn in capitals with Radiance SemiBold at 15.15 units, 2 units of letter spacing, and
 * every glyph's advance (with kerning) snaps to whole screen pixels at 1.1497 px per unit (1080p).
 * These numbers are the in-game measurements published by GridStudio (gridstudio.me, GPL-3.0; the
 * code here is our own); radiance.json holds the font's advances, made by scripts/radiance-metrics.mjs.
 */
import metrics from './radiance.json' with { type: 'json' };

export const CANVAS_W = 1193;
export const CANVAS_H = 593;
export const HEADER = 20;
export const PAD = 4;
export const CELL_W = 51;
export const CELL_H = 83;
export const IMAGE_MARGIN = 4;
export const FONT_SIZE = 15.15;
export const LETTER_SPACING = 2;
export const SCREEN_SCALE = 1.1497;
export const LABEL_COLOR = '#808fa6';
export const BASELINE = FONT_SIZE * 0.857;
/** Size Dota is given for a category without heroes (it is not drawn). */
export const TEXT_BOX = 30;
/** Above this many categories in one grid the game gets slow. */
export const SLOW_CATEGORIES = 2000;
export const MAX_CATEGORIES = 10000;

const ADV: Record<string, number> = metrics.adv;
const KERN: Record<string, number> = metrics.kern;

export interface HeroLayout {
  cols: number;
  rows: number;
  scale: number;
  cardW: number;
  cardH: number;
  /** Offsets of the first card from the category's corner (the header included). */
  left: number;
  top: number;
  stepX: number;
  stepY: number;
}

/** The game's fit of n cards into a w × h hero list: the biggest card scale, every column that fits. */
export function heroLayout(w: number, h: number, n: number): HeroLayout {
  const aw = Math.max(1, w - PAD * 2);
  const ah = Math.max(1, h - PAD * 2);
  let best: HeroLayout | null = null;
  for (let cols = 1; cols <= Math.max(1, n); cols++) {
    const rows = Math.ceil(Math.max(1, n) / cols);
    const scale = Math.min(aw / (cols * CELL_W), ah / (rows * CELL_H));
    if (!best || scale >= best.scale - 1e-10) {
      const inset = IMAGE_MARGIN * scale;
      best = {
        cols,
        rows,
        scale,
        cardW: (CELL_W - IMAGE_MARGIN * 2) * scale,
        cardH: (CELL_H - IMAGE_MARGIN * 2) * scale,
        left: PAD + inset,
        top: HEADER + PAD + inset,
        stepX: CELL_W * scale,
        stepY: CELL_H * scale,
      };
    }
  }
  return best!;
}

/** The list size for n heroes in `cols` columns at card scale `scale`. */
export function listSize(n: number, cols: number, scale: number): { w: number; h: number } {
  const c = Math.max(1, Math.min(cols, n || 1));
  return { w: c * CELL_W * scale + PAD * 2, h: Math.ceil(Math.max(1, n) / c) * CELL_H * scale + PAD * 2 };
}

// ---------- text --------------------------------------------------------------------------------

/** Braille, box drawing and block elements: Dota shows nothing for them. */
const INVISIBLE = /[─-▟⠀-⣿]/u;

export const upper = (s: string) => s.toUpperCase();
/** In Radiance itself: drawn by the game exactly as measured. */
export const inFont = (ch: string) => ADV[upper(ch)] !== undefined;
export const invisible = (ch: string) => INVISIBLE.test(ch);

/** A name Dota will take: no markup characters, no leading # (a localisation key), no line breaks. */
export function cleanName(s: string): string {
  return s.replace(/[<>&\r\n\t]/g, '').replace(/^#+/, '');
}

/** What the game will not draw as in the editor: invisible glyphs and glyphs of a fallback font. */
export function glyphWarnings(text: string): { invisible: string[]; foreign: string[] } {
  const inv = new Set<string>();
  const foreign = new Set<string>();
  for (const ch of Array.from(upper(text))) {
    if (/\s/.test(ch)) continue;
    if (invisible(ch)) inv.add(ch);
    else if (!inFont(ch)) foreign.add(ch);
  }
  return { invisible: [...inv], foreign: [...foreign] };
}

/** Raw width of `ch` after `before` (kerning), in units at the label size; unknown glyphs: a W. */
function pairWidth(before: string, ch: string): number {
  return (ADV[ch] ?? ADV['W']) + (before ? (KERN[before + ch] ?? 0) : 0);
}

/** Where the game puts each glyph's pen step: kerned width snapped to screen pixels, plus spacing. */
export const snap = (width: number) => Math.round(width * SCREEN_SCALE) / SCREEN_SCALE + LETTER_SPACING;

/** The advance of every glyph of a line as the game draws it (capitals). */
export function advances(line: string): number[] {
  let before = '';
  return Array.from(upper(line), (ch) => {
    const a = snap(pairWidth(before, ch));
    before = ch;
    return a;
  });
}

export const lineWidth = (line: string) => advances(line).reduce((s, a) => s + a, 0);

/** Pen x of every glyph of a line, from the category's corner (the 4-unit padding included). */
export function glyphXs(line: string): number[] {
  let pen = PAD;
  return advances(line).map((a) => {
    const x = pen;
    pen += a;
    return x;
  });
}

// ---------- rows of art -------------------------------------------------------------------------

export interface Glyph {
  ch: string;
  /** Where the glyph's pen should be on the canvas. */
  x: number;
}

/**
 * One line of art: glyphs at wanted x positions (sorted), joined into a single name with spaces so
 * each glyph lands as close as the game's widths allow; a glyph whose spot the previous one still
 * covers is left out, so a dense line never drifts. Returns the category x and the name.
 */
export function typesetRow(glyphs: Glyph[]): { x: number; text: string; error: number } {
  if (!glyphs.length) return { x: 0, text: '', error: 0 };
  const first = glyphs[0];
  let text = upper(first.ch);
  let pen = first.x + snap(pairWidth('', text));
  let prev = text;
  let error = 0;
  for (const g of glyphs.slice(1)) {
    const ch = upper(g.ch);
    // spaces while one more brings the pen closer to the wanted spot
    for (;;) {
      const step = snap(pairWidth(prev, ' '));
      if (Math.abs(pen + step - g.x) >= Math.abs(pen - g.x)) break;
      text += ' ';
      pen += step;
      prev = ' ';
    }
    const adv = snap(pairWidth(prev, ch));
    // the previous glyph still covers this spot: drop this one rather than push the rest right
    if (pen - g.x > adv / 2) continue;
    error = Math.max(error, Math.abs(pen - g.x));
    pen += adv;
    text += ch;
    prev = ch;
  }
  return { x: first.x - PAD, text, error };
}
