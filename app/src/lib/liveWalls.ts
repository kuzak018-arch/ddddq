/**
 * Live wallpapers: scenes drawn on a canvas, about 30 frames a second at no more than 1280 px
 * across (they are soft; the canvas is stretched over the window). Detail comes from fractal
 * noise textures made once per scene (clouds, smoke, mist), particles drawn with pre-made glow
 * sprites, and silhouettes. In performance mode, during a match or with "reduce motion" a scene
 * draws one frame and stops.
 */

export interface LiveWall {
  id: string;
  name: string;
  /** brightness for the glass veil (see wallLuma.ts) */
  luma: number;
}

export const LIVE_WALLS: LiveWall[] = [
  { id: 'nebula', name: 'Туманность', luma: 0.08 },
  { id: 'aurora', name: 'Сияние', luma: 0.08 },
  { id: 'embers', name: 'Угли · Dire', luma: 0.07 },
  { id: 'fireflies', name: 'Светлячки · Radiant', luma: 0.06 },
  { id: 'bokeh', name: 'Огни', luma: 0.09 },
];

type Draw = (g: CanvasRenderingContext2D, t: number) => void;
type Make = (w: number, h: number, rnd: () => number) => Draw;
type Rgb = [number, number, number];

const TAU = Math.PI * 2;
const MAX_W = 1280;
const FPS = 30;

function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const hex = (c: string): Rgb => [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)];
const rgba = ([r, g, b]: Rgb, a: number) => `rgba(${r},${g},${b},${a})`;
const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

function canvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return [c, c.getContext('2d')!];
}

/** A soft round glow of one colour, drawn once and stretched to any size. */
const sprites = new Map<string, HTMLCanvasElement>();
function glow(color: string, kind: 'soft' | 'disc' = 'soft'): HTMLCanvasElement {
  const key = color + kind;
  let s = sprites.get(key);
  if (s) return s;
  const [c, g] = canvas(64, 64);
  const rgb = hex(color);
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  if (kind === 'soft') {
    gr.addColorStop(0, rgba(rgb, 1));
    gr.addColorStop(0.25, rgba(rgb, 0.55));
    gr.addColorStop(1, rgba(rgb, 0));
  } else {
    // a bokeh disc: flat with a slightly brighter rim and a soft edge
    gr.addColorStop(0, rgba(rgb, 0.5));
    gr.addColorStop(0.78, rgba(rgb, 0.6));
    gr.addColorStop(0.9, rgba(rgb, 0.85));
    gr.addColorStop(1, rgba(rgb, 0));
  }
  g.fillStyle = gr;
  g.fillRect(0, 0, 64, 64);
  sprites.set(key, c);
  return c;
}

/**
 * Fractal value noise (fbm, wraps around on both axes so it can scroll), coloured by `paint`
 * (n in 0..1 → colour and alpha). Small: it is stretched over the window and so stays soft.
 */
function noiseTexture(rnd: () => number, tw: number, th: number, cell: number, paint: (n: number, x: number, y: number) => [Rgb, number]) {
  const [c, g] = canvas(tw, th);
  const octaves: { gw: number; gh: number; v: Float32Array }[] = [];
  for (let o = 0, gw = Math.max(2, Math.round(tw / cell)), gh = Math.max(2, Math.round(th / cell)); o < 5; o++, gw *= 2, gh *= 2) {
    const v = new Float32Array(gw * gh);
    for (let i = 0; i < v.length; i++) v[i] = rnd();
    octaves.push({ gw, gh, v });
  }
  const img = g.createImageData(tw, th);
  for (let y = 0; y < th; y++) {
    for (let x = 0; x < tw; x++) {
      let n = 0;
      let amp = 0.5;
      let sum = 0;
      for (const { gw, gh, v } of octaves) {
        const fx = (x / tw) * gw;
        const fy = (y / th) * gh;
        const x0 = Math.floor(fx);
        const y0 = Math.floor(fy);
        const sx = fx - x0;
        const sy = fy - y0;
        const ux = sx * sx * (3 - 2 * sx);
        const uy = sy * sy * (3 - 2 * sy);
        const x1 = (x0 + 1) % gw;
        const y1 = (y0 + 1) % gh;
        const a = v[y0 * gw + x0]! + (v[y0 * gw + x1]! - v[y0 * gw + x0]!) * ux;
        const b = v[y1 * gw + x0]! + (v[y1 * gw + x1]! - v[y1 * gw + x0]!) * ux;
        n += (a + (b - a) * uy) * amp;
        sum += amp;
        amp *= 0.5;
      }
      const [rgb, al] = paint(n / sum, x / tw, y / th);
      const i = (y * tw + x) * 4;
      img.data[i] = rgb[0];
      img.data[i + 1] = rgb[1];
      img.data[i + 2] = rgb[2];
      img.data[i + 3] = Math.round(Math.min(1, Math.max(0, al)) * 255);
    }
  }
  g.putImageData(img, 0, 0);
  return c;
}

