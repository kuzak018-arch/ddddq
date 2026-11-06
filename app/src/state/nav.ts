/** Where the profile is open (its tab and the match in «Кто заруинил»): not saved, but shared, so
 * the app can open a breakdown by itself after a match (lib/afterMatch.ts). */
import { create } from 'zustand';

export type ProfileTab = 'stats' | 'history' | 'matches' | 'ruin' | 'pool' | 'search';

interface NavState {
  profileTab: ProfileTab;
  ruinId: number | null;
  /** a player to look up in «Найти игрока» (from the search on Ctrl+K), taken once */
  playerQuery: string | null;
  set: (p: Partial<Omit<NavState, 'set'>>) => void;
}

export const useNav = create<NavState>((set) => ({ profileTab: 'stats', ruinId: null, playerQuery: null, set }));
