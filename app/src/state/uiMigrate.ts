/** Upgrading saved settings (zustand persist `migrate`), kept apart from the store so a test can run it. */

/** The built-in wallpapers on offer (components/Chrome.tsx PRESETS has the same ids). */
export const PRESET_IDS = ['slate', 'graphite', 'light', 'dark', 'night'] as const;
/** What a wallpaper that is no longer offered falls back to (v4: night, the default then). */
export const DEFAULT_PRESET_ID = 'night';
/** v5: the default look is «Чёткий» on the flat slate wallpaper. */
export const NEW_DEFAULT_PRESET_ID = 'slate';

type Saved = Record<string, unknown> & {
  background?: { kind?: string; id?: string };
  banner?: { kind?: string; key?: string };
};

const known = (id: unknown) => (PRESET_IDS as readonly string[]).includes(String(id));

export function migrateUi(old: unknown, version: number): unknown {
  const s = { ...(old as Saved) };
  // 3: the live refraction is off by default (it re-blurred the wallpaper every frame and flickered)
  if (version < 3) s.refraction = false;
  // 4: only graphite, light, dark and night are offered (the other gradients and the live wallpapers
  // are gone): what was chosen falls back to the default; hero art and own files stay
  if (version < 4) {
    const bg = s.background;
    if (bg && (bg.kind === 'live' || (bg.kind === 'preset' && !known(bg.id)))) {
      s.background = { kind: 'preset', id: DEFAULT_PRESET_ID };
    }
    const banner = s.banner;
    if (banner && banner.kind === 'preset' && !known(banner.key)) s.banner = { ...banner, key: DEFAULT_PRESET_ID };
  }
  // 5: the default look became «Чёткий» (dense panels, sharp corners, no glow) on a flat wallpaper:
  // the old defaults (liquid glass on «Ночь») move to it; any other choice stays
  if (version < 5) {
    if (s.material === undefined || s.material === 'glass') s.material = 'dota';
    const bg = s.background;
    if (bg && bg.kind === 'preset' && bg.id === DEFAULT_PRESET_ID) s.background = { kind: 'preset', id: NEW_DEFAULT_PRESET_ID };
  }
  return s;
}