const mix = (a: Rgb, b: Rgb, t: number): Rgb => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

/** Darker corners, made once per size. */
function vignette(w: number, h: number, strength = 0.55) {
  const [c, g] = canvas(w, h);
  const gr = g.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.hypot(w, h) * 0.62);
  gr.addColorStop(0, 'rgba(0,0,0,0)');
  gr.addColorStop(1, `rgba(0,0,0,${strength})`);
  g.fillStyle = gr;
  g.fillRect(0, 0, w, h);
  return c;
}

/** Draws a texture scrolled by (dx, dy) px, repeated so the scroll never shows an edge. */
function scroll(g: CanvasRenderingContext2D, tex: HTMLCanvasElement, x: number, y: number, w: number, h: number, dx: number, dy: number) {
  const ox = ((dx % w) + w) % w;
  const oy = ((dy % h) + h) % h;
  for (const ix of [-1, 0]) for (const iy of [-1, 0]) g.drawImage(tex, x + ox + ix * w, y + oy + iy * h, w, h);
}

interface Star {
  x: number;
  y: number;
  r: number;
  tw: number;
  ph: number;
  depth: number;
}
function stars(rnd: () => number, w: number, h: number, density: number, maxY = 1): Star[] {
  return Array.from({ length: Math.round((w * h * maxY) / density) }, () => ({
    x: rnd() * w,
    y: rnd() ** 1.3 * h * maxY,
    r: 0.6 + rnd() ** 4 * 1.8,
    tw: 0.4 + rnd() * 2.2,
    ph: rnd() * TAU,
    depth: 0.25 + rnd() * 0.75,
  }));
}
function drawStars(g: CanvasRenderingContext2D, list: Star[], t: number, w: number, drift: number) {
  g.fillStyle = '#fff';
  for (const s of list) {
    const x = (((s.x - t * drift * s.depth) % w) + w) % w;
    const tw = 0.55 + 0.45 * Math.sin(t * s.tw + s.ph);
    g.globalAlpha = (0.25 + 0.75 * s.depth) * tw;
    g.fillRect(x, s.y, s.r, s.r);
    if (s.r > 2) {
      g.globalAlpha *= 0.35;
      g.drawImage(glow('#cfe0ff'), x - s.r * 3, s.y - s.r * 3, s.r * 7, s.r * 7);
    }
  }
  g.globalAlpha = 1;
}

/** A mountain or rock ridge (midpoint displacement), as points across the width. */
function ridge(rnd: () => number, base: number, rough: number, n = 64): number[] {
  const p = new Array(n + 1).fill(base) as number[];
  let step = n;
  let amp = rough;
  p[0] = base + (rnd() - 0.5) * rough;
  p[n] = base + (rnd() - 0.5) * rough;
  while (step > 1) {
    for (let i = step / 2; i < n; i += step) p[i] = (p[i - step / 2]! + p[i + step / 2]!) / 2 + (rnd() - 0.5) * amp;
    step /= 2;
    amp *= 0.55;
  }
  return p;
}
function fillRidge(g: CanvasRenderingContext2D, pts: number[], w: number, h: number) {
  g.beginPath();
  g.moveTo(0, h);
  pts.forEach((y, i) => g.lineTo((i / (pts.length - 1)) * w, y));
  g.lineTo(w, h);
  g.closePath();
  g.fill();
}

