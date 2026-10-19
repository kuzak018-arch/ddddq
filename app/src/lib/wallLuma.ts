/**
 * How bright the wallpaper is, so the glass can darken itself on a bright picture and white text
 * stays readable on any background. The picture is drawn small and its bright end (75th
 * percentile of relative luminance) is what counts: text sits on any part of it.
 */

const SIZE = 48;

/** Relative luminance (WCAG) of the bright end of the drawn picture, 0..1; null if unreadable. */
function measure(draw: (g: CanvasRenderingContext2D, w: number, h: number) => void): number | null {
  const c = document.createElement('canvas');
  c.width = SIZE;
  c.height = Math.round(SIZE * 0.6);
  const g = c.getContext('2d', { willReadFrequently: true });
  if (!g) return null;
  try {
    draw(g, c.width, c.height);
    const d = g.getImageData(0, 0, c.width, c.height).data;
    const lin = (v: number) => {
      const s = v / 255;
      return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    };
    const ls: number[] = [];
    for (let i = 0; i < d.length; i += 4) {
      const a = d[i + 3]! / 255; // transparent parts of a hero render show the dark page under them
      ls.push(a * (0.2126 * lin(d[i]!) + 0.7152 * lin(d[i + 1]!) + 0.0722 * lin(d[i + 2]!)));
    }
    ls.sort((x, y) => x - y);
    return ls[Math.floor(ls.length * 0.75)] ?? null;
  } catch {
    return null; // a cross-origin picture taints the canvas
  }
}

export async function lumaOfBlob(blob: Blob): Promise<number | null> {
  if (blob.type.startsWith('video/')) {
    const url = URL.createObjectURL(blob);
    try {
      return await lumaOfVideo(url);
    } finally {
      URL.revokeObjectURL(url);
    }
  }
  try {
    const bmp = await createImageBitmap(blob);
    const l = measure((g, w, h) => g.drawImage(bmp, 0, 0, w, h));
    bmp.close();
    return l;
  } catch {
    return null;
  }
}

export function lumaOfUrl(url: string): Promise<number | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(measure((g, w, h) => g.drawImage(img, 0, 0, w, h)));
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

function lumaOfVideo(url: string): Promise<number | null> {
  return new Promise((resolve) => {
    const v = document.createElement('video');
    v.muted = true;
    v.preload = 'auto';
    const done = (l: number | null) => {
      v.removeAttribute('src');
      v.load();
      resolve(l);
    };
    v.onloadeddata = () => {
      v.currentTime = Math.min(1, (v.duration || 2) / 2);
    };
    v.onseeked = () => done(measure((g, w, h) => g.drawImage(v, 0, 0, w, h)));
    v.onerror = () => done(null);
    setTimeout(() => done(null), 8000);
    v.src = url;
  });
}

/**
 * How much black to lay under the glass: white text needs a background of luminance <= ~0.18
 * (contrast 4.5:1). The glass itself is 10% white over the wallpaper, the user's dim darkens it.
 */
export function veilFor(luma: number, dim: number): number {
  const wall = luma * (1 - dim);
  const glass = 0.1 + 0.9 * wall;
  return Math.max(0, Math.min(0.65, 1 - 0.18 / glass));
}
