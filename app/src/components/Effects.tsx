/**
 * Background effects over the wallpaper: rain, snow, stars, fog, floating particles.
 *
 * Kept light on purpose: one 2D canvas at CSS-pixel resolution (no devicePixelRatio upscaling),
 * at most 30 frames a second, a few dozen to ~150 simple shapes; fog is drawn on a canvas four
 * times smaller and stretched (it is blurry anyway). Nothing runs while the window is hidden, in
 * the overlay, during a match (GSI), in performance mode or with "reduce motion" on in Windows.
 */
import { useEffect, useRef } from 'react';

import { isOverlayWindow } from '../lib/overlay';
import { useDraft } from '../state/draft';
import { useUi, type Effect } from '../state/ui';

const FRAME_MS = 1000 / 30;

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  r: number;
  a: number;
  t: number;
}

type Painter = { step: (g: CanvasRenderingContext2D, w: number, h: number, dt: number) => void; scale: number };

const rand = (a: number, b: number) => a + Math.random() * (b - a);

function makeRain(n: number, w: number, h: number): Painter {
  const drops: Particle[] = Array.from({ length: n }, () => ({ x: rand(0, w), y: rand(0, h), vx: -60, vy: rand(700, 1000), r: rand(10, 22), a: rand(0.12, 0.3), t: 0 }));
  return {
    scale: 1,
    step(g, W, H, dt) {
      g.clearRect(0, 0, W, H);
      g.lineWidth = 1;
      g.lineCap = 'round';
      for (const d of drops) {
        d.x += d.vx * dt;
        d.y += d.vy * dt;
        if (d.y > H + 20) {
          d.y = rand(-40, -10);
          d.x = rand(0, W + 60);
        }
        g.strokeStyle = `rgba(190, 210, 255, ${d.a})`;
        g.beginPath();
        g.moveTo(d.x, d.y);
        g.lineTo(d.x + (d.vx / d.vy) * d.r, d.y + d.r);
        g.stroke();
      }
    },
  };
}

function makeSnow(n: number, w: number, h: number): Painter {
  const flakes: Particle[] = Array.from({ length: n }, () => ({ x: rand(0, w), y: rand(0, h), vx: rand(-15, 15), vy: rand(25, 70), r: rand(0.8, 2.6), a: rand(0.35, 0.85), t: rand(0, 6.28) }));
  return {
    scale: 1,
    step(g, W, H, dt) {
      g.clearRect(0, 0, W, H);
      for (const f of flakes) {
        f.t += dt;
        f.x += (f.vx + Math.sin(f.t) * 12) * dt;
        f.y += f.vy * dt;
        if (f.y > H + 5) {
          f.y = -5;
          f.x = rand(0, W);
        }
        if (f.x < -5) f.x = W + 5;
        if (f.x > W + 5) f.x = -5;
        g.fillStyle = `rgba(255, 255, 255, ${f.a})`;
        g.beginPath();
        g.arc(f.x, f.y, f.r, 0, Math.PI * 2);
        g.fill();
      }
    },
  };
}

function makeStars(n: number, w: number, h: number): Painter {
  const stars: Particle[] = Array.from({ length: n }, () => ({ x: rand(0, w), y: rand(0, h), vx: 0, vy: 0, r: rand(0.5, 1.6), a: rand(0.3, 0.9), t: rand(0, 6.28) }));
  let shooting: Particle | null = null;
  return {
    scale: 1,
    step(g, W, H, dt) {
      g.clearRect(0, 0, W, H);
      for (const s of stars) {
        s.t += dt * rand(0.6, 1.4);
        const tw = 0.55 + 0.45 * Math.sin(s.t * 1.7);
        g.fillStyle = `rgba(235, 240, 255, ${s.a * tw})`;
        g.fillRect(s.x, s.y, s.r, s.r);
      }
      // now and then a shooting star
      if (!shooting && Math.random() < dt * 0.08) shooting = { x: rand(W * 0.2, W), y: rand(0, H * 0.4), vx: -rand(500, 800), vy: rand(150, 260), r: 0, a: 1, t: 0 };
      if (shooting) {
        const s = shooting;
        s.t += dt;
        s.x += s.vx * dt;
        s.y += s.vy * dt;
        const k = Math.max(0, 1 - s.t / 0.9);
        const grad = g.createLinearGradient(s.x, s.y, s.x - s.vx * 0.12, s.y - s.vy * 0.12);
        grad.addColorStop(0, `rgba(255,255,255,${0.9 * k})`);
        grad.addColorStop(1, 'rgba(255,255,255,0)');
        g.strokeStyle = grad;
        g.lineWidth = 1.5;
        g.beginPath();
        g.moveTo(s.x, s.y);
        g.lineTo(s.x - s.vx * 0.12, s.y - s.vy * 0.12);
        g.stroke();
        if (k <= 0) shooting = null;
      }
    },
  };
}

