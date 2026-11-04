/**
 * The draft model in the browser (the demo site): the same numbers and formulas as the app's
 * backend (backend/drafter/model/predictor.py: evaluate, suggest, bans; api/app.py: _term;
 * model/explain.py: term_text), exported by backend/drafter/web_export.py. No personal pool in
 * the demo, so comfort is off.
 */

export interface DemoModel {
  n_ids: number;
  S: number[][];
  C: number[][];
  hero_w: number[];
  hero_group_w: number[][];
  intercept: number;
  cal_a: number;
  cal_b: number;
  pick_rate: number[][];
  lw: number[][];
  pos_mat: number[][];
  positions_source: string;
  names: Record<string, string>;
}

interface Term {
  kind: string;
  heroes: number[];
  value: number;
  note?: string | null;
}

const MAIN_POS_SHARE = 0.4;
const MIN_POS_SHARE = 0.1;
const SPECIALIST_PICK_RATE = 0.03;

export const expit = (z: number) => 1 / (1 + Math.exp(-z));

/** model/draft.py rank_group */
export const rankGroup = (rankTier: number) => {
  const t = Math.floor(rankTier / 10);
  return t <= 3 ? 0 : t <= 5 ? 1 : 2;
};

const pctText = (v: number) => {
  const x = (expit(v) - 0.5) * 100;
  return `${x >= 0 ? '+' : '-'}${Math.abs(x).toFixed(1)}%`;
};

const byAbs = (a: Term, b: Term) => Math.abs(b.value) - Math.abs(a.value);

export class Predictor {
  private m: DemoModel;
  constructor(m: DemoModel) {
    this.m = m;
  }

  name = (h: number) => this.m.names[String(h)] ?? `#${h}`;
  get positionsSource() {
    return this.m.positions_source;
  }

  private strength(h: number, g: number) {
    return (this.m.hero_w[h] ?? 0) + (this.m.hero_group_w[g]?.[h] ?? 0);
  }
  private S = (a: number, b: number) => this.m.S[a]?.[b] ?? 0;
  private C = (a: number, b: number) => this.m.C[a]?.[b] ?? 0;

  private sideTerm(side: string | null | undefined) {
    const s = this.m.cal_a * this.m.intercept + this.m.cal_b;
    return side === 'radiant' ? s : side === 'dire' ? -s : 0;
  }

  text(t: Term): string {
    const n = this.name;
    if (t.kind === 'hero') return `сила ${n(t.heroes[0]!)} в мете ${pctText(t.value)}`;
    if (t.kind === 'synergy') {
      const [a, b] = t.heroes as [number, number];
      return t.value >= 0 ? `синергия ${n(a)} + ${n(b)} ${pctText(t.value)}` : `${n(a)} плохо сочетается с ${n(b)} ${pctText(t.value)}`;
    }
    if (t.kind === 'counter') {
      const [a, b] = t.heroes as [number, number];
      return t.value >= 0 ? `${n(a)} хорош против ${n(b)} ${pctText(t.value)}` : `${n(b)} контрит ${n(a)} ${pctText(t.value)}`;
    }
    if (t.kind === 'risk') {
      const who = t.heroes.map(n).join(', ');
      return `риск контрпика${who ? ` (${who})` : ''} ${pctText(t.value)}`;
    }
    return `${t.kind} ${pctText(t.value)}`;
  }

  /** api/app.py _term */
  out(t: Term) {
    return {
      kind: t.kind,
      heroes: t.heroes,
      value: Math.round(t.value * 1e4) / 1e4,
      pct: Math.round((expit(t.value) - 0.5) * 1e4) / 100,
      text: this.text(t),
      note: t.note ?? null,
    };
  }

  evaluate(allies: number[], enemies: number[], g: number, side?: string | null) {
    const a = this.m.cal_a;
    const terms: Term[] = [];
    for (const h of allies) terms.push({ kind: 'hero', heroes: [h], value: a * this.strength(h, g) });
    for (const h of enemies) terms.push({ kind: 'hero', heroes: [h], value: -a * this.strength(h, g) });
    allies.forEach((x, i) => allies.slice(i + 1).forEach((y) => terms.push({ kind: 'synergy', heroes: [x, y], value: a * this.S(x, y) })));
    enemies.forEach((x, i) => enemies.slice(i + 1).forEach((y) => terms.push({ kind: 'synergy', heroes: [x, y], value: -a * this.S(x, y) })));
    for (const x of allies) for (const y of enemies) terms.push({ kind: 'counter', heroes: [x, y], value: a * this.C(x, y) });
    const z = terms.reduce((s, t) => s + t.value, 0) + this.sideTerm(side);
    return { p_win: expit(z), terms: terms.sort(byAbs) };
  }