// ---------- scenes ------------------------------------------------------------------------------

const nebula: Make = (w, h, rnd) => {
  const tw = 240;
  const th = Math.round((tw * h) / w);
  const deep: Rgb = hex('#2a0b5e');
  const pink: Rgb = hex('#d0307a');
  const teal: Rgb = hex('#1aa6b7');
  const blue: Rgb = hex('#2747c9');
  const cloudA = noiseTexture(rnd, tw, th, 60, (n, x, y) => {
    const a = smooth(0.42, 0.8, n) * (0.55 + 0.45 * Math.sin(x * 3.1 + y * 2.3));
    return [mix(deep, pink, smooth(0.5, 0.85, n)), a];
  });
  const cloudB = noiseTexture(rnd, tw, th, 45, (n, x) => [mix(blue, teal, smooth(0.45, 0.9, n)), smooth(0.48, 0.86, n) * (0.4 + 0.6 * x)]);
  const dust = noiseTexture(rnd, tw, th, 30, (n) => [[2, 2, 8], smooth(0.55, 0.8, n) * 0.75]);
  const sky = stars(rnd, w, h, 1500);
  const vig = vignette(w, h, 0.6);
  return (g, t) => {
    g.globalCompositeOperation = 'source-over';
    g.fillStyle = '#04040b';
    g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = 'lighter';
    drawStars(g, sky, t, w, 1.6);
    const ox = Math.sin(t * 0.021) * w * 0.04;
    const oy = Math.cos(t * 0.017) * h * 0.04;
    g.globalAlpha = 0.95;
    g.drawImage(cloudA, -w * 0.08 + ox, -h * 0.08 + oy, w * 1.16, h * 1.16);
    g.globalAlpha = 0.75;
    g.drawImage(cloudB, -w * 0.12 - ox * 1.6, -h * 0.1 - oy * 1.3, w * 1.24, h * 1.2);
    // a slow breathing core of light
    const p = 0.75 + 0.25 * Math.sin(t * 0.35);
    g.globalAlpha = 0.28 * p;
    g.drawImage(glow('#ff7ac8'), w * 0.58 - h * 0.5, h * 0.42 - h * 0.5, h, h);
    g.globalAlpha = 1;
    g.globalCompositeOperation = 'source-over';
    g.globalAlpha = 0.85;
    g.drawImage(dust, -w * 0.1 + ox * 2.2, -h * 0.1 + oy * 2, w * 1.2, h * 1.2);
    g.globalAlpha = 1;
    g.drawImage(vig, 0, 0);
  };
};

