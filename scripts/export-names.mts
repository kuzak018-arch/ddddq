// Converts the hand-made RU name/slang dictionaries from dota2-tierlist into JSON
// that both the Python backend and the React app read.
// Usage: node scripts/export-names.mts <path-to-dota2-tierlist>
import { writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const src = resolve(process.argv[2] ?? '../dota2-tierlist');
const load = (p: string) => import(pathToFileURL(join(src, p)).href);

const heroes = await load('scripts/data/hero-names.ts');
const items = await load('scripts/data/item-meta.ts');

writeFileSync('shared/hero_names.json', JSON.stringify(heroes.HERO_NAMES, null, 1) + '\n');
writeFileSync('shared/item_names.json', JSON.stringify(items.ITEM_NAMES, null, 1) + '\n');
console.log(`heroes: ${Object.keys(heroes.HERO_NAMES).length}, items: ${Object.keys(items.ITEM_NAMES).length}`);
