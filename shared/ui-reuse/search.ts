/**
 * Search helpers: case/ё-insensitive substring match over English names, Russian
 * names and aliases, plus keyboard layout auto-fix (`згвпу` → `pudge`, `,r,` → `бкб`).
 */
const EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`";
const RU = 'йцукенгшщзхъфывапролджэячсмитьбюё';

const EN_TO_RU = new Map([...EN].map((c, i) => [c, RU[i]!]));
const RU_TO_EN = new Map([...RU].map((c, i) => [c, EN[i]!]));

export function normalize(s: string): string {
  return s
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/[^a-z0-9а-я]+/g, '');
}

function switchLayout(s: string): string {
  return [...s.toLowerCase()].map((c) => EN_TO_RU.get(c) ?? RU_TO_EN.get(c) ?? c).join('');
}

export interface Query {
  /** What the user most likely meant. */
  primary: string;
  /** Same keys in the other keyboard layout — used only if `primary` finds nothing. */
  alternate?: string;
}

export function parseQuery(input: string): Query | null {
  const typed = normalize(input);
  const switched = normalize(switchLayout(input));
  if (!typed && !switched) return null;
  // `,r,` loses its commas when normalized — the other layout ("бкб") is what was meant
  if (switched.length > typed.length) return { primary: switched };
  return switched && switched !== typed ? { primary: typed, alternate: switched } : { primary: typed };
}

export function buildHaystack(parts: string[]): string[] {
  return [...new Set(parts.map(normalize).filter(Boolean))];
}

export function matches(haystack: string[], term: string): boolean {
  return haystack.some((h) => h.includes(term));
}
