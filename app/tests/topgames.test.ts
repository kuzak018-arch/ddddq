import assert from 'node:assert/strict';
import { test } from 'node:test';

import { clock, coreTimings, filterMatches, summarize, type TopMatch } from '../src/lib/topgames.ts';

const m = (id: number, w: boolean, pos: number, items: [number, string][], enemies = [2]): TopMatch => ({
  m: id, t: 0, dur: 2400, rank: 80, src: 'stratz', acc: 1, name: null, league: null, w, pos, radiant: true,
  k: 1, d: 1, a: 1, lh: 1, dn: 1, gpm: 1, xpm: 1, nw: 1, dmg: 1, final: null, neutral: null, items, skills: [], curve: null, curve_kind: 'networth', allies: [], enemies,
});
const core = new Set(['bfury', 'manta', 'power_treads', 'abyssal_blade']);

test('core timings: first purchase only, in order', () => {
  const x = m(1, true, 1, [[900, 'bfury'], [400, 'power_treads'], [-60, 'tango'], [1500, 'bfury']]);
  assert.deepEqual(coreTimings(x, core), [['power_treads', 400], ['bfury', 900]]);
});

test('summary: winrate, median timings, most frequent builds', () => {
  const list = [
    m(1, true, 1, [[400, 'power_treads'], [900, 'bfury'], [1300, 'manta']]),
    m(2, false, 1, [[500, 'power_treads'], [1100, 'bfury'], [1500, 'manta']]),
    m(3, true, 1, [[450, 'power_treads'], [1000, 'manta'], [1600, 'abyssal_blade']]),
  ];
  const s = summarize(list, core);
  assert.equal(s.count, 3);
  assert.equal(s.wins, 2);
  assert.ok(Math.abs((s.winrate ?? 0) - 2 / 3) < 1e-9);
  const treads = s.items.find((i) => i.key === 'power_treads')!;
  assert.equal(treads.median, 450);
  assert.equal(treads.share, 1);
  assert.deepEqual(s.builds[0], { items: ['power_treads', 'bfury', 'manta'], count: 2, wins: 1 });
  assert.equal(summarize([], core).winrate, null);
});

test('filters: position, wins only, against a hero', () => {
  const list = [m(1, true, 1, [], [5]), m(2, false, 1, [], [6]), m(3, true, 2, [], [5])];
  assert.deepEqual(filterMatches(list, { pos: 1, winsOnly: false, against: null }).map((x) => x.m), [1, 2]);
  assert.deepEqual(filterMatches(list, { pos: null, winsOnly: true, against: 5 }).map((x) => x.m), [1, 3]);
  assert.equal(clock(-89), '-1:29');
  assert.equal(clock(754), '12:34');
});