const aurora: Make = (w, h, rnd) => {
  const sky = stars(rnd, w, h, 1300, 0.75);
  const far = ridge(rnd, h * 0.8, h * 0.22);
  const near = ridge(rnd, h * 0.9, h * 0.16);
  const [buf, bg] = canvas(Math.round(w / 4), Math.round(h / 4));
  const bw = buf.width;
  const bh = buf.height;
  // one column of the curtain: bright at the lower edge, fading up into violet
  const [cur, cg] = canvas(1, 128);
  const cgr = cg.createLinearGradient(0, 0, 0, 128);
  cgr.addColorStop(0, 'rgba(150,80,255,0)');
  cgr.addColorStop(0.45, 'rgba(110,90,255,0.35)');
  cgr.addColorStop(0.82, 'rgba(60,255,170,0.9)');
  cgr.addColorStop(0.94, 'rgba(190,255,220,1)');
  cgr.addColorStop(1, 'rgba(60,255,170,0)');
  cg.fillStyle = cgr;
  cg.fillRect(0, 0, 1, 128);
  const ribbons = [0, 1, 2].map((i) => ({ base: 0.32 + i * 0.1, f1: 0.9 + rnd(), f2: 2.4 + rnd() * 2, s: 0.04 + rnd() * 0.05, ph: rnd() * TAU, len: 0.22 + rnd() * 0.12, a: 0.7 - i * 0.18 }));
  const skyGr = (g: CanvasRenderingContext2D) => {
    const gr = g.createLinearGradient(0, 0, 0, h);
    gr.addColorStop(0, '#030512');
    gr.addColorStop(0.6, '#06142a');
    gr.addColorStop(1, '#0b2a33');
    return gr;
  };
  let skyFill: CanvasGradient | null = null;
  const vig = vignette(w, h, 0.5);
  return (g, t) => {
    g.globalCompositeOperation = 'source-over';
    g.fillStyle = skyFill ??= skyGr(g);
    g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = 'lighter';
    drawStars(g, sky, t, w, 0.6);
    bg.globalCompositeOperation = 'source-over';
    bg.clearRect(0, 0, bw, bh);
    bg.globalCompositeOperation = 'lighter';
    for (const r of ribbons) {
      for (let x = 0; x < bw; x++) {
        const u = x / bw;
        const base = bh * (r.base + 0.07 * Math.sin(u * TAU * r.f1 * 0.5 + t * r.s + r.ph) + 0.025 * Math.sin(u * TAU * r.f2 - t * r.s * 2.3));
        const len = bh * r.len * (0.75 + 0.35 * Math.sin(u * 9 + t * 0.21 + r.ph));
        const i = 0.35 + 0.65 * Math.sin(u * 13 + t * 0.5 + r.ph) ** 2;
        const ripple = 0.75 + 0.25 * Math.sin(u * 70 - t * 1.4 + r.ph);
        bg.globalAlpha = r.a * i * ripple * smooth(0, 0.12, u) * smooth(1, 0.88, u);
        bg.drawImage(cur, x, base - len, 1, len * 1.12);
      }
    }
    bg.globalAlpha = 1;
    g.globalAlpha = 0.9;
    g.drawImage(buf, 0, 0, w, h);
    // the glow on the horizon and the land
    g.globalAlpha = 0.22;
    g.drawImage(glow('#3cffaa'), -w * 0.1, h * 0.55, w * 1.2, h * 0.5);
    g.globalAlpha = 1;
    g.globalCompositeOperation = 'source-over';
    g.fillStyle = '#07101a';
    fillRidge(g, far, w, h);
    g.fillStyle = '#02050a';
    fillRidge(g, near, w, h);
    g.drawImage(vig, 0, 0);
  };
};

interface Spark {
  x: number;
  y: number;
  vy: number;
  wob: number;
  ph: number;
  r: number;
}

