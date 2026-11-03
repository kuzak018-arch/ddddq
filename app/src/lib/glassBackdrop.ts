/**
 * The blurred wallpaper under the glass panels, made once instead of live.
 *
 * `backdrop-filter` re-blurs what is behind a panel on every frame anything moves (snow, a video
 * wallpaper, a hero model, page animations), and WebView2 does it in pieces: the light bands and
 * flicker in the glass, and the lag. The panels sit right on the wallpaper, so the same picture can
 * be blurred once on a small canvas and shown under every panel as a fixed background lined up
 * with the wallpaper (CSS: html.glass-img .glass::before). A video wallpaper is re-blurred a couple
 * of times a second, a gradient wallpaper is used as it is (it is already soft). When the picture
 * cannot be read (a hero render from a CDN without CORS) the live blur stays.
 */

export type Material = 'glass' | 'matte' | 'acrylic' | 'dota';

export const MATERIALS: { value: Material; label: string; title: string }[] = [
  { value: 'dota', label: 'Чёткий', title: 'Плотные тёмные панели с тонкой кромкой и острыми углами, без свечения — как в клиенте Доты' },
  { value: 'glass', label: 'Жидкое стекло', title: 'Прозрачные панели с бликом и светлой кромкой поверх размытых обоев' },
  { value: 'matte', label: 'Матовое', title: 'Сильно размытое, почти непрозрачное стекло: спокойнее и читается на любых обоях' },
  { value: 'acrylic', label: 'Акрил', title: 'Как в Windows 11: размытие с цветом обоев и мелким зерном' },
];

/** Blur (CSS px) and saturation of the picture under the panels for each material. */
export const MATERIAL_BLUR: Record<Material, { blur: number; saturate: number }> = {
  glass: { blur: 26, saturate: 1.6 },
  matte: { blur: 48, saturate: 1.15 },
  acrylic: { blur: 34, saturate: 1.35 },
  dota: { blur: 0, saturate: 1 },
};

const CANVAS_W = 320;

/** Where a picture of iw×ih lands when it covers a cw×ch box at object-position px%/py%. */
export function coverRect(iw: number, ih: number, cw: number, ch: number, px: number, py: number) {
  const s = Math.max(cw / iw, ch / ih);
  const dw = iw * s;
  const dh = ih * s;
  return { x: (cw - dw) * (px / 100), y: (ch - dh) * (py / 100), w: dw, h: dh };
}

/**
 * A small blurred copy of the picture at the window's aspect, as a data URL; null when the
 * picture can't be read back (tainted by another origin). The edges are drawn from a larger
 * canvas so the blur does not darken them.
 */
export function blurPicture(src: CanvasImageSource, iw: number, ih: number, view: { w: number; h: number }, pos: { x: number; y: number }, m: Material): string | null {
  if (!iw || !ih || !view.w || !view.h) return null;
  const { blur, saturate } = MATERIAL_BLUR[m];
  const cw = CANVAS_W;
  const ch = Math.max(8, Math.round((CANVAS_W * view.h) / view.w));
  const k = cw / view.w;
  const pad = Math.ceil(blur * k * 2.5) + 2;
  const big = document.createElement('canvas');
  big.width = cw + 2 * pad;
  big.height = ch + 2 * pad;
  const g = big.getContext('2d');
  if (!g) return null;
  const r = coverRect(iw, ih, big.width, big.height, pos.x, pos.y);
  g.drawImage(src, r.x, r.y, r.w, r.h);
  const out = document.createElement('canvas');
  out.width = cw;
  out.height = ch;
  const o = out.getContext('2d');
  if (!o) return null;
  o.filter = `blur(${(blur * k).toFixed(2)}px) saturate(${saturate})`;
  o.drawImage(big, -pad, -pad);
  try {
    return out.toDataURL('image/jpeg', 0.86);
  } catch {
    return null; // another origin without CORS: the canvas is tainted
  }
}

/** Loads a picture for blurring; null when it fails or can't be read back. */
export function loadPicture(url: string): Promise<HTMLImageElement | null> {
  return new Promise((ok) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => ok(img);
    img.onerror = () => ok(null);
    img.src = url;
  });
}

/** Sets (or clears) the picture under the glass: a CSS background value. `picture`: a blurred
 * copy made at the window's size (stretched over the viewport); otherwise a gradient wallpaper. */
export function setGlassPicture(css: string | null, picture = false): void {
  const root = document.documentElement;
  if (css) {
    root.style.setProperty('--glass-img', css);
    root.classList.add('glass-img');
  } else {
    root.style.removeProperty('--glass-img');
    root.classList.remove('glass-img');
  }
  root.classList.toggle('glass-pic', !!css && picture);
}
