import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Page = 'draft' | 'meta' | 'hero' | 'builds' | 'profile' | 'settings' | 'vision';
export type Theme = 'system' | 'light' | 'dark';

/** Background: a built-in gradient, a hero render from the Steam CDN, or the user's own file. */
export type Background =
  | { kind: 'preset'; id: string }
  | { kind: 'hero'; key: string }
  | { kind: 'file'; name: string };

interface UiState {
  page: Page;
  heroPageId: number | null;
  buildHero: number | null;
  buildPos: number;
  theme: Theme;
  background: Background;
  bgBlur: number;      // px applied to the wallpaper itself
  bgDim: number;       // 0..0.8 dark overlay over the wallpaper
  refraction: boolean; // SVG edge refraction (Chromium only)
  performance: boolean; // no blur, no refraction, no animations
  overlay: {
    toggle: string;      // global hotkey: show/hide
    interact: string;    // global hotkey: click-through on/off
    opacity: number;     // 0.35..1 for the whole overlay
    effect: 'acrylic' | 'tint';
    mode: 'auto' | 'draft' | 'build'; // auto: build once the match starts (GSI)
    autoPerf: boolean;   // performance mode in the overlay while a match is running
    autoShow: boolean;   // show the overlay by itself when hero selection starts (GSI)
  };
  go: (page: Page) => void;
  openHero: (id: number) => void;
  openBuild: (hero: number, pos?: number) => void;
  set: (patch: Partial<UiState>) => void;
}

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      page: 'draft',
      heroPageId: null,
      buildHero: null,
      buildPos: 1,
      theme: 'dark',
      background: { kind: 'preset', id: 'dire' },
      bgBlur: 0,
      bgDim: 0.15,
      refraction: true,
      performance: false,
      overlay: { toggle: 'Ctrl+Shift+M', interact: 'Ctrl+Shift+N', opacity: 0.94, effect: 'acrylic', mode: 'auto', autoPerf: true, autoShow: true },
      go: (page) => set({ page }),
      openHero: (id) => set({ page: 'hero', heroPageId: id }),
      openBuild: (hero, pos) => set((s) => ({ page: 'builds', buildHero: hero, buildPos: pos ?? s.buildPos })),
      set: (patch) => set(patch),
    }),
    {
      name: 'drafter-ui',
      version: 2,
      // v1 had no overlay settings: keep everything else, take the defaults for the new block
      migrate: (old) => old as UiState,
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as Partial<UiState>),
        overlay: { ...current.overlay, ...((persisted as Partial<UiState>)?.overlay ?? {}) },
      }),
    },
  ),
);

// Both windows share localStorage: when one changes settings, the other picks them up.
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === 'drafter-ui') void useUi.persist.rehydrate();
  });
}
