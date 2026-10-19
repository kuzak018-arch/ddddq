/**
 * The font preview: Dota's main menu and a moment of a match, split by a slanted line that can be
 * dragged. Each scene is a screenshot of the Russian client with its text removed (the plate) and the
 * text drawn again on top — in the chosen font for the roles it replaces, as the game's own pixels
 * (a layer per role) for the others; each label is laid out like Panorama does it (glyph by glyph,
 * advances rounded to pixels, plus letter spacing; shrinking and «…» like the game).
 *
 * Использовано из GridStudio — https://gridstudio.me, https://github.com/linsisss/dota2-grid-toolkit
 * (GPL-3.0-only): a port of src/customize/FontScene.jsx with its scenes (app/src/data/font-scene.json,
 * public/font-scene; the friends' nicknames there are replaced with made-up ones).
 */
import { useEffect, useRef, useState } from 'react';

import scenes from '../../data/font-scene.json';

type Role = 'Radiance' | 'RadianceM' | 'Reaver';
interface Part {
  t: string;
  r: Role;
  w: number;
  s: number;
  l: number;
  m: 'f' | 'r' | 'x';
  p: number;
  c: string;
  g?: number;
  dy?: number;
  k?: number;
  cs?: number;
  e?: number;
  el?: string;
}
interface Label extends Part {
  id: string;
  a: 'start' | 'middle' | 'end';
  x: number;
  y: number;
  f?: Part[];
}
interface SceneData {
  plate: string;
  layers: Partial<Record<Role, string>>;
  labels: Label[];
}
const data = scenes as unknown as { width: number; height: number; scenes: Record<string, SceneData> };
const W = data.width;
const H = data.height;
const asset = (file: string) => `/font-scene/${file}`;

const ruler = typeof document === 'undefined' ? null : document.createElement('canvas').getContext('2d');
const widths = new Map<string, number>();
const ROUND = { f: Math.floor, r: Math.round, x: (v: number) => v };
function advance(css: string, ch: string) {
  const key = `${css}|${ch}`;
  if (!widths.has(key)) {
    ruler!.font = css;
    widths.set(key, ruler!.measureText(ch).width);
  }
  return widths.get(key)!;
}
function lay(part: Part, family: string, text: string, size: number) {
  const css = `${part.w} ${size}px '${family}', sans-serif`;
  const xs: number[] = [];
  let pen = 0;
  for (const ch of Array.from(text)) {
    xs.push(pen);
    pen += ROUND[part.m](advance(css, ch)) + part.l;
  }
  return { text, size, xs, pen };
}
function setLabel(part: Part, family: string) {
  let size = part.s;
  if (part.k && part.cs) {
    size = part.cs;
    const wide = lay(part, family, part.t, size).pen;
    if (wide > part.k) size = Math.max(4, (size * part.k) / wide);
  }
  let done = lay(part, family, part.t, size);
  if (part.e && done.pen > part.e) {
    const chars = Array.from(part.t);
    const dots = part.el || '…';
    let n = chars.length - 1;
    while (n > 1 && lay(part, family, `${chars.slice(0, n).join('').trimEnd()}${dots}`, size).pen > part.e) n--;
    done = lay(part, family, `${chars.slice(0, n).join('').trimEnd()}${dots}`, size);
  }
  return done;
}
/** A label and the next ones of its row, laid out together and anchored as Panorama anchored the row. */
function row(label: Label, family: string, roles: Partial<Record<Role, boolean>>) {
  const parts = [label, ...(label.f ?? [])].map((part) => ({ part, done: roles[part.r] ? setLabel(part, family) : null }));
  const total = parts.reduce((sum, { part, done }, i) => sum + (i ? (part.g ?? 0) : 0) + (done ? done.pen : part.p), 0);
  let x = label.a === 'middle' ? label.x - total / 2 : label.a === 'end' ? label.x - total : label.x;
  let y = label.y;
  return parts
    .map(({ part, done }, i) => {
      if (i) {
        x += part.g ?? 0;
        y += part.dy ?? 0;
      }
      const at = { x, y, part, done };
      x += done ? done.pen : part.p;
      return at;
    })
    .filter((at) => at.done);
}

function Scene({ id, family, roles }: { id: string; family: string | null; roles: Partial<Record<Role, boolean>> }) {
  const scene = data.scenes[id];
  if (!scene) return null;
  return (
    <svg className="fscene__layer" viewBox={`0 0 ${W} ${H}`} aria-hidden preserveAspectRatio="xMidYMid slice">
      <image href={asset(scene.plate)} x="0" y="0" width={W} height={H} preserveAspectRatio="none" />
      {Object.entries(scene.layers).map(([role, file]) =>
        !(roles[role as Role] && family) ? <image key={role} href={asset(file!)} x="0" y="0" width={W} height={H} preserveAspectRatio="none" /> : null,
      )}
      {family && ruler && (
        <g className="fscene__text" fontFamily={`'${family}', sans-serif`}>
          {scene.labels.flatMap((label) =>
            row(label, family, roles).map(({ x, y, part, done }, i) => (
              <text key={`${label.id}-${i}`} x={done!.xs.map((at) => +(x + at).toFixed(2)).join(' ')} y={y} fontWeight={part.w} fontSize={+done!.size.toFixed(2)} fill={part.c}>
                {done!.text}
              </text>
            )),
          )}
        </g>
      )}
    </svg>
  );
}

const LEAN = 0.07;
const clamp = (v: number) => Math.max(0.06, Math.min(0.94, v));

export function FontScene({ family, roles }: { family: string | null; roles: Partial<Record<Role, boolean>> }) {
  const [split, setSplit] = useState(0.45);
  const [dragging, setDragging] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!dragging) return;
    const up = () => setDragging(false);
    window.addEventListener('pointerup', up);
    return () => window.removeEventListener('pointerup', up);
  }, [dragging]);
  const top = (split + LEAN) * 100;
  const bottom = (split - LEAN) * 100;
  return (
    <div
      ref={box}
      className="fscene"
      style={{ aspectRatio: `${W} / ${H}` }}
      onPointerMove={(e) => {
        if (!dragging || !box.current) return;
        const r = box.current.getBoundingClientRect();
        const fx = (e.clientX - r.left) / r.width;
        const fy = (e.clientY - r.top) / r.height;
        setSplit(clamp(fx - LEAN + 2 * LEAN * fy));
      }}
    >
      <div className="fscene__part">
        <Scene id="hud" family={family} roles={roles} />
      </div>
      <div className="fscene__part" style={{ clipPath: `polygon(0 0, ${top}% 0, ${bottom}% 100%, 0 100%)` }}>
        <Scene id="menu" family={family} roles={roles} />
      </div>
      <div className="fscene__split">
        <i style={{ clipPath: `polygon(calc(${top}% - 1px) 0, calc(${top}% + 1px) 0, calc(${bottom}% + 1px) 100%, calc(${bottom}% - 1px) 100%)` }} />
        <button
          type="button"
          className="fscene__handle"
          style={{ left: `${split * 100}%` }}
          aria-label="Сдвинуть черту"
          onPointerDown={(e) => {
            setDragging(true);
            e.currentTarget.setPointerCapture?.(e.pointerId);
          }}
        />
      </div>
    </div>
  );
}
