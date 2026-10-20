/**
 * The grid as Dota draws it: a 1193 × 593 canvas scaled to the panel. Groups with their hero cards
 * (the game's fit), captions and art drawn glyph by glyph at the game's advances.
 *
 * Mouse: drag an item to move it, the corner of a group to resize it, a hero card into another
 * group or onto the canvas (out of its group); double click a group's name to rename it.
 * Keys: Delete, arrows (Shift — by 10), Ctrl+D duplicate, Ctrl+Z / Ctrl+Y.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { create } from 'zustand';

import { asset } from '../../api/client';
import { useHeroes } from '../../api/hooks';
import { BASELINE, CANVAS_H, CANVAS_W, cleanName, glyphXs, HEADER, heroLayout, LABEL_COLOR, lineWidth, PAD } from '../../lib/grid/dota';
import { clampItem, newId, type GroupItem, type Item } from '../../lib/grid/doc';
import { activeGrid, useGrids } from '../../state/grids';

/** A hero being dragged (from the palette or out of a group), shared with the palette. */
export const useHeroDrag = create<{ hero: number | null; from: { id: string; index: number } | null; x: number; y: number }>(() => ({
  hero: null,
  from: null,
  x: 0,
  y: 0,
}));

export function portraitUrl(id: number) {
  return `/portraits/${id}.webp`;
}

/** The hero's tall portrait, or its wide icon (cropped the same way) when there is none yet. */
export function Portrait({ id, className }: { id: number; className?: string }) {
  const hero = useHeroes().data?.byId.get(id);
  const [fallback, setFallback] = useState(false);
  const src = fallback && hero ? asset(hero.icon) : portraitUrl(id);
  return <img className={className} src={src} alt={hero?.name ?? ''} title={hero?.name} draggable={false} onError={() => setFallback(true)} />;
}

/** One line of a name: glyphs placed at the game's advances (the font itself is not ours). */
export function GlyphLine({ text, x, y }: { text: string; x: number; y: number }) {
  const up = text.toUpperCase();
  const xs = glyphXs(up);
  const chars = Array.from(up);
  const keep = chars.map((c, i) => [c, xs[i]] as const).filter(([c]) => c !== ' ');
  if (!keep.length) return null;
  return (
    <text x={keep.map(([, px]) => (x + px).toFixed(2)).join(' ')} y={y + BASELINE}>
      {keep.map(([c]) => c).join('')}
    </text>
  );
}

const itemBox = (it: Item) =>
  it.type === 'group'
    ? { x: it.x, y: it.y, w: it.w, h: it.h + HEADER }
    : it.type === 'art'
      ? { x: it.x, y: it.y, w: it.w, h: it.h }
      : { x: it.x, y: it.y, w: Math.max(12, lineWidth(cleanName(it.text)) + PAD), h: HEADER };

type Gesture =
  | { kind: 'move'; id: string; sx: number; sy: number; ox: number; oy: number; moved: boolean }
  | { kind: 'resize'; id: string; sx: number; sy: number; ow: number; oh: number };

