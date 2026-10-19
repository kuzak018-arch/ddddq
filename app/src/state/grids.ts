/**
 * The grid editor's document (kept in localStorage) with undo/redo. Pictures of image art are in
 * IndexedDB (bgstore), only their keys are here.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { emptyGrid, newId, type Grid, type Item } from '../lib/grid/doc';

const HISTORY = 80;

interface GridDoc {
  grids: Grid[];
  active: string;
}

interface GridState extends GridDoc {
  selected: string | null;
  past: GridDoc[];
  future: GridDoc[];
  /** Change the document; one undo step (pass `merge` to fold into the previous step while dragging). */
  edit: (fn: (d: GridDoc) => GridDoc, merge?: boolean) => void;
  editItems: (fn: (items: Item[]) => Item[], merge?: boolean) => void;
  select: (id: string | null) => void;
  undo: () => void;
  redo: () => void;
}

const first = emptyGrid();
let lastMerge = 0;

export const useGrids = create<GridState>()(
  persist(
    (set, get) => ({
      grids: [first],
      active: first.id,
      selected: null,
      past: [],
      future: [],
      edit: (fn, merge) => {
        const s = get();
        const before: GridDoc = { grids: s.grids, active: s.active };
        const after = fn(before);
        if (after === before) return;
        // a drag is many edits: one undo step while they keep coming
        const now = Date.now();
        const folding = merge && now - lastMerge < 800 && s.past.length > 0;
        lastMerge = merge ? now : 0;
        set({
          ...after,
          past: folding ? s.past : [...s.past.slice(-HISTORY + 1), before],
          future: [],
        });
      },
      editItems: (fn, merge) =>
        get().edit((d) => ({ ...d, grids: d.grids.map((g) => (g.id === d.active ? { ...g, items: fn(g.items) } : g)) }), merge),
      select: (id) => set({ selected: id }),
      undo: () => {
        const s = get();
        const prev = s.past[s.past.length - 1];
        if (!prev) return;
        set({ ...prev, past: s.past.slice(0, -1), future: [{ grids: s.grids, active: s.active }, ...s.future], selected: null });
      },
      redo: () => {
        const s = get();
        const next = s.future[0];
        if (!next) return;
        set({ ...next, future: s.future.slice(1), past: [...s.past, { grids: s.grids, active: s.active }], selected: null });
      },
    }),
    {
      name: 'drafter-grids',
      version: 1,
      partialize: (s) => ({ grids: s.grids, active: s.active }),
      merge: (saved, current) => {
        const doc = saved as Partial<GridDoc> | undefined;
        if (!doc?.grids?.length) return current;
        const active = doc.grids.some((g) => g.id === doc.active) ? doc.active! : doc.grids[0].id;
        return { ...current, grids: doc.grids, active };
      },
    },
  ),
);

export const activeGrid = (s: GridDoc) => s.grids.find((g) => g.id === s.active) ?? s.grids[0];

/** A name not used by another grid: «Сетка», «Сетка (2)», … */
export function freeName(grids: Grid[], name: string): string {
  const taken = new Set(grids.map((g) => g.name));
  if (!taken.has(name)) return name;
  for (let i = 2; ; i++) if (!taken.has(`${name} (${i})`)) return `${name} (${i})`;
}

export function addGrids(added: Grid[]) {
  useGrids.getState().edit((d) => {
    const grids = [...d.grids];
    for (const g of added) grids.push({ ...g, id: newId(), name: freeName(grids, g.name) });
    return { grids, active: grids[grids.length - added.length]?.id ?? d.active };
  });
}
