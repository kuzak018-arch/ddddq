import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Page = 'draft' | 'meta' | 'hero' | 'builds' | 'profile' | 'settings';
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
      go: (page) => set({ page }),
      openHero: (id) => set({ page: 'hero', heroPageId: id }),
      openBuild: (hero, pos) => set((s) => ({ page: 'builds', buildHero: hero, buildPos: pos ?? s.buildPos })),
      set: (patch) => set(patch),
    }),
    { name: 'drafter-ui', version: 1 },
  ),
);
