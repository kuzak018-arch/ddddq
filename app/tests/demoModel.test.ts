import assert from 'node:assert/strict';
import { test } from 'node:test';

import { Predictor, rankGroup, type DemoModel } from '../src/demo/model.ts';

// three heroes: 1 strong, 2 weak, 3 counters 1; all play every position
const m: DemoModel = {
  n_ids: 4,
  S: [[0, 0, 0, 0], [0, 0, 0.1, 0], [0, 0.1, 0, 0], [0, 0, 0, 0]],
  C: [[0, 0, 0, 0], [0, 0, 0, -0.2], [0, 0, 0, 0], [0, 0.2, 0, 0]],
  hero_w: [0, 0.2, -0.1, 0],
  hero_group_w: [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
  intercept: 0.05,
  cal_a: 1,
  cal_b: 0,
  pick_rate: [[0, 0.3, 0.3, 0.3], [0, 0.3, 0.3, 0.3], [0, 0.3, 0.3, 0.3]],
  lw: [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]],
  pos_mat: [[0, 0, 0, 0, 0], [0.5, 0.5, 0.5, 0.5, 0.5], [0.5, 0.5, 0.5, 0.5, 0.5], [0.5, 0.5, 0.5, 0.5, 0.5]],
  positions_source: 'test',
  names: { '1': 'A', '2': 'B', '3': 'C' },
};

test('the demo model: an empty draft is even, sides mirror, a counter pick lowers the chance', () => {
  const pr = new Predictor(m);
  assert.equal(pr.evaluate([], [], 1).p_win, 0.5);
  const r = pr.evaluate([], [], 1, 'radiant').p_win;
  const d = pr.evaluate([], [], 1, 'dire').p_win;
  assert.ok(Math.abs(r + d - 1) < 1e-12);
  assert.ok(pr.evaluate([1], [3], 1).p_win < pr.evaluate([1], [2], 1).p_win);
  assert.equal(pr.text({ kind: 'counter', heroes: [1, 3], value: -0.2 }), 'C контрит A -5.0%');
  assert.deepEqual([rankGroup(35), rankGroup(54), rankGroup(80)], [0, 1, 2]);
});

test('the demo model weighs the counter-pick risk and never suggests a taken hero', () => {
  const pr = new Predictor(m);
  const s = pr.suggest([], [2], [], 1, 1);
  // A is stronger, but C (still free for the enemy) counters it: C comes first
  assert.equal(s.main[0]!.hero, 3);
  assert.ok(s.main.find((x) => x.hero === 1)!.terms.some((t) => t.kind === 'risk' && t.heroes[0] === 3));
  assert.ok(s.main.every((x) => x.hero !== 2));
  assert.ok(pr.bans([1], [], [], 1).every((x) => x.hero !== 1));
});
