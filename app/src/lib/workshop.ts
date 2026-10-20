/**
 * GridStudio's workshop arts in our grid editor. An art there is either a text (lines, 20 units
 * apart, as their library lays it out: scripts/ascii-library.mjs layoutAsciiArt) or rows taken from
 * their editor ({ text, x, y } in grid units). Each line becomes one text category of ours, the
 * whole art centred on the canvas.
 */
import { CANVAS_H, CANVAS_W, cleanName, lineWidth, TEXT_BOX } from './grid/dota.ts';
import { newId, type TextItem } from './grid/doc.ts';

export interface WorkshopArt {
  id: number;
  name: string;
  text: string;
  rows?: { text: string; x: number; y: number }[] | null;
}

export const ART_LINE_STEP = 20;

export function artRows(art: WorkshopArt): { text: string; x: number; y: number }[] {
  if (art.rows?.length) return art.rows.filter((r) => r.text.trim()).map((r) => ({ text: r.text, x: r.x, y: r.y }));
  return art.text
    .replace(/\r/g, '')
    .split('\n')
    .map((line, i) => ({ text: line.replace(/\s+$/u, ''), x: 0, y: i * ART_LINE_STEP }))
    .filter((r) => r.text.trim());
}

export function artToItems(art: WorkshopArt): { items: TextItem[]; w: number; h: number } {
  // Dota reads a name starting with # as a translation key, so cleanName drops leading #: the rest of
  // the line is moved right by their width and stays where it was in the art
  const rows = artRows(art)
    .map((r) => {
      const lead = /^#+/.exec(r.text)?.[0] ?? '';
      return { ...r, x: r.x + (lead ? lineWidth(r.text) - lineWidth(r.text.slice(lead.length)) : 0), text: cleanName(r.text) };
    })
    .filter((r) => r.text.trim());
  if (!rows.length) return { items: [], w: 0, h: 0 };
  const w = Math.max(...rows.map((r) => r.x + Math.max(TEXT_BOX, lineWidth(r.text))));
  const h = Math.max(...rows.map((r) => r.y)) + TEXT_BOX;
  const x0 = Math.max(0, (CANVAS_W - w) / 2);
  const y0 = Math.max(0, (CANVAS_H - h) / 2);
  const round = (v: number) => Math.round(v * 100) / 100;
  return { items: rows.map((r) => ({ id: newId(), type: 'text', text: r.text, x: round(x0 + r.x), y: round(y0 + r.y) })), w, h };
}
