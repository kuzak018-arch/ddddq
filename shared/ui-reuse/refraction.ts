/**
 * Liquid Glass edge refraction.
 *
 * Chromium can run an SVG filter as a `backdrop-filter: url(#id)`. For every glass
 * surface we render a displacement map shaped like the element's rounded rectangle:
 * neutral in the middle, bending the backdrop inward along a "bezel" near the edges —
 * the lens look of iOS 26 Liquid Glass. Maps are regenerated when the element resizes.
 *
 * Safari and Firefox don't support `url()` in backdrop-filter (Safari even reports
 * support but renders nothing), so they keep the plain `blur() saturate()` glass from CSS.
 */

interface RefractOptions {
  /** Width of the refracting rim, px. */
  bezel?: number;
  /** Max displacement, px. */
  scale?: number;
  blur?: number;
  saturate?: number;
}

const SVG_NS = 'http://www.w3.org/2000/svg';

function detect(): boolean {
  const uaData = (navigator as Navigator & { userAgentData?: { brands: { brand: string }[] } }).userAgentData;
  const isChromium = !!uaData?.brands.some((b) => /Chromium|Google Chrome|Microsoft Edge|Opera/i.test(b.brand));
  return isChromium && CSS.supports('backdrop-filter', 'url(#x)');
}

export const refractionSupported = typeof window !== 'undefined' && detect();

let defs: SVGDefsElement | null = null;
let counter = 0;

function ensureDefs(): SVGDefsElement {
  if (defs) return defs;
  const root = document.createElementNS(SVG_NS, 'svg');
  root.setAttribute('aria-hidden', 'true');
  root.setAttribute('width', '0');
  root.setAttribute('height', '0');
  // not display:none — some engines drop filters inside hidden SVGs
  root.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;pointer-events:none';
  defs = document.createElementNS(SVG_NS, 'defs');
  root.append(defs);
  document.body.prepend(root);
  return defs;
}

/**
 * Builds a displacement map for a rounded rectangle using its signed distance field.
 * R/G = 0.5 + 0.5 · strength · inward normal (x / y). Rendered at reduced resolution —
 * the map is smooth, and the filter stretches it to the element size.
 */
function displacementMap(w: number, h: number, radius: number, bezel: number): string {
  const k = Math.min(0.5, 600 / Math.max(w, h));
  const cw = Math.max(8, Math.round(w * k));
  const ch = Math.max(8, Math.round(h * k));
  const canvas = document.createElement('canvas');
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext('2d')!;
  const img = ctx.createImageData(cw, ch);
  const data = img.data;

  const hw = w / 2;
  const hh = h / 2;
  const r = Math.min(radius, hw, hh);

  for (let py = 0; py < ch; py++) {
    for (let px = 0; px < cw; px++) {
      // pixel center in element coordinates, relative to the center
      const x = ((px + 0.5) / cw) * w - hw;
      const y = ((py + 0.5) / ch) * h - hh;
      const ax = Math.abs(x);
      const ay = Math.abs(y);
      const qx = ax - (hw - r);
      const qy = ay - (hh - r);

      // signed distance (negative inside) and outward normal
      let dist: number;
      let nx: number;
      let ny: number;
      if (qx > 0 && qy > 0) {
        const len = Math.hypot(qx, qy) || 1;
        dist = len - r;
        nx = qx / len;
        ny = qy / len;
      } else if (qx > qy) {
        dist = qx - r;
        nx = 1;
        ny = 0;
      } else {
        dist = qy - r;
        nx = 0;
        ny = 1;
      }
      nx *= Math.sign(x) || 1;
      ny *= Math.sign(y) || 1;

      const depth = -dist; // distance from the edge, inside
      let s = 0;
      if (depth >= 0 && depth < bezel) {
        const t = 1 - depth / bezel; // 1 at the edge → 0 at the inner bezel line
        s = t * t * (3 - 2 * t); // smoothstep: soft convex lens
      }
      const i = (py * cw + px) * 4;
      // sample from inside (inward normal = −outward): magnifies the rim
      data[i] = Math.round(128 - 127 * s * nx);
      data[i + 1] = Math.round(128 - 127 * s * ny);
      data[i + 2] = 128;
      data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL('image/png');
}

function createFilter(id: string): { filter: SVGFilterElement; image: SVGFEImageElement; map: SVGFEDisplacementMapElement } {
  const filter = document.createElementNS(SVG_NS, 'filter');
  filter.id = id;
  filter.setAttribute('filterUnits', 'userSpaceOnUse');
  filter.setAttribute('primitiveUnits', 'userSpaceOnUse');
  filter.setAttribute('color-interpolation-filters', 'sRGB');
  filter.setAttribute('x', '0');
  filter.setAttribute('y', '0');

  const image = document.createElementNS(SVG_NS, 'feImage');
  image.setAttribute('x', '0');
  image.setAttribute('y', '0');
  image.setAttribute('preserveAspectRatio', 'none');
  image.setAttribute('result', 'map');

  const blur = document.createElementNS(SVG_NS, 'feGaussianBlur');
  blur.setAttribute('in', 'map');
  blur.setAttribute('stdDeviation', '1.5');
  blur.setAttribute('result', 'smooth');

  const map = document.createElementNS(SVG_NS, 'feDisplacementMap');
  map.setAttribute('in', 'SourceGraphic');
  map.setAttribute('in2', 'smooth');
  map.setAttribute('xChannelSelector', 'R');
  map.setAttribute('yChannelSelector', 'G');

  filter.append(image, blur, map);
  ensureDefs().append(filter);
  return { filter, image, map };
}

/**
 * Turns on edge refraction for a top-level glass element (nested glass would only
 * refract its parent's tint, so it isn't worth the cost there).
 * Returns a disposer.
 */
export function refract(el: HTMLElement, opts: RefractOptions = {}): () => void {
  if (!refractionSupported) return () => {};
  const id = `lg-refract-${++counter}`;
  const { filter, image, map } = createFilter(id);
  const bezel = opts.bezel ?? 22;
  const scale = opts.scale ?? 36;
  const blur = opts.blur ?? 18;
  const saturate = opts.saturate ?? 185;
  let lastKey = '';
  let frame = 0;

  const update = (): void => {
    frame = 0;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    if (!w || !h) return;
    const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
    const key = `${w}x${h}r${radius}`;
    if (key === lastKey) return;
    lastKey = key;
    filter.setAttribute('width', String(w));
    filter.setAttribute('height', String(h));
    image.setAttribute('width', String(w));
    image.setAttribute('height', String(h));
    image.setAttribute('href', displacementMap(w, h, radius, Math.min(bezel, w / 3, h / 3)));
    map.setAttribute('scale', String(scale));
    el.style.setProperty('--refract-filter', `url(#${id}) blur(${blur}px) saturate(${saturate}%)`);
    el.classList.add('is-refracting');
  };

  const ro = new ResizeObserver(() => {
    if (!frame) frame = requestAnimationFrame(update);
  });
  ro.observe(el);
  update();

  return () => {
    ro.disconnect();
    cancelAnimationFrame(frame);
    filter.remove();
    el.classList.remove('is-refracting');
    el.style.removeProperty('--refract-filter');
  };
}

export function markRefractionSupport(): void {
  document.documentElement.classList.toggle('has-refraction', refractionSupported);
}
