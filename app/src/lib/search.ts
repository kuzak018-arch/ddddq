/**
 * Hero search over English/Russian names and slang with keyboard-layout auto-fix
 * (`згвпу` → Pudge). Same rules as the backend: exact > prefix > substring.
 */
import type { Hero } from '../api/types';

const EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`";
const RU = 'йцукенгшщзхъфывапролджэячсмитьбюё';
const SWAP = new Map<string, string>([...[...EN].map((c, i) => [c, RU[i]!] as const), ...[...RU].map((c, i) => [c, EN[i]!] as const)]);

export function normalize(s: string): string {
  return s.toLowerCase().replace(/ё/g, 'е').replace(/[^a-z0-9а-я]+/g, '');
}

const switchLayout = (s: string) => [...s.toLowerCase()].map((c) => SWAP.get(c) ?? c).join('');

const haystacks = new WeakMap<Hero, string[]>();
function hay(h: Hero): string[] {
  let v = haystacks.get(h);
  if (!v) {
    v = [...new Set([h.name, h.key.replace(/_/g, ' '), ...h.ru, ...h.alias].map(normalize).filter(Boolean))];
    haystacks.set(h, v);
  }
  return v;
}

function rank(heroes: Hero[], term: string): Hero[] {
  const scored: [number, Hero][] = [];
  for (const h of heroes) {
    let best = 9;
    for (const x of hay(h)) best = Math.min(best, x === term ? 0 : x.startsWith(term) ? 1 : x.includes(term) ? 2 : 9);
    if (best < 9) scored.push([best, h]);
  }
  return scored.sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name)).map(([, h]) => h);
}

export function searchHeroes(heroes: Hero[], query: string, limit = 12): Hero[] {
  const typed = normalize(query);
  const switched = normalize(switchLayout(query));
  if (!typed && !switched) return [];
  // `,r,` loses its commas when normalized: the other layout is what was meant
  const terms = switched.length > typed.length ? [switched] : [typed, switched];
  for (const t of terms) {
    if (!t) continue;
    const res = rank(heroes, t);
    if (res.length) return res.slice(0, limit);
  }
  return [];
}
