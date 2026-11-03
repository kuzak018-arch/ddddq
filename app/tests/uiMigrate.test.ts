import assert from 'node:assert/strict';
import { test } from 'node:test';

import { migrateUi, PRESET_IDS } from '../src/state/uiMigrate.ts';

test('a wallpaper that is no longer offered falls back to the default', () => {
  for (const id of ['default', 'dire', 'radiant', 'aurora', 'sunrise']) {
    const out = migrateUi({ background: { kind: 'preset', id } }, 3) as { background: { id: string } };
    assert.equal(out.background.id, 'slate');   // to night at v4, then to the v5 default
  }
  const live = migrateUi({ background: { kind: 'live', id: 'nebula' } }, 3) as { background: { kind: string; id: string } };
  assert.deepEqual(live.background, { kind: 'preset', id: 'slate' });
});

test('the four offered wallpapers, hero art and own files are kept', () => {
  for (const id of PRESET_IDS) {
    const kept = (migrateUi({ background: { kind: 'preset', id } }, 3) as { background: { id: string } }).background.id;
    assert.equal(kept, id === 'night' ? 'slate' : id);   // night was the default: v5 moves it to the new one
  }
  const hero = { kind: 'hero', key: 'pudge' };
  assert.deepEqual((migrateUi({ background: hero }, 3) as { background: unknown }).background, hero);
  const file = { kind: 'file', name: 'a.png' };
  assert.deepEqual((migrateUi({ background: file }, 3) as { background: unknown }).background, file);
});

test('the profile banner preset follows, and nothing is changed once at version 6', () => {
  const out = migrateUi({ banner: { kind: 'preset', key: 'dire', x: 1 } }, 3) as { banner: { key: string; x: number } };
  assert.equal(out.banner.key, 'night');
  assert.equal(out.banner.x, 1);
  const same = { background: { kind: 'preset', id: 'dire' } };
  assert.deepEqual(migrateUi(same, 6), same);
});

test('older settings still get the refraction switched off', () => {
  assert.equal((migrateUi({ refraction: true }, 2) as { refraction: boolean }).refraction, false);
  assert.equal((migrateUi({ refraction: true }, 3) as { refraction: boolean }).refraction, true);
});

test('version 5: the old default look (glass on «Ночь») becomes «Чёткий» on «Сланец», other choices stay', () => {
  const old = migrateUi({ material: 'glass', background: { kind: 'preset', id: 'night' } }, 4) as { material: string; background: { id: string } };
  assert.equal(old.material, 'glass');   // «Чёткий» at v5, back to glass at v6
  assert.equal(old.background.id, 'slate');
  const chosen = migrateUi({ material: 'matte', background: { kind: 'preset', id: 'graphite' } }, 4) as { material: string; background: { id: string } };
  assert.equal(chosen.material, 'matte');
  assert.equal(chosen.background.id, 'graphite');
  const fromV3 = migrateUi({ background: { kind: 'preset', id: 'aurora' } }, 3) as { background: { id: string } };
  assert.equal(fromV3.background.id, 'slate');
});

test('version 6: «Чёткий» and no choice become liquid glass, «Матовое» and «Акрил» stay', () => {
  assert.equal((migrateUi({ material: 'dota' }, 5) as { material: string }).material, 'glass');
  assert.equal((migrateUi({}, 5) as { material: string }).material, 'glass');
  assert.equal((migrateUi({ material: 'matte' }, 5) as { material: string }).material, 'matte');
  assert.equal((migrateUi({ material: 'acrylic' }, 5) as { material: string }).material, 'acrylic');
  assert.equal((migrateUi({ material: 'dota' }, 6) as { material: string }).material, 'dota');
});