  private known(h: number) {
    return String(h) in this.m.names;
  }

  private playable(h: number, pos: number) {
    return (this.m.pos_mat[h]?.[pos - 1] ?? 0) >= MIN_POS_SHARE;
  }

  suggest(allies: number[], enemies: number[], bans: number[], pos: number, g: number, side?: string | null, top = 10, offroleTop = 3) {
    const a = this.m.cal_a;
    const taken = new Set([...allies, ...enemies, ...bans]);
    const base = this.evaluate(allies, enemies, g, side);
    const zNow = Math.log(base.p_win / (1 - base.p_win));
    const n = this.m.n_ids;
    const available = Array.from({ length: n }, (_, h) => this.known(h) && !taken.has(h));
    const enemyLeft = Math.max(0, 5 - enemies.length);
    const pr = this.m.pick_rate[g] ?? [];
    let q = available.map((ok, h) => (ok ? (pr[h] ?? 0) : 0));
    const qs = q.reduce((s, x) => s + x, 0);
    if (qs > 0) q = q.map((x) => x / qs);
    const rows = [];
    for (let h = 0; h < n; h++) {
      if (!available[h] || !this.playable(h, pos)) continue;
      let strength = a * this.strength(h, g);
      const specialist = (pr[h] ?? 0) < SPECIALIST_PICK_RATE && (this.m.lw[g]?.[h] ?? 0) > 0.06;
      if (specialist && strength > 0) strength = 0;
      const terms: Term[] = [{ kind: 'hero', heroes: [h], value: strength }];
      for (const x of allies) terms.push({ kind: 'synergy', heroes: [h, x], value: a * this.S(h, x) });
      for (const e of enemies) terms.push({ kind: 'counter', heroes: [h, e], value: a * this.C(h, e) });
      if (enemyLeft) {
        let qh = q.slice();
        qh[h] = 0;
        const s = qh.reduce((acc, x) => acc + x, 0);
        if (s > 0) qh = qh.map((x) => x / s);
        const threat = qh.map((x, e) => x * this.C(e, h));
        const risk = -a * enemyLeft * threat.reduce((acc, x) => acc + x, 0);
        const by = threat
          .map((t, e) => [e, t] as const)
          .sort((x, y) => y[1] - x[1])
          .slice(0, 3)
          .filter(([, t]) => t > 0)
          .map(([e]) => e);
        terms.push({ kind: 'risk', heroes: by, value: risk });
      }
      const dz = terms.reduce((acc, t) => acc + t.value, 0);
      const pAfter = expit(zNow + dz);
      rows.push({
        hero: h,
        score: dz,
        p_win: pAfter,
        delta: pAfter - base.p_win,
        pos_share: this.m.pos_mat[h]?.[pos - 1] ?? 0,
        meta_wr: expit(this.m.lw[g]?.[h] ?? 0),
        pick_rate: pr[h] ?? 0,
        specialist,
        terms: terms.sort(byAbs),
      });
    }
    rows.sort((x, y) => y.score - x.score);
    return {
      p_win: base.p_win,
      main: rows.filter((r) => r.pos_share >= MAIN_POS_SHARE).slice(0, top),
      offrole: rows.filter((r) => r.pos_share < MAIN_POS_SHARE).slice(0, offroleTop),
    };
  }

  bans(allies: number[], enemies: number[], bans: number[], g: number, top = 5) {
    const a = this.m.cal_a;
    const taken = new Set([...allies, ...enemies, ...bans]);
    const q = this.m.pick_rate[g] ?? [];
    const rows = [];
    for (const key of Object.keys(this.m.names)) {
      const e = Number(key);
      if (taken.has(e)) continue;
      const terms: Term[] = [{ kind: 'hero', heroes: [e], value: a * this.strength(e, g) }];
      for (const x of allies) terms.push({ kind: 'counter', heroes: [e, x], value: a * this.C(e, x) });
      const harm = terms.reduce((acc, t) => acc + t.value, 0);
      rows.push({ hero: e, threat: (q[e] ?? 0) * harm, harm, pick_rate: q[e] ?? 0, against: allies, terms: terms.sort(byAbs) });
    }
    rows.sort((x, y) => y.threat - x.threat);
    return rows.slice(0, top);
  }
}
