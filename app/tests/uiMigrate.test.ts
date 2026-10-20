import assert from 'node:assert/strict';
import { test } from 'node:test';

import { migrateUi, PRESET_IDS } from '../src/state/uiMigrate.ts';

test('a wallpaper that is no longer offered falls back to the default', () => {
  for (const id of ['default', 'dire', 'radiant', 'aurora', 'sunrise']) {
    const out = migrateUi({ background: { kind: 'preset', id } }, 3) as { background: { id: string } };
    assert.equal(out.background.id, 'night');
  }
  const live = migrateUi({ background: { kind: 'live', id: 'nebula' } }, 3) as { background: { kind: string; id: string } };
  assert.deepEqual(live.background, { kind: 'preset', id: 'night' });
});

test('the four offered wallpapers, hero art and own files are kept', () => {
  for (const id of PRESET_IDS) assert.equal((migrateUi({ background: { kind: 'preset', id } }, 3) as { background: { id: string } }).background.id, id);
  const hero = { kind: 'hero', key: 'pudge' };
  assert.deepEqual((migrateUi({ background: hero }, 3) as { background: unknown }).background, hero);
  const file = { kind: 'file', name: 'a.png' };
  assert.deepEqual((migrateUi({ background: file }, 3) as { background: unknown }).background, file);
});

test('the profile banner preset follows, and nothing is changed once at version 4', () => {
  const out = migrateUi({ banner: { kind: 'preset', key: 'dire', x: 1 } }, 3) as { banner: { key: string; x: number } };
  assert.equal(out.banner.key, 'night');
  assert.equal(out.banner.x, 1);
  const same = { background: { kind: 'preset', id: 'dire' } };
  assert.deepEqual(migrateUi(same, 4), same);
});

test('older settings still get the refraction switched off', () => {
  assert.equal((migrateUi({ refraction: true }, 2) as { refraction: boolean }).refraction, false);
  assert.equal((migrateUi({ refraction: true }, 3) as { refraction: boolean }).refraction, true);
});
