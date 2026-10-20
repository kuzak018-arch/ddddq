/**
 * «Игры топов»: the filters and the summary over the loaded matches (pure, see tests).
 */

export interface TopMatch {
  m: number;
  t: number | null;
  dur: number | null;
  rank: number | null;
  src: 'stratz' | 'pro';
  acc: number | null;
  name: string | null;
  team?: string | null;
  league: string | null;
  w: boolean;
  pos: number | null;
  radiant: boolean;
  k: number | null;
  d: number | null;
  a: number | null;
  lh: number | null;
  dn: number | null;
  gpm: number | null;
  xpm: number | null;
  nw: number | null;
  dmg: number | null;
  final: (string | null)[] | null;
  neutral: string | null;
  items: [number, string][];
  skills: string[];
  curve: number[] | null;
  curve_kind: 'networth' | 'gold';
  allies: number[];
  enemies: number[];
}

export interface Filters {
  pos: number | null;
  winsOnly: boolean;
  against: number | null;
}

export function filterMatches(list: TopMatch[], f: Filters): TopMatch[] {
  return list.filter((m) => (f.pos == null || m.pos === f.pos) && (!f.winsOnly || m.w) && (f.against == null || m.enemies.includes(f.against)));
}

/** First time each core item was bought in a match (a second copy is not a new timing). */
export function coreTimings(m: TopMatch, core: Set<string>): [string, number][] {
  const seen = new Set<string>();
  const out: [string, number][] = [];
  for (const [t, k] of [...m.items].sort((a, b) => a[0] - b[0])) {
    if (!core.has(k) || seen.has(k)) continue;
    seen.add(k);
    out.push([k, t]);
  }
  return out;
}

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  const n = s.length;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
};

export interface Summary {
  count: number;
  wins: number;
  winrate: number | null;
  /** Core items by how often they are bought: share of matches and the median minute. */
  items: { key: string; share: number; median: number; count: number }[];
  /** The most frequent first three core items, in order. */
  builds: { items: string[]; count: number; wins: number }[];
  duration: number | null;
}

export function summarize(list: TopMatch[], core: Set<string>, buildSize = 3): Summary {
  const count = list.length;
  const wins = list.filter((m) => m.w).length;
  const times = new Map<string, number[]>();
  const builds = new Map<string, { items: string[]; count: number; wins: number }>();
  for (const m of list) {
    const tl = coreTimings(m, core);
    for (const [k, t] of tl) times.set(k, [...(times.get(k) ?? []), t]);
    if (tl.length >= buildSize) {
      const items = tl.slice(0, buildSize).map(([k]) => k);
      const key = items.join('>');
      const b = builds.get(key) ?? { items, count: 0, wins: 0 };
      b.count++;
      if (m.w) b.wins++;
      builds.set(key, b);
    }
  }
  return {
    count,
    wins,
    winrate: count ? wins / count : null,
    items: [...times.entries()]
      .map(([key, ts]) => ({ key, share: ts.length / Math.max(1, count), median: median(ts), count: ts.length }))
      .sort((a, b) => b.count - a.count || a.median - b.median),
    builds: [...builds.values()].sort((a, b) => b.count - a.count || b.wins - a.wins),
    duration: count ? median(list.map((m) => m.dur ?? 0).filter(Boolean)) : null,
  };
}

/** «12:34» from seconds (negative: bought before the horn). */
export function clock(seconds: number): string {
  const s = Math.round(seconds);
  const sign = s < 0 ? '-' : '';
  const a = Math.abs(s);
  return `${sign}${Math.floor(a / 60)}:${String(a % 60).padStart(2, '0')}`;
}

/** Skills by hero level (1..n): ability keys, talents marked. */
export function skillLevels(skills: string[]): { level: number; key: string; talent: boolean }[] {
  return skills.map((key, i) => ({ level: i + 1, key, talent: key.startsWith('special_bonus') }));
}
