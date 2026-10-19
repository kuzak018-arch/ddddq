/**
 * The grid editor's document: several grids, each a list of items on the 1193 × 593 canvas.
 *
 *  * group — a hero category: name, place, list size, heroes;
 *  * text  — a caption: one empty category whose name is the text;
 *  * art   — a picture of symbols: one empty category per line (rows[i] at y + i·step), made from
 *            a text or an image and remade from its settings when they change.
 *
 * Import turns a file's categories into groups (with heroes) and texts (without); fields we do not
 * know are kept and written back. Export gives Dota's own configs.
 */
import { CANVAS_H, CANVAS_W, cleanName, HEADER, listSize, TEXT_BOX } from './dota.ts';

export interface Extra {
  [k: string]: unknown;
}

export interface GroupItem {
  id: string;
  type: 'group';
  name: string;
  x: number;
  y: number;
  /** The hero list's size (the 20-unit header is above it). */
  w: number;
  h: number;
  heroes: number[];
  extra?: Extra;
}

export interface TextItem {
  id: string;
  type: 'text';
  text: string;
  x: number;
  y: number;
  extra?: Extra;
}

export interface TextArtSource {
  kind: 'text';
  text: string;
  /** Letter height in symbols. */
  size: number;
  /** Distance between symbols across and between lines, units. */
  pitch: number;
  step: number;
  glyph: string;
  bold: boolean;
}

export interface ImageArtSource {
  kind: 'image';
  /** Picture key in IndexedDB. */
  key: string;
  /** Width of the art, in symbols. */
  cols: number;
  pitch: number;
  step: number;
  contrast: number;
  brightness: number;
  invert: boolean;
  ramp: string;
}

export interface ArtItem {
  id: string;
  type: 'art';
  x: number;
  y: number;
  /** Line step, units. */
  step: number;
  /** Each line: its category's x offset from x, and its name (symbols and spaces, see art.ts). */
  rows: { dx: number; text: string }[];
  source: TextArtSource | ImageArtSource;
  /** Width and height of the art, units (for selection and dragging). */
  w: number;
  h: number;
}

export type Item = GroupItem | TextItem | ArtItem;

export interface Grid {
  id: string;
  name: string;
  items: Item[];
  /** Write this grid into Dota. */
  game: boolean;
  extra?: Extra;
}

export interface DotaCategory {
  category_name: string;
  x_position: number;
  y_position: number;
  width: number;
  height: number;
  hero_ids: number[];
  [k: string]: unknown;
}

export interface DotaConfig {
  config_name: string;
  categories: DotaCategory[];
  [k: string]: unknown;
}

let counter = 0;
export const newId = () => `${Date.now().toString(36)}${(counter++).toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export const emptyGrid = (name = 'Новая сетка'): Grid => ({ id: newId(), name, items: [], game: true });

export function newGroup(x: number, y: number, name = 'Группа', heroes: number[] = [], cols = 6, scale = 1): GroupItem {
  const { w, h } = listSize(Math.max(heroes.length, cols), cols, scale);
  return { id: newId(), type: 'group', name, x, y, w, h, heroes };
}

const num = (v: unknown, fallback = 0) => (typeof v === 'number' && Number.isFinite(v) ? v : fallback);
const KNOWN = new Set(['category_name', 'x_position', 'y_position', 'width', 'height', 'hero_ids']);
const extraOf = (o: Record<string, unknown>, known: Set<string>): Extra | undefined => {
  const e = Object.fromEntries(Object.entries(o).filter(([k]) => !known.has(k)));
  return Object.keys(e).length ? e : undefined;
};

/** A file's text (Dota's hero_grid_config.json, BOM allowed) → its configs; throws on another format. */
export function parseFile(text: string): DotaConfig[] {
  const data = JSON.parse(text.replace(/^﻿/, ''));
  if (!data || typeof data !== 'object' || !Array.isArray(data.configs)) throw new Error('это не файл сеток Доты (нет списка configs)');
  if (data.version !== 3) throw new Error(`незнакомая версия файла сеток (${data.version}), ждём 3`);
  return data.configs.filter((c: unknown) => c && typeof c === 'object' && Array.isArray((c as DotaConfig).categories));
}

export function fromDota(cfg: DotaConfig, prefix = ''): Grid {
  const items: Item[] = cfg.categories.map((c) => {
    const heroes = Array.isArray(c.hero_ids) ? c.hero_ids.filter((h): h is number => Number.isInteger(h)) : [];
    const base = { id: newId(), x: num(c.x_position), y: num(c.y_position), extra: extraOf(c, KNOWN) };
    if (heroes.length || num(c.width) > TEXT_BOX || num(c.height) > TEXT_BOX)
      return { ...base, type: 'group', name: String(c.category_name ?? ''), w: num(c.width, 100), h: num(c.height, 100), heroes };
    return { ...base, type: 'text', text: String(c.category_name ?? '') };
  });
  const name = String(cfg.config_name ?? 'Сетка');
  return {
    id: newId(),
    name: prefix && name.startsWith(prefix) ? name.slice(prefix.length) : name,
    items,
    game: true,
    extra: extraOf(cfg, new Set(['config_name', 'categories'])),
  };
}

const round = (v: number) => Math.round(v * 1e4) / 1e4;

/** Dota's categories of one grid. */
export function toDota(grid: Grid, prefix = ''): DotaConfig {
  const categories: DotaCategory[] = [];
  const text = (name: string, x: number, y: number, extra?: Extra) =>
    categories.push({ ...extra, category_name: name, x_position: round(x), y_position: round(y), width: TEXT_BOX, height: TEXT_BOX, hero_ids: [] });
  for (const it of grid.items) {
    if (it.type === 'group')
      categories.push({
        ...it.extra,
        category_name: cleanName(it.name),
        x_position: round(it.x),
        y_position: round(it.y),
        width: round(it.w),
        height: round(it.h),
        hero_ids: [...it.heroes],
      });
    else if (it.type === 'text') {
      const name = cleanName(it.text);
      if (name.trim()) text(name, it.x, it.y, it.extra);
    }
    else it.rows.forEach((r, i) => r.text.trim() && text(r.text, it.x + r.dx, it.y + i * it.step));
  }
  return { ...grid.extra, config_name: prefix + cleanName(grid.name), categories };
}

/** Keep an item on the canvas (the header of a group included). */
export function clampItem<T extends Item>(it: T): T {
  const w = it.type === 'group' ? it.w : it.type === 'art' ? it.w : 30;
  const h = it.type === 'group' ? it.h + HEADER : it.type === 'art' ? it.h : HEADER;
  return { ...it, x: Math.min(Math.max(0, it.x), Math.max(0, CANVAS_W - w)), y: Math.min(Math.max(0, it.y), Math.max(0, CANVAS_H - h)) };
}

/** Categories one grid gives Dota. */
export const categoryCount = (g: Grid) => g.items.reduce((n, it) => n + (it.type === 'art' ? it.rows.filter((r) => r.text.trim()).length : 1), 0);
