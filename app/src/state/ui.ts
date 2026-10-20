import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { Material } from '../lib/glassBackdrop';
import type { PageAnim } from '../lib/pageAnim';

export type Page = 'draft' | 'meta' | 'hero' | 'builds' | 'top' | 'patches' | 'grids' | 'profile' | 'settings' | 'vision';
export type Theme = 'system' | 'light' | 'dark';
export type Effect = 'none' | 'rain' | 'snow' | 'stars' | 'fog' | 'particles';

/** Background: a built-in gradient, a hero render from the Steam CDN, or the user's own file
 * (picture, GIF or video, in IndexedDB). */
export type Background =
  | { kind: 'preset'; id: string }
  | { kind: 'live'; id: string }
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
  /** visible part of a picture, video or hero art (background-position, %) */
  bgPos: { x: number; y: number };
  /** check, download in the background and install on exit (lib/updates.ts) */
  autoUpdate: boolean;
  refraction: boolean; // SVG edge refraction (Chromium only): needs the live blur, see lib/glassBackdrop.ts
  /** what the panels are made of (lib/glassBackdrop.ts) */
  material: Material;
  performance: boolean; // no blur, no refraction, no animations
  /** how one tab turns into another (lib/pageAnim.ts) */
  pageAnim: PageAnim;
  /** cards lean towards the pointer with a glare (lib/tilt.ts) */
  tilt: boolean;
  /** interface sounds (lib/sounds.ts): on/off, volume 0..1, a tick on tab change */
  sounds: { on: boolean; volume: number; tabs: boolean };
  /** closing the main window hides it into the tray instead of quitting */
  closeToTray: boolean;
  /** Background effect over the wallpaper and its intensity (0.1..1). */
  fx: { kind: Effect; intensity: number };
  /** App icon next to the title and in the taskbar: built-in or the user's picture (IndexedDB). */
  logo: { kind: 'default' | 'file'; key?: string };
  /** Profile banner: own file (image or GIF, in IndexedDB), a hero render or a built-in gradient
   * (key = its id); x/y = visible part in %. The rest is the profile's look (ProfilePage). */
  banner: {
    kind: 'none' | 'file' | 'hero' | 'preset';
    key?: string;
    x: number;
    y: number;
    blur: number;
    dim: number;
    /** 'auto' = the banner hero's colour, else a colour */
    accent: string;
    avatar: 'round' | 'squircle' | 'hex';
    status: string;
    /** up to 5 heroes shown in the header */
    showcase: number[];
    /** which tiles the header shows */
    tiles: { games: boolean; winrate: boolean; pos: boolean; month: boolean };
  };
  /** «Оформление игры» (menu background, fonts) is unlocked: off until the user reads the warning. */
  gameMods: boolean;
  /** «Оформление»: which tool is open. */
  lookTab: 'grids' | 'background' | 'font' | 'packs' | 'workshop';
  overlay: {
    toggle: string;      // global hotkey: show/hide
    interact: string;    // global hotkey: click-through on/off
    opacity: number;     // 0.35..1 for the whole overlay
    effect: 'acrylic' | 'tint';
    mode: 'auto' | 'draft' | 'build'; // auto: build once the match starts (GSI)
    autoPerf: boolean;   // performance mode in the overlay while a match is running
    autoShow: boolean;   // show the overlay by itself when hero selection starts (GSI)
    hints: boolean;      // in-game hints in the build mode: next item, timers, buyback (GSI)
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
      background: { kind: 'preset', id: 'default' },
      bgBlur: 0,
      bgDim: 0.15,
      bgPos: { x: 50, y: 30 },
      autoUpdate: true,
      refraction: false,
      material: 'glass',
      performance: false,
      pageAnim: 'rise',
      tilt: true,
      sounds: { on: true, volume: 0.5, tabs: false },
      closeToTray: false,
      logo: { kind: 'default' },
      fx: { kind: 'none', intensity: 0.5 },
      banner: {
        kind: 'none', x: 50, y: 30, blur: 0, dim: 0.35, accent: 'auto', avatar: 'squircle', status: '', showcase: [],
        tiles: { games: true, winrate: true, pos: true, month: true },
      },
      gameMods: false,
      lookTab: 'grids',
      overlay: { toggle: 'Ctrl+Shift+M', interact: 'Ctrl+Shift+N', opacity: 0.94, effect: 'acrylic', mode: 'auto', autoPerf: true, autoShow: true, hints: true },
      go: (page) => set({ page }),
      openHero: (id) => set({ page: 'hero', heroPageId: id }),
      openBuild: (hero, pos) => set((s) => ({ page: 'builds', buildHero: hero, buildPos: pos ?? s.buildPos })),
      set: (patch) => set(patch),
    }),
    {
      name: 'drafter-ui',
      // 3: the live refraction is off by default (it re-blurs the wallpaper every frame and
      // flickered in WebView2); the blurred wallpaper is made once instead (lib/glassBackdrop.ts)
      version: 3,
      // v1 had no overlay settings: keep everything else, take the defaults for the new block
      migrate: (old, version) => (version < 3 ? { ...(old as UiState), refraction: false } : old) as UiState,
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as Partial<UiState>),
        overlay: { ...current.overlay, ...((persisted as Partial<UiState>)?.overlay ?? {}) },
        banner: { ...current.banner, ...((persisted as Partial<UiState>)?.banner ?? {}) },
        fx: { ...current.fx, ...((persisted as Partial<UiState>)?.fx ?? {}) },
        sounds: { ...current.sounds, ...((persisted as Partial<UiState>)?.sounds ?? {}) },
        bgPos: { ...current.bgPos, ...((persisted as Partial<UiState>)?.bgPos ?? {}) },
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