function makeFog(n: number, w: number, h: number): Painter {
  // drawn at 1/4 size: big soft blobs drifting sideways
  const blobs: Particle[] = Array.from({ length: n }, () => ({ x: rand(0, w), y: rand(h * 0.3, h), vx: rand(4, 10) * (Math.random() < 0.5 ? -1 : 1), vy: 0, r: rand(w * 0.25, w * 0.5), a: rand(0.05, 0.12), t: rand(0, 6.28) }));
  return {
    scale: 0.25,
    step(g, W, H, dt) {
      g.clearRect(0, 0, W, H);
      for (const b of blobs) {
        b.t += dt * 0.15;
        b.x += b.vx * dt;
        if (b.x - b.r > W) b.x = -b.r;
        if (b.x + b.r < 0) b.x = W + b.r;
        const a = b.a * (0.75 + 0.25 * Math.sin(b.t));
        const grad = g.createRadialGradient(b.x, b.y, 0, b.x, b.y, b.r);
        grad.addColorStop(0, `rgba(220, 225, 235, ${a})`);
        grad.addColorStop(1, 'rgba(220, 225, 235, 0)');
        g.fillStyle = grad;
        g.fillRect(b.x - b.r, b.y - b.r, b.r * 2, b.r * 2);
      }
    },
  };
}

function makeParticles(n: number, w: number, h: number): Painter {
  const ps: Particle[] = Array.from({ length: n }, () => ({ x: rand(0, w), y: rand(0, h), vx: rand(-8, 8), vy: rand(-22, -8), r: rand(1, 2.6), a: rand(0.25, 0.7), t: rand(0, 6.28) }));
  return {
    scale: 1,
    step(g, W, H, dt) {
      g.clearRect(0, 0, W, H);
      for (const p of ps) {
        p.t += dt;
        p.x += (p.vx + Math.sin(p.t * 0.7) * 6) * dt;
        p.y += p.vy * dt;
        if (p.y < -10) {
          p.y = H + 10;
          p.x = rand(0, W);
        }
        const a = p.a * (0.6 + 0.4 * Math.sin(p.t * 1.3));
        g.fillStyle = `rgba(255, 214, 150, ${a})`;
        g.beginPath();
        g.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        g.fill();
      }
    },
  };
}

/** How many shapes at full intensity (scaled by window area against 1920×1080). Exported for timing. */
export const MAKERS: Record<Exclude<Effect, 'none'>, { make: (n: number, w: number, h: number) => Painter; max: number }> = {
  rain: { make: makeRain, max: 160 },
  snow: { make: makeSnow, max: 130 },
  stars: { make: makeStars, max: 170 },
  fog: { make: makeFog, max: 7 },
  particles: { make: makeParticles, max: 70 },
};

/** Why effects are off right now, or null when they may run here and now. */
export function useEffectsBlocked(): string | null {
  const performance = useUi((s) => s.performance);
  const phase = useDraft((s) => s.phase);
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if (isOverlayWindow()) return 'не рисуется в оверлее';
  if (performance) return 'сейчас выключен: включён режим производительности';
  if (phase === 'game') return 'сейчас выключен: идёт матч';
  if (reduced) return 'сейчас выключен: в Windows отключены эффекты анимации (Параметры → Специальные возможности → Визуальные эффекты)';
  return null;
}

/** Whether effects may run here and now. */
export function useEffectsAllowed(): boolean {
  return useEffectsBlocked() === null;
}

export function Effects() {
  const fx = useUi((s) => s.fx);
  const allowed = useEffectsAllowed();
  const canvas = useRef<HTMLCanvasElement>(null);
  const on = allowed && fx.kind !== 'none';

  useEffect(() => {
    const c = canvas.current;
    if (!on || !c || fx.kind === 'none') return;
    const g = c.getContext('2d');
    if (!g) return;
    const spec = MAKERS[fx.kind];
    let painter: Painter;
    let W = 0;
    let H = 0;
    const resize = () => {
      const scale = fx.kind === 'fog' ? 0.25 : 1;
      W = Math.max(1, Math.round(window.innerWidth * scale));
      H = Math.max(1, Math.round(window.innerHeight * scale));
      c.width = W;
      c.height = H;
      const area = (window.innerWidth * window.innerHeight) / (1920 * 1080);
      const n = Math.max(fx.kind === 'fog' ? 2 : 8, Math.round(spec.max * fx.intensity * Math.min(1.5, Math.max(0.5, area))));
      painter = spec.make(n, W, H);
    };
    resize();
    let raf = 0;
    let last = performance.now();
    let acc = 0;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      acc += now - last;
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (acc < FRAME_MS) return; // 30 fps is plenty for drifting snow
      acc = 0;
      painter.step(g, W, H, Math.max(dt, FRAME_MS / 1000));
    };
    const start = () => {
      cancelAnimationFrame(raf);
      last = performance.now();
      if (!document.hidden) raf = requestAnimationFrame(loop);
    };
    start();
    window.addEventListener('resize', resize);
    document.addEventListener('visibilitychange', start);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', start);
      g.clearRect(0, 0, c.width, c.height);
    };
  }, [on, fx.kind, fx.intensity]);

  if (!on) return null;
  return <canvas ref={canvas} className={`fx fx--${fx.kind}`} aria-hidden />;
}