const embers: Make = (w, h, rnd) => {
  const tw = 200;
  const th = Math.round((tw * h) / w);
  const smoke = noiseTexture(rnd, tw, th, 40, (n, _x, y) => [mix(hex('#3a0a06'), hex('#7a1d0c'), smooth(0.5, 0.9, n)), smooth(0.4, 0.85, n) * (0.25 + 0.75 * y)]);
  const rocks = ridge(rnd, h * 0.86, h * 0.14, 128);
  const back = ridge(rnd, h * 0.72, h * 0.34, 64);
  const s = Math.min(w, h) / 720;
  const spawn = (y?: number): Spark => ({
    x: rnd() * w,
    y: y ?? h * (0.85 + rnd() * 0.2),
    vy: (18 + rnd() * 46) * s,
    wob: (6 + rnd() * 22) * s,
    ph: rnd() * TAU,
    r: (0.8 + rnd() ** 2 * 2.4) * s,
  });
  const sparks = Array.from({ length: Math.round((w * h) / 7000) }, () => spawn(rnd() * h));
  const vig = vignette(w, h, 0.5);
  let last = 0;
  let fill: CanvasGradient | null = null;
  return (g, t) => {
    const dt = Math.min(0.1, Math.max(0, t - last));
    last = t;
    g.globalCompositeOperation = 'source-over';
    if (!fill) {
      fill = g.createLinearGradient(0, 0, 0, h);
      fill.addColorStop(0, '#050203');
      fill.addColorStop(0.65, '#170405');
      fill.addColorStop(1, '#2c0703');
    }
    g.fillStyle = fill;
    g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = 'lighter';
    const p = 0.8 + 0.2 * Math.sin(t * 0.6) + 0.06 * Math.sin(t * 2.3);
    g.globalAlpha = 0.55 * p;
    g.drawImage(glow('#ff4a12'), -w * 0.2, h * 0.5, w * 1.4, h);
    g.globalAlpha = 0.35 * p;
    g.drawImage(glow('#ffae3b'), w * 0.15, h * 0.72, w * 0.7, h * 0.5);
    g.globalAlpha = 0.8;
    scroll(g, smoke, 0, 0, w, h, Math.sin(t * 0.05) * w * 0.05, -t * 10 * s);
    g.globalAlpha = 1;
    g.globalCompositeOperation = 'source-over';
    g.fillStyle = '#120405';
    fillRidge(g, back, w, h);
    g.fillStyle = '#060102';
    fillRidge(g, rocks, w, h);
    // the lava light on the rocks' edge
    g.globalCompositeOperation = 'lighter';
    g.strokeStyle = 'rgba(255,90,30,0.35)';
    g.lineWidth = 2 * s;
    g.beginPath();
    rocks.forEach((y, i) => (i ? g.lineTo((i / (rocks.length - 1)) * w, y) : g.moveTo(0, y)));
    g.stroke();
    for (const sp of sparks) {
      sp.y -= sp.vy * dt;
      if (sp.y < -20) Object.assign(sp, spawn());
      const x = sp.x + Math.sin(t * 0.9 + sp.ph) * sp.wob;
      const k = Math.min(1, Math.max(0, sp.y / h));
      const life = smooth(0, 0.55, k);
      const color = k > 0.6 ? '#ffd27a' : k > 0.35 ? '#ff8a2a' : '#ff3d1a';
      g.globalAlpha = 0.5 * life;
      g.drawImage(glow(color), x - sp.r * 5, sp.y - sp.r * 5, sp.r * 10, sp.r * 10);
      g.globalAlpha = 0.9 * life;
      g.fillStyle = color;
      g.fillRect(x - sp.r / 2, sp.y - sp.r / 2, sp.r, sp.r);
    }
    g.globalAlpha = 1;
    g.globalCompositeOperation = 'source-over';
    g.drawImage(vig, 0, 0);
  };
};

