import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

// The window's CSP decides what the app may load from its own backend (http://127.0.0.1:<port>).
// It once allowed fonts only from the app itself: every font preview silently stayed Dota's
// (the browser in development has no CSP, so nothing showed there).
const csp: string = JSON.parse(readFileSync(new URL('../src-tauri/tauri.conf.json', import.meta.url), 'utf8')).app.security.csp;
const directive = (name: string) => (csp.split(';').map((d) => d.trim().split(/\s+/)).find((d) => d[0] === name) ?? []).slice(1);

test('fonts: the catalog from the backend and the user\'s own files (blob:)', () => {
  assert.ok(directive('font-src').includes('http://127.0.0.1:*'));
  assert.ok(directive('font-src').includes('blob:'));
});

test('media: the hero render video from the backend, wallpapers and menu videos as blob:', () => {
  assert.ok(directive('media-src').includes('http://127.0.0.1:*'));
  assert.ok(directive('media-src').includes('blob:'));
});

test('images and requests to the backend', () => {
  assert.ok(directive('img-src').includes('http://127.0.0.1:*'));
  assert.ok(directive('connect-src').includes('http://127.0.0.1:*'));
});
