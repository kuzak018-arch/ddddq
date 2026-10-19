/**
 * Dota's screens over the chosen background, laid out in 1080p pixels and scaled like Panorama does
 * it (min(width / 1920, height / 1080)): on a wide screen the panels move to the edges. Pictures cut
 * from the game by GridStudio (public/dota-ui, see its README); positions from GridStudio's
 * DotaMenu.jsx / DotaHeroPage.jsx / DotaGridPage.jsx (https://github.com/linsisss/dota2-grid-toolkit,
 * GPL-3.0-only). The grid page shows the grid open in our editor where the game puts it: 1193 × 593
 * units at 1.1497 px from (269, 174).
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';

import { CANVAS_H, CANVAS_W, cleanName, HEADER, heroLayout, LABEL_COLOR, SCREEN_SCALE } from '../../lib/grid/dota';
import type { Grid } from '../../lib/grid/doc';
import { GlyphLine, Portrait } from '../grid/GridCanvas';

const ui = (name: string) => `/dota-ui/${name}.webp`;

function Layer({ children }: { children: ReactNode }) {
  const frame = useRef<HTMLDivElement>(null);
  const layer = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const fit = () => {
      const r = frame.current!.getBoundingClientRect();
      if (!r.width || !r.height) return;
      const scale = Math.min(r.width / 1920, r.height / 1080);
      Object.assign(layer.current!.style, { width: `${r.width / scale}px`, height: `${r.height / scale}px`, transform: `scale(${scale})` });
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(frame.current!);
    return () => ro.disconnect();
  }, []);
  return (
    <div className="dscreen" ref={frame} aria-hidden>
      <div className="dscreen__layer" ref={layer}>
        {children}
      </div>
    </div>
  );
}

function TopBar({ hero }: { hero?: boolean }) {
  const bar = ui(hero ? 'hero-bar' : 'bar');
  return (
    <>
      <div className={`dm-bar-left ${hero ? 'is-hero' : ''}`} style={{ backgroundImage: `url(${bar})` }} />
      <div className="dm-bar-mid" style={{ backgroundImage: `url(${ui('bar-mid')})` }} />
      <div className={`dm-bar-right ${hero ? 'is-hero' : ''}`} style={{ backgroundImage: `url(${bar})` }} />
    </>
  );
}

export function MenuScreen({ news }: { news: boolean }) {
  return (
    <Layer>
      <TopBar />
      <img className={`dm-news ${news ? '' : 'is-hidden'}`} src={ui('news')} alt="" />
      <img className={`dm-news dm-season ${news ? '' : 'is-hidden'}`} src={ui('season')} alt="" />
      <img className="dm-chat" src={ui('chat')} alt="" />
      <img className="dm-play" src={ui('play')} alt="" />
    </Layer>
  );
}

export function HeroScreen({ aspect }: { aspect: string }) {
  return (
    <Layer>
      <div className="dh-content" data-aspect={aspect.replace(':', 'x')}>
        <img className="dh-left" src={ui('hero-left')} alt="" />
        <img className="dh-right" src={ui('hero-right')} alt="" />
      </div>
      <div className="dh-band" />
      <img className="dh-prev" src={ui('hero-prev')} alt="" />
      <img className="dh-tabs" src={ui('hero-tabs')} alt="" />
      <img className="dh-next" src={ui('hero-next')} alt="" />
      <img className="dh-armory" src={ui('hero-armory')} alt="" />
      <TopBar hero />
      <img className="dm-chat" src={ui('chat')} alt="" />
      <img className="dm-play" src={ui('play')} alt="" />
    </Layer>
  );
}

/** A grid of our editor drawn as the game does (no interaction). */
export function GridPicture({ grid, fontFamily }: { grid: Grid | null; fontFamily?: string }) {
  if (!grid) return null;
  return (
    <div className="gpic" style={{ width: CANVAS_W, height: CANVAS_H }}>
      {grid.items.map((it) => {
        if (it.type !== 'group') return null;
        const l = heroLayout(it.w, it.h, it.heroes.length);
        return (
          <div key={it.id} className="gpic__group" style={{ left: it.x, top: it.y, width: it.w, height: it.h + HEADER }}>
            {it.heroes.map((h, k) => (
              <div key={`${h}-${k}`} className="gc__card" style={{ left: l.left + (k % l.cols) * l.stepX, top: l.top + Math.floor(k / l.cols) * l.stepY, width: l.cardW, height: l.cardH }}>
                <Portrait id={h} />
              </div>
            ))}
          </div>
        );
      })}
      <svg className="gc__text" width={CANVAS_W} height={CANVAS_H} viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`} fill={LABEL_COLOR} style={fontFamily ? { fontFamily } : undefined}>
        {grid.items.map((it) =>
          it.type === 'group' ? (
            <GlyphLine key={it.id} text={cleanName(it.name)} x={it.x} y={it.y} />
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
    </div>
  );
}

export function GridScreen({ grid }: { grid: Grid | null }) {
  return (
    <Layer>
      <div className="dg-band" />
      <div className="dg-box">
        <img className="dg-subnav" src={ui('grid-subnav')} alt="" />
        <img className="dg-bans" src={ui('grid-bans')} alt="" />
        <div className="dg-grid" style={{ transform: `scale(${SCREEN_SCALE})` }}>
          <GridPicture grid={grid} />
        </div>
        <img className="dg-sort" src={ui('grid-sort')} alt="" />
        {grid && <span className="dg-sort-name">{grid.name}</span>}
        <img className="dg-filters" src={ui('grid-filters')} alt="" />
      </div>
      <TopBar hero />
      <img className="dm-chat" src={ui('chat')} alt="" />
      <img className="dm-play" src={ui('play')} alt="" />
    </Layer>
  );
}

/** Content of a fixed size (the grid's 1193 × 593) scaled to the width of its box. */
export function FitWidth({ width, children }: { width: number; children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.5);
  useLayoutEffect(() => {
    const fit = () => box.current && setScale(box.current.clientWidth / width);
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(box.current!);
    return () => ro.disconnect();
  }, [width]);
  return (
    <div ref={box} className="fitw">
      <div className="fitw__inner" style={{ transform: `scale(${scale})` }}>
        {children}
      </div>
    </div>
  );
}