const fireflies: Make = (w, h, rnd) => {
  const tw = 220;
  const th = Math.round(((tw * h) / w) * 0.5);
  const mist = noiseTexture(rnd, tw, th, 40, (n, _x, y) => [mix(hex('#2a5a48'), hex('#7fbfa0'), n), smooth(0.45, 0.85, n) * Math.sin(y * Math.PI) * 0.8]);
  const s = Math.min(w, h) / 720;
  // pines: trunks of stacked triangles, a far and a near row at the sides
  const pines = (n: number, scale: number, edge: number) =>
    Array.from({ length: n }, () => {
      const left = rnd() < 0.5;
      const x = left ? rnd() * w * edge : w - rnd() * w * edge;
      return { x, hgt: h * (0.45 + rnd() * 0.45) * scale, wid: w * (0.05 + rnd() * 0.05) * scale };
    });
  const far = pines(14, 0.75, 0.38);
  const near = pines(9, 1.1, 0.24);
  const drawPines = (g: CanvasRenderingContext2D, list: typeof far, color: string) => {
    g.fillStyle = color;
    for (const p of list) {
      for (let k = 0; k < 6; k++) {
        const top = h - p.hgt + (p.hgt * k) / 7;
        const half = (p.wid * (k + 1.5)) / 7;
        g.beginPath();
        g.moveTo(p.x, top);
        g.lineTo(p.x - half, top + p.hgt / 4);
        g.lineTo(p.x + half, top + p.hgt / 4);
        g.closePath();
        g.fill();
      }
      g.fillRect(p.x - p.wid * 0.04, h - p.hgt * 0.25, p.wid * 0.08, p.hgt * 0.25);
    }
  };
  const flies = Array.from({ length: Math.round((w * h) / 16000) }, () => ({
    cx: rnd() * w,
    cy: h * (0.35 + rnd() * 0.6),
    ax: (30 + rnd() * 90) * s,
    ay: (20 + rnd() * 60) * s,
    fx: 0.05 + rnd() * 0.15,
    fy: 0.07 + rnd() * 0.15,
    ph: rnd() * TAU,
    fb: 0.4 + rnd() * 0.9,
    r: (2 + rnd() * 3) * s,
  }));
  const vig = vignette(w, h, 0.55);
  let fill: CanvasGradient | null = null;
  return (g, t) => {
    g.globalCompositeOperation = 'source-over';
    if (!fill) {
      fill = g.createLinearGradient(0, 0, 0, h);
      fill.addColorStop(0, '#081a24');
      fill.addColorStop(0.5, '#0a2a20');
      fill.addColorStop(1, '#040c08');
    }
    g.fillStyle = fill;
    g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = 'lighter';
    g.globalAlpha = 0.35;
    g.drawImage(glow('#9fe8ff'), w * 0.62, -h * 0.35, h * 0.9, h * 0.9);
    // light shafts from the moon, swaying a little
    for (let i = 0; i < 5; i++) {
      const a = -0.5 + i * 0.13 + Math.sin(t * 0.07 + i) * 0.03;
      g.save();
      g.translate(w * 0.82, -h * 0.05);
      g.rotate(a + Math.PI / 2);
      g.globalAlpha = 0.05 + 0.03 * Math.sin(t * 0.3 + i * 1.7);
      const gr = g.createLinearGradient(0, 0, h * 1.4, 0);
      gr.addColorStop(0, 'rgba(190,255,230,0.9)');
      gr.addColorStop(1, 'rgba(190,255,230,0)');
      g.fillStyle = gr;
      g.fillRect(0, -h * 0.04, h * 1.4, h * 0.08);
      g.restore();
    }
    g.globalAlpha = 1;
    g.globalCompositeOperation = 'source-over';
    drawPines(g, far, '#0b2219');
    g.globalAlpha = 0.5;
    scroll(g, mist, 0, h * 0.5, w, h * 0.5, t * 6 * s, 0);
    g.globalAlpha = 1;
    drawPines(g, near, '#020705');
    g.globalCompositeOperation = 'lighter';
    for (const f of flies) {
      const x = f.cx + Math.sin(t * f.fx + f.ph) * f.ax + Math.sin(t * f.fx * 2.7 + f.ph * 2) * f.ax * 0.3;
      const y = f.cy + Math.sin(t * f.fy + f.ph * 1.3) * f.ay;
      const b = Math.max(0, Math.sin(t * f.fb + f.ph)) ** 2;
      if (b < 0.02) continue;
      g.globalAlpha = 0.6 * b;
      g.drawImage(glow('#c8ff5a'), x - f.r * 7, y - f.r * 7, f.r * 14, f.r * 14);
      g.globalAlpha = b;
      g.drawImage(glow('#f4ffc0'), x - f.r, y - f.r, f.r * 2, f.r * 2);
    }
    g.globalAlpha = 1;
    g.globalCompositeOperation = 'source-over';
    g.drawImage(vig, 0, 0);
  };
};

