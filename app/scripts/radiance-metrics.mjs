/**
 * Glyph advances and kerning of Radiance SemiBold, the font Dota draws category names with, for
 * the grid editor (src/lib/grid/radiance.json). Only the numbers are kept: the font is Valve's and
 * is not shipped. Run once when the table needs remaking:
 *
 *   node scripts/radiance-metrics.mjs path/to/radiance-semibold.otf
 *
 * (the font is game/dota/panorama/fonts/radiance-semibold.otf in a Dota install; the table in the repo
 * was made from the copy in GridStudio's assets/fonts, see THIRD_PARTY_NOTICES.md). Needs Playwright.
 * Widths are measured with a canvas at 64× the label size, so hinting cannot round them, and are
 * given in grid units at the label size Dota uses (15.15).
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { chromium } from 'playwright';

const SIZE = 15.15;
const SCALE = 64;
const font = process.argv[2];
if (!font) throw new Error('path to radiance-semibold.otf expected');

// Radiance's own characters (its cmap, as listed in GridStudio's scripts/dota-rendering.mjs `RADIANCE`,
// https://github.com/linsisss/dota2-grid-toolkit, GPL-3.0-only), capitals only: the game draws names in capitals.
const RANGES = [
  [0x20, 0x5f], [0x7b, 0x7e], [0xa1, 0xa7], [0xa9, 0xac], [0xae, 0xb7], [0xb9, 0xbf], [0xd7, 0xd7], [0xf7, 0xf7],
  [0x401, 0x40c], [0x40e, 0x42f], [0x2013, 0x2015], [0x2018, 0x201a], [0x201c, 0x201e], [0x2020, 0x2022], [0x2026, 0x2026],
  [0x2030, 0x2030], [0x2039, 0x203a], [0x20ac, 0x20ac], [0x2116, 0x2116], [0x2122, 0x2122], [0x2202, 0x2202], [0x2206, 0x2206],
  [0x220f, 0x220f], [0x2211, 0x2212], [0x221a, 0x221a], [0x221e, 0x221e], [0x222b, 0x222b], [0x2248, 0x2248], [0x2260, 0x2260],
  [0x2264, 0x2265], [0x25ca, 0x25ca],
];
const chars = RANGES.flatMap(([a, b]) => Array.from({ length: b - a + 1 }, (_, i) => String.fromCodePoint(a + i)));

const browser = await chromium.launch();
const page = await browser.newPage();
const data = readFileSync(font).toString('base64');
const out = await page.evaluate(
  async ({ data, chars, SIZE, SCALE }) => {
    const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
    const face = new FontFace('R', bytes, { weight: '600' });
    await face.load();
    document.fonts.add(face);
    const ctx = document.createElement('canvas').getContext('2d');
    ctx.font = `600 ${SIZE * SCALE}px R`;
    const w = (s) => ctx.measureText(s).width / SCALE;
    const adv = {};
    for (const c of chars) adv[c] = +w(c).toFixed(4);
    const kern = {};
    for (const a of chars)
      for (const b of chars) {
        const k = w(a + b) - w(a) - w(b);
        if (Math.abs(k) >= 0.01) kern[a + b] = +k.toFixed(3);
      }
    return { adv, kern };
  },
  { data, chars, SIZE, SCALE },
);
await browser.close();
writeFileSync(
  new URL('../src/lib/grid/radiance.json', import.meta.url),
  JSON.stringify({ font: 'Radiance SemiBold', size: SIZE, ...out }),
);
console.log(`${Object.keys(out.adv).length} glyphs, ${Object.keys(out.kern).length} kerning pairs`);
