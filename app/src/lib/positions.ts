/**
 * Which position each hero of a team most likely plays: the assignment of the picked heroes to
 * distinct positions 1–5 that is most likely by how often each hero plays each position. Empty
 * slots get the positions left over, in order (mine first for my team: that is the pick I make).
 */

type Shares = (hero: number) => number[] | undefined;

function permutations<T>(xs: T[], k: number): T[][] {
  if (k === 0) return [[]];
  const out: T[][] = [];
  xs.forEach((x, i) => {
    for (const rest of permutations([...xs.slice(0, i), ...xs.slice(i + 1)], k - 1)) out.push([x, ...rest]);
  });
  return out;
}

/**
 * Positions for the five slots of a team (null slots get the leftovers).
 * `fixed`: a hero whose position is known (my own hero at my position).
 */
export function assignPositions(
  slots: (number | null)[],
  shares: Shares,
  opts: { mine?: number; fixed?: { hero: number; pos: number } | null } = {},
): number[] {
  const out = new Array<number>(slots.length).fill(0);
  const picked = slots.map((h, i) => ({ h, i })).filter((x): x is { h: number; i: number } => x.h !== null);
  let free = [1, 2, 3, 4, 5];
  const fixed = opts.fixed && picked.find((x) => x.h === opts.fixed!.hero);
  if (fixed) {
    out[fixed.i] = opts.fixed!.pos;
    free = free.filter((p) => p !== opts.fixed!.pos);
  }
  const rest = picked.filter((x) => x !== fixed);
  const score = (h: number, p: number) => Math.log((shares(h)?.[p - 1] ?? 0.2) + 1e-3);
  let best: number[] = [];
  let bestScore = -Infinity;
  for (const perm of permutations(free, Math.min(rest.length, free.length))) {
    const s = perm.reduce((acc, p, j) => acc + score(rest[j]!.h, p), 0);
    if (s > bestScore) {
      bestScore = s;
      best = perm;
    }
  }
  rest.forEach((x, j) => {
    out[x.i] = best[j] ?? 0;
  });
  const used = new Set(out.filter(Boolean));
  const left = free.filter((p) => !used.has(p)).sort((a, b) => (a === opts.mine ? -1 : b === opts.mine ? 1 : a - b));
  slots.forEach((h, i) => {
    if (h === null) out[i] = left.shift() ?? 0;
  });
  return out;
}