const bokeh: Make = (w, h, rnd) => {
  const m = Math.max(w, h);
  const colors = ['#ffb347', '#ff5e9c', '#4fd1ff', '#8b6bff', '#ffd86b'];
  const discs = Array.from({ length: 46 }, () => ({
    x: rnd() * w,
    y: h * (0.15 + rnd() * 0.8),
    r: m * (0.015 + rnd() ** 2 * 0.07),
    c: colors[Math.floor(rnd() * colors.length)]!,
    vx: (rnd() - 0.5) * 6,
    ph: rnd() * TAU,
    f: 0.15 + rnd() * 0.4,
    a: 0.12 + rnd() * 0.2,
  }));
  const s = Math.min(w, h) / 720;
  const lights = Array.from({ length: Math.round(w / 6) }, () => ({ x: rnd() * w, y: h * (0.8 + rnd() ** 0.6 * 0.2), r: (0.6 + rnd() * 1.4) * s, c: colors[Math.floor(rnd() * 4)]!, ph: rnd() * TAU, f: 0.5 + rnd() * 2 }));
  const tw = 200;
  const haze = noiseTexture(rnd, tw, Math.round((tw * h) / w), 50, (n, _x, y) => [mix(hex('#2a1450'), hex('#5a2060'), n), smooth(0.4, 0.9, n) * (0.3 + 0.7 * y)]);
  const vig = vignette(w, h, 0.55);
  let fill: CanvasGradient | null = null;
  return (g, t) => {
    g.globalCompositeOperation = 'source-over';
    if (!fill) {
      fill = g.createLinearGradient(0, 0, 0, h);
      fill.addColorStop(0, '#07051a');
      fill.addColorStop(0.7, '#160a2a');
      fill.addColorStop(1, '#251032');
    }
    g.fillStyle = fill;
    g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = 'lighter';
    g.globalAlpha = 0.7;
    scroll(g, haze, 0, 0, w, h, t * 4 * s, 0);
    for (const d of discs) {
      const x = (((d.x + t * d.vx * s) % (w + 2 * d.r)) + w + 2 * d.r) % (w + 2 * d.r) - d.r;
      const y = d.y + Math.sin(t * d.f * 0.5 + d.ph) * 12 * s;
      g.globalAlpha = d.a * (0.6 + 0.4 * Math.sin(t * d.f + d.ph));
      g.drawImage(glow(d.c, 'disc'), x - d.r, y - d.r, d.r * 2, d.r * 2);
    }
    for (const l of lights) {
      g.globalAlpha = 0.5 + 0.5 * Math.sin(t * l.f + l.ph);
      g.drawImage(glow(l.c), l.x - l.r * 4, l.y - l.r * 4, l.r * 8, l.r * 8);
    }
    g.globalAlpha = 1;
    g.globalCompositeOperation = 'source-over';
    g.drawImage(vig, 0, 0);
  };
};

const SCENES: Record<string, Make> = { nebula, aurora, embers, fireflies, bokeh };

/** The canvas size for a window: no more than MAX_W across. */
export function liveSize(vw: number, vh: number) {
  const k = Math.min(1, MAX_W / Math.max(1, vw));
  return { w: Math.max(2, Math.round(vw * k)), h: Math.max(2, Math.round(vh * k)) };
}

/**
 * Runs scene `id` on the canvas (already sized). `still`: one frame and stop. Returns stop().
 * `onFrame` is called after each drawn frame.
 */
export function runLive(cv: HTMLCanvasElement, id: string, still: boolean, onFrame?: () => void): () => void {
  const make = SCENES[id] ?? nebula;
  const g = cv.getContext('2d');
  if (!g) return () => undefined;
  const draw = make(cv.width, cv.height, mulberry32(hashId(id)));
  // the scene's clock starts some seconds in, so the first frame is already lively
  const t0 = performance.now() - 20_000;
  let raf = 0;
  let last = -1;
  const frame = (now: number) => {
    if (now - last >= 1000 / FPS - 2) {
      last = now;
      draw(g, (now - t0) / 1000);
      onFrame?.();
    }
    raf = requestAnimationFrame(frame);
  };
  if (still) {
    draw(g, 20);
    onFrame?.();
  } else raf = requestAnimationFrame(frame);
  return () => cancelAnimationFrame(raf);
}

function hashId(id: string) {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619);
  return h >>> 0;
}

/** A still frame of a scene as a picture (the tiles in Settings). */
const stills = new Map<string, string>();
export function liveStill(id: string, w = 240, h = 136): string {
  const key = `${id}:${w}x${h}`;
  let url = stills.get(key);
  if (url) return url;
  const [c] = canvas(w, h);
  runLive(c, id, true);
  url = c.toDataURL('image/jpeg', 0.85);
  stills.set(key, url);
  return url;
}
