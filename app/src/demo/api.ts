/**
 * The backend of the demo site (VITE_DEMO=1, GitHub Pages): the draft is computed in the browser by
 * the same model (demo/model.ts); meta, heroes, abilities, builds and neutral items are the app's
 * own answers exported from the seed data (backend/drafter/web_export.py → <site>/demo/*.json);
 * settings and the draft board live in the browser's storage. Everything that needs the user's PC
 * (Dota, the screen, the account, Stratz) answers that it is in the app only.
 */
import { Predictor, rankGroup, type DemoModel } from './model';

export const DEMO = import.meta.env.VITE_DEMO === '1';
/** The site's folder (GitHub Pages serves it under /<repo>/). */
export const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');
export const DOWNLOAD_URL = 'https://github.com/kuzak018-arch/ddddq/releases/latest';
/** The pages of the demo (the others need the PC: Dota, the account, Stratz). */
export const DEMO_PAGES: string[] = ['draft', 'meta', 'hero', 'builds'];

export class DemoError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const ONLY_APP = 'В демо этого нет: работает в программе на ПК (нужны Дота, твой аккаунт или Stratz).';

const files = new Map<string, Promise<unknown>>();
function file<T>(name: string): Promise<T> {
  let p = files.get(name);
  if (!p) {
    p = fetch(`${BASE}/demo/${name}`).then((r) => {
      if (!r.ok) throw new DemoError(404, ONLY_APP);
      return r.json();
    });
    p.catch(() => files.delete(name));
    files.set(name, p);
  }
  return p as Promise<T>;
}

/** One hero's answer from a pack (`pack/<name>.json` = {hero id: answer}, web_export.py). */
async function packed<T>(name: string, hero: string | number): Promise<T> {
  const all = await file<Record<string, T>>(`pack/${name}.json`);
  const v = all[String(hero)];
  if (v === undefined) throw new DemoError(404, `нет героя с id ${hero}`);
  return v;
}

// the hero, item and ability icons as data URIs (icons/<group>.json), loaded before the app starts
const icons = new Map<string, string>();
let iconsLoading: Promise<void> | null = null;
function loadIcons(): Promise<void> {
  return (iconsLoading ??= Promise.all(
    ['heroes', 'items', 'abilities'].map((g) =>
      file<Record<string, string>>(`icons/${g}.json`).then((m) => Object.entries(m).forEach(([k, v]) => icons.set(k, v))),
    ),
  ).then(() => undefined));
}
/** The picture for a backend path ("/icons/items/blink.png"), when the demo has it. */
export const demoAsset = (path: string) => icons.get(path.split('?')[0]!);

let predictor: Promise<Predictor> | null = null;
const model = () => (predictor ??= file<DemoModel>('model.json').then((m) => new Predictor(m)));

// ---- browser storage ----------------------------------------------------------------------

function load<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}
function save(key: string, v: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {
    /* private mode: the value lives until the page closes */
  }
}

type Settings = Record<string, unknown> & { pos?: number; rank_tier?: number | null };
async function settings(): Promise<Settings> {
  const base = await file<Settings>('settings.json');
  return { ...base, ...load<Settings>('drafter-demo-settings', {}) };
}

const EMPTY_SESSION = {
  allies: [null, null, null, null, null],
  enemies: [null, null, null, null, null],
  bans: [],
  side: null,
  pos: null,
  comfort: null,
  my_hero: null,
  phase: 'idle',
  rev: 0,
  source: '',
};

// ---- the draft ---------------------------------------------------------------------------

interface DraftIn {
  allies?: number[];
  enemies?: number[];
  bans?: number[];
  pos?: number | null;
  side?: 'radiant' | 'dire' | null;
  rank_tier?: number | null;
}

async function draft(kind: 'evaluate' | 'suggest' | 'bans', d: DraftIn) {
  const [pr, s] = await Promise.all([model(), settings()]);
  const allies = d.allies ?? [];
  const enemies = d.enemies ?? [];
  const bans = d.bans ?? [];
  const ids = [...allies, ...enemies, ...bans];
  if (new Set(ids).size !== ids.length) throw new DemoError(422, 'один и тот же герой указан дважды');
  const rank = d.rank_tier || s.rank_tier || 50;
  const g = rankGroup(rank);
  const pos = d.pos || s.pos || 1;
  if (kind === 'evaluate') {
    const ev = pr.evaluate(allies, enemies, g, d.side);
    return { p_win: ev.p_win, rank_tier: rank, terms: ev.terms.slice(0, 15).map((t) => pr.out(t)) };
  }
  if (kind === 'suggest') {
    const r = pr.suggest(allies, enemies, bans, pos, g, d.side);
    const row = (x: (typeof r.main)[number]) => ({ ...x, terms: x.terms.slice(0, 6).map((t) => pr.out(t)) });
    return { pos, rank_tier: rank, positions_source: pr.positionsSource, p_win_now: r.p_win, main: r.main.map(row), offrole: r.offrole.map(row) };
  }
  const b = pr.bans(allies, enemies, bans, g);
  return { pos, bans: b.map((x) => ({ ...x, terms: x.terms.slice(0, 4).map((t) => pr.out(t)) })) };
}

// ---- items against the enemies (backend builds/counter.py against + api build_vs) -------------