export function GridCanvas({ onRename }: { onRename?: (id: string) => void }) {
  const grid = useGrids(activeGrid);
  const selected = useGrids((s) => s.selected);
  const { editItems, select } = useGrids.getState();
  const wrap = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.6);
  const [live, setLive] = useState<{ id: string; x?: number; y?: number; w?: number; h?: number } | null>(null);
  const [renaming, setRenaming] = useState<string | null>(null);
  const gesture = useRef<Gesture | null>(null);
  const drag = useHeroDrag();

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const fit = () => setScale(Math.max(0.2, Math.min(el.clientWidth / CANVAS_W, el.clientHeight / CANVAS_H)));
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const items = useMemo(
    () => grid.items.map((it) => (live && it.id === live.id ? ({ ...it, ...live } as Item) : it)),
    [grid.items, live],
  );

  const toUnits = (e: { clientX: number; clientY: number }) => {
    const r = wrap.current!.querySelector('.gc__canvas')!.getBoundingClientRect();
    return { x: (e.clientX - r.left) / scale, y: (e.clientY - r.top) / scale };
  };

  // ---------- moving and resizing items ----------
  const startMove = (e: React.PointerEvent, it: Item) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    select(it.id);
    const p = toUnits(e);
    gesture.current = { kind: 'move', id: it.id, sx: p.x, sy: p.y, ox: it.x, oy: it.y, moved: false };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const startResize = (e: React.PointerEvent, it: GroupItem) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    select(it.id);
    const p = toUnits(e);
    gesture.current = { kind: 'resize', id: it.id, sx: p.x, sy: p.y, ow: it.w, oh: it.h };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onMove = (e: React.PointerEvent) => {
    const g = gesture.current;
    if (!g) return;
    const p = toUnits(e);
    const it = grid.items.find((i) => i.id === g.id);
    if (!it) return;
    if (g.kind === 'move') {
      if (!g.moved && Math.hypot(p.x - g.sx, p.y - g.sy) < 2) return;
      g.moved = true;
      const c = clampItem({ ...it, x: Math.round(g.ox + p.x - g.sx), y: Math.round(g.oy + p.y - g.sy) });
      setLive({ id: it.id, x: c.x, y: c.y });
    } else if (it.type === 'group') {
      const w = Math.min(CANVAS_W - it.x, Math.max(40, Math.round(g.ow + p.x - g.sx)));
      const h = Math.min(CANVAS_H - it.y - HEADER, Math.max(30, Math.round(g.oh + p.y - g.sy)));
      setLive({ id: it.id, w, h });
    }
  };
  const onUp = () => {
    const g = gesture.current;
    gesture.current = null;
    if (g && live && live.id === g.id) {
      const patch = live;
      editItems((list) => list.map((i) => (i.id === patch.id ? ({ ...i, ...patch } as Item) : i)));
    }
    setLive(null);
  };

  // ---------- heroes: drag from a group or the palette ----------
  const startHeroDrag = (e: React.PointerEvent, group: GroupItem, index: number) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    select(group.id);
    useHeroDrag.setState({ hero: group.heroes[index], from: { id: group.id, index }, x: e.clientX, y: e.clientY });
  };
  useEffect(() => {
    if (drag.hero === null) return;
    const move = (e: PointerEvent) => useHeroDrag.setState({ x: e.clientX, y: e.clientY });
    const up = (e: PointerEvent) => {
      const { hero, from } = useHeroDrag.getState();
      useHeroDrag.setState({ hero: null, from: null });
      if (hero === null || !wrap.current) return;
      const r = wrap.current.querySelector('.gc__canvas')!.getBoundingClientRect();
      const inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      const p = { x: (e.clientX - r.left) / scale, y: (e.clientY - r.top) / scale };
      const target = inside
        ? [...grid.items].reverse().find((i): i is GroupItem => i.type === 'group' && p.x >= i.x && p.x <= i.x + i.w && p.y >= i.y && p.y <= i.y + i.h + HEADER)
        : undefined;
      if (!target && !from) return; // a palette hero dropped next to the groups
      if (!target && from && !inside) return; // dragged out of the canvas: nothing changes
      editItems((list) =>
        list.map((i) => {
          if (i.type !== 'group') return i;
          let heroes = i.heroes;
          if (from && i.id === from.id) heroes = heroes.filter((_, k) => k !== from.index);
          if (target && i.id === target.id) {
            const at = dropIndex(target, heroes.length, p);
            heroes = [...heroes.slice(0, at), hero, ...heroes.slice(at)];
          }
          return heroes === i.heroes ? i : { ...i, heroes };
        }),
      );
      if (target) select(target.id);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up, { once: true });
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }, [drag.hero !== null, grid.items, scale]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- keys ----------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest('input, textarea, select, [contenteditable]')) return;
      const s = useGrids.getState();
      if (e.ctrlKey && (e.code === 'KeyZ' || e.code === 'KeyY')) {
        e.preventDefault();
        if (e.code === 'KeyY' || e.shiftKey) s.redo();
        else s.undo();
        return;
      }
      const id = s.selected;
      if (!id) return;
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault();
        s.editItems((l) => l.filter((i) => i.id !== id));
        s.select(null);
      } else if (e.ctrlKey && e.code === 'KeyD') {
        e.preventDefault();
        const it = activeGrid(s).items.find((i) => i.id === id);
        if (!it) return;
        const copy = clampItem({ ...structuredClone(it), id: newId(), x: it.x + 16, y: it.y + 16 });
        s.editItems((l) => [...l, copy]);
        s.select(copy.id);
      } else if (e.key.startsWith('Arrow')) {
        e.preventDefault();
        const d = e.shiftKey ? 10 : 1;
        const dx = e.key === 'ArrowLeft' ? -d : e.key === 'ArrowRight' ? d : 0;
        const dy = e.key === 'ArrowUp' ? -d : e.key === 'ArrowDown' ? d : 0;
        s.editItems((l) => l.map((i) => (i.id === id ? clampItem({ ...i, x: i.x + dx, y: i.y + dy }) : i)), true);
      } else if (e.key === 'Escape') s.select(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="gc" ref={wrap} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
      <div className="gc__sizer" style={{ width: CANVAS_W * scale, height: CANVAS_H * scale }}>
      <div
        className="gc__canvas"
        style={{ width: CANVAS_W, height: CANVAS_H, transform: `scale(${scale})` }}
        onPointerDown={(e) => e.target === e.currentTarget && select(null)}
      >
        {items.map((it) =>
          it.type === 'group' ? (
            <Group
              key={it.id}
              g={it}
              selected={selected === it.id}
              dragFrom={drag.from?.id === it.id ? drag.from.index : null}
              onPointerDown={(e) => startMove(e, it)}
              onResize={(e) => startResize(e, it)}
              onHero={(e, k) => startHeroDrag(e, it, k)}
              onRemoveHero={(k) => editItems((l) => l.map((i) => (i.id === it.id && i.type === 'group' ? { ...i, heroes: i.heroes.filter((_, n) => n !== k) } : i)))}
              onRename={() => (onRename ? onRename(it.id) : setRenaming(it.id))}
            />
          ) : (
            <div
              key={it.id}
              className={`gc__hit ${selected === it.id ? 'is-selected' : ''}`}
              style={{ left: itemBox(it).x, top: itemBox(it).y, width: itemBox(it).w, height: itemBox(it).h }}
              onPointerDown={(e) => startMove(e, it)}
            />
          ),
        )}
        <svg className="gc__text" width={CANVAS_W} height={CANVAS_H} viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`} fill={LABEL_COLOR}>
          {items.map((it) =>
            it.type === 'group' ? (
              renaming === it.id ? null : <GlyphLine key={it.id} text={cleanName(it.name)} x={it.x} y={it.y} />
            ) : it.type === 'text' ? (
              <GlyphLine key={it.id} text={cleanName(it.text)} x={it.x} y={it.y} />
            ) : (
              <g key={it.id}>
                {it.rows.map((r, i) => (
                  <GlyphLine key={i} text={r.text} x={it.x + r.dx} y={it.y + i * it.step} />
                ))}
              </g>
            ),
          )}
        </svg>
        {renaming &&
          (() => {
            const g = grid.items.find((i) => i.id === renaming);
            if (!g || g.type !== 'group') return null;
            return (
              <input
                className="gc__rename"
                autoFocus
                defaultValue={g.name}
                style={{ left: g.x, top: g.y, width: Math.max(120, g.w) }}
                onPointerDown={(e) => e.stopPropagation()}
                onBlur={(e) => {
                  const name = cleanName(e.target.value);
                  editItems((l) => l.map((i) => (i.id === g.id && i.type === 'group' ? { ...i, name } : i)));
                  setRenaming(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                  if (e.key === 'Escape') setRenaming(null);
                }}
              />
            );
          })()}
      </div>
      </div>
      {drag.hero !== null && (
        <div className="gc__ghost" style={{ left: drag.x, top: drag.y }}>
          <Portrait id={drag.hero} />
        </div>
      )}
    </div>
  );
}

/** Where a hero dropped at p goes in the group's list (the game's card grid). */
function dropIndex(g: GroupItem, n: number, p: { x: number; y: number }): number {
  const l = heroLayout(g.w, g.h, n + 1);
  const col = Math.max(0, Math.min(l.cols - 1, Math.floor((p.x - g.x - l.left + l.stepX / 2) / l.stepX)));
  const row = Math.max(0, Math.floor((p.y - g.y - l.top) / l.stepY));
  return Math.max(0, Math.min(n, row * l.cols + col));
}

function Group({ g, selected, dragFrom, onPointerDown, onResize, onHero, onRemoveHero, onRename }: {
  g: GroupItem;
  selected: boolean;
  dragFrom: number | null;
  onPointerDown: (e: React.PointerEvent) => void;
  onResize: (e: React.PointerEvent) => void;
  onHero: (e: React.PointerEvent, index: number) => void;
  onRemoveHero: (index: number) => void;
  onRename: () => void;
}) {
  const l = heroLayout(g.w, g.h, g.heroes.length);
  return (
    <div
      className={`gc__group ${selected ? 'is-selected' : ''}`}
      style={{ left: g.x, top: g.y, width: g.w, height: g.h + HEADER }}
      onPointerDown={onPointerDown}
      onDoubleClick={(e) => (e.nativeEvent.offsetY < HEADER || e.target === e.currentTarget) && onRename()}
    >
      <div className="gc__head" title="Двойной щелчок — переименовать" />
      {g.heroes.map((h, k) => (
        <div
          key={`${h}-${k}`}
          className={`gc__card ${dragFrom === k ? 'is-lifted' : ''}`}
          style={{ left: l.left + (k % l.cols) * l.stepX, top: l.top + Math.floor(k / l.cols) * l.stepY, width: l.cardW, height: l.cardH }}
          onPointerDown={(e) => onHero(e, k)}
          onContextMenu={(e) => {
            e.preventDefault();
            onRemoveHero(k);
          }}
        >
          <Portrait id={h} />
        </div>
      ))}
      {selected && <div className="gc__resize" onPointerDown={onResize} title="Тяни, чтобы поменять размер" />}
    </div>
  );
}
