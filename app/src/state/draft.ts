import { create } from 'zustand';

export type Team = 'ally' | 'enemy' | 'ban';
export interface Slot {
  team: Team;
  index: number;
}

export const MAX_BANS = 16;

interface DraftState {
  allies: (number | null)[];
  enemies: (number | null)[];
  bans: number[];
  side: 'radiant' | 'dire' | null;
  /** My position and the comfort toggle; null = take the default from backend settings. */
  pos: number | null;
  comfort: boolean | null;
  /** Set by the backend (GSI, stage 5): match phase and the hero I picked. */
  phase: 'idle' | 'draft' | 'game';
  myHero: number | null;
  setPos: (p: number) => void;
  setComfort: (c: boolean) => void;
  focus: Slot;
  setFocus: (s: Slot) => void;
  /** Put a hero into the focused slot (or the next free slot of the focused team). */
  place: (hero: number) => void;
  /** Place into a specific team's next free slot. */
  placeIn: (team: Team, hero: number) => void;
  clear: (s: Slot) => void;
  reset: () => void;
  setSide: (s: 'radiant' | 'dire' | null) => void;
  setDraft: (allies: number[], enemies: number[], bans?: number[]) => void;
}

const empty = () => [null, null, null, null, null] as (number | null)[];

function without(state: DraftState, hero: number) {
  return {
    allies: state.allies.map((h) => (h === hero ? null : h)),
    enemies: state.enemies.map((h) => (h === hero ? null : h)),
    bans: state.bans.filter((h) => h !== hero),
  };
}

function nextFocus(team: Team, list: (number | null)[], from: number): Slot {
  const free = list.findIndex((h, i) => h === null && i >= from);
  const anyFree = list.findIndex((h) => h === null);
  return { team, index: free >= 0 ? free : anyFree >= 0 ? anyFree : from };
}

export const useDraft = create<DraftState>((set, get) => ({
  allies: empty(),
  enemies: empty(),
  bans: [],
  side: null,
  pos: null,
  comfort: null,
  phase: 'idle',
  myHero: null,
  setPos: (pos) => set({ pos }),
  setComfort: (comfort) => set({ comfort }),
  focus: { team: 'ally', index: 0 },
  setFocus: (focus) => set({ focus }),
  place: (hero) => {
    const { focus } = get();
    if (focus.team === 'ban') return get().placeIn('ban', hero);
    const s = without(get(), hero); // a hero can only be in one slot: moving it frees the old one
    const key = focus.team === 'ally' ? 'allies' : 'enemies';
    const list = [...s[key]];
    list[focus.index] = hero;
    set({ ...s, [key]: list, focus: nextFocus(focus.team, list, focus.index + 1) });
  },
  placeIn: (team, hero) => {
    const s = without(get(), hero);
    if (team === 'ban') {
      if (s.bans.length >= MAX_BANS) return;
      set({ ...s, bans: [...s.bans, hero] });
      return;
    }
    const key = team === 'ally' ? 'allies' : 'enemies';
    const list = [...s[key]];
    const i = list.indexOf(null);
    if (i < 0) return;
    list[i] = hero;
    set({ ...s, [key]: list, focus: nextFocus(team, list, i + 1) });
  },
  clear: ({ team, index }) => {
    if (team === 'ban') return set({ bans: get().bans.filter((_, i) => i !== index) });
    const key = team === 'ally' ? 'allies' : 'enemies';
    const list = [...get()[key]];
    list[index] = null;
    set({ [key]: list, focus: { team, index } } as Partial<DraftState>);
  },
  reset: () => set({ allies: empty(), enemies: empty(), bans: [], focus: { team: 'ally', index: 0 } }),
  setSide: (side) => set({ side }),
  setDraft: (allies, enemies, bans) => {
    const fill = (xs: number[]) => [...xs, ...empty()].slice(0, 5);
    set({ allies: fill(allies), enemies: fill(enemies), bans: bans ?? get().bans });
  },
}));

export const picked = (xs: (number | null)[]) => xs.filter((h): h is number => h !== null);