interface CounterData {
  rules: { tag: string; min: number; weight: 'core' | 'any'; items: Record<string, string[]>; why: string }[];
  tags: Record<string, Record<string, number>>;
  items: Record<string, { dname: string; cost?: number }>;
  rare_on_hero: number;
}
type BuildEntry = { key: string; alternatives?: { key: string }[] };
type Build = { core: BuildEntry[]; early: BuildEntry[]; boots?: BuildEntry | null };

async function buildVs(hero: number, b: { enemies?: number[]; pos?: number }) {
  const [build, c, pr] = await Promise.all([
    packed<{ pos: number; item_share?: Record<string, number>; builds: Build[]; approximate: Build | null }>(`builds_${b.pos || 1}`, hero),
    file<CounterData>('counter.json'),
    file<DemoModel>('model.json'),
  ]);
  const enemies = b.enemies ?? [];
  const pos = String(build.pos);
  const coreShare = (e: number) => (pr.pos_mat[e] ?? []).slice(0, 3).reduce((s, x) => s + x, 0);
  const shares = build.item_share;
  const found = new Map<string, { item: string; name: string; cost?: number; score: number; hero_share: number | null; reasons: { tag: string; text: string; score: number }[] }>();
  for (const rule of c.rules) {
    let total = 0;
    const who: [number, string][] = [];
    for (const e of enemies) {
      const t = c.tags[String(e)]?.[rule.tag] ?? 0;
      if (!t) continue;
      const w = rule.weight === 'core' ? coreShare(e) : 1;
      total += t * w;
      who.push([t * w, pr.names[String(e)] ?? '']);
    }
    if (total < rule.min) continue;
    const heroes = who.sort((x, y) => y[0] - x[0]).map(([, n]) => n).join(', ');
    const urgency = total / rule.min;
    (rule.items[pos] ?? []).forEach((key, rank) => {
      const it = c.items[key];
      if (!it) return;
      let score = urgency / (1 + 0.5 * rank);
      const share = shares ? (shares[key] ?? 0) : null;
      if (share != null && share < c.rare_on_hero && !['dust', 'ward_sentry', 'gem'].includes(key)) score *= 0.25;
      const reason = { tag: rule.tag, text: rule.why.replace('{heroes}', heroes), score: Math.round(score * 100) / 100 };
      const rec = found.get(key);
      if (!rec) found.set(key, { item: key, name: it.dname, cost: it.cost, score, hero_share: share, reasons: [reason] });
      else {
        rec.score += 0.5 * score;
        rec.reasons.push(reason);
      }
    });
  }
  const base = build.builds[0] ?? build.approximate;
  const have = new Set<string>();
  if (base) {
    for (const x of [...base.core, ...base.early]) have.add(x.key);
    for (const x of base.core) for (const a of x.alternatives ?? []) have.add(a.key);
    if (base.boots) have.add(base.boots.key);
  }
  const vs = [...found.values()]
    .sort((x, y) => y.score - x.score)
    .slice(0, 6)
    .map((r) => ({
      ...r,
      score: Math.round(r.score * 100) / 100,
      in_build: have.has(r.item),
      rare_on_hero: r.hero_share != null && r.hero_share < c.rare_on_hero,
      icon: `/icons/items/${r.item}.png`,
    }));
  return { build, vs };
}

// ---- routing --------------------------------------------------------------------------------

export async function demoApi<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const url = new URL(path, 'https://demo.invalid');
  const p = url.pathname;
  const q = url.searchParams;
  const method = init.method ?? (init.body === undefined ? 'GET' : 'POST');
  const body = (init.body ?? {}) as Record<string, unknown>;
  const out = async (): Promise<unknown> => {
    if (p === '/health') {
      await loadIcons();
      return file('health.json');
    }
    if (p === '/heroes') return file('heroes.json');
    if (p === '/settings') {
      if (method === 'GET') return settings();
      const next = { ...(await settings()), ...body };
      save('drafter-demo-settings', next);
      return next;
    }
    if (p === '/session') {
      const cur = load<typeof EMPTY_SESSION>('drafter-demo-session', EMPTY_SESSION);
      if (method === 'GET') return cur;
      const next = { ...cur, ...body, phase: 'idle', rev: cur.rev + 1 };
      save('drafter-demo-session', next);
      return next;
    }
    if (p === '/draft/evaluate') return draft('evaluate', body as DraftIn);
    if (p === '/draft/suggest') return draft('suggest', body as DraftIn);
    if (p === '/draft/bans') return draft('bans', body as DraftIn);
    if (p === '/meta/tierlist') return file(`tierlist/${q.get('pos') || 'all'}.json`);
    let m = p.match(/^\/heroes\/(\d+)$/);
    if (m) return packed('hero', m[1]!);
    if ((m = p.match(/^\/heroes\/(\d+)\/abilities$/))) return packed('abilities', m[1]!);
    if ((m = p.match(/^\/heroes\/(\d+)\/neutrals$/))) return packed('neutrals', m[1]!);
    if ((m = p.match(/^\/builds\/(\d+)$/))) return packed(`builds_${q.get('pos') || 1}`, m[1]!);
    if ((m = p.match(/^\/builds\/(\d+)\/vs$/))) return buildVs(Number(m[1]), body as { enemies?: number[]; pos?: number });
    // the app asks these on its own: quiet empty answers instead of errors
    if (p === '/ui-icons') return { talent: null, innate: null };
    if (p === '/data/patch-status') return { behind: false, model_behind: false };
    if (p === '/jobs') return [];
    throw new DemoError(404, ONLY_APP);
  };
  return (await out()) as T;
}
