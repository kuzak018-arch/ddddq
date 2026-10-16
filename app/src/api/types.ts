export interface Hero {
  id: number;
  key: string;
  name: string;
  ru: string[];
  alias: string[];
  attr: 'str' | 'agi' | 'int' | 'all';
  attack: 'Melee' | 'Ranged';
  roles: string[];
  icon: string;
  positions: number[];
  main_pos: number;
}

export interface Term {
  kind: 'hero' | 'synergy' | 'counter' | 'comfort' | 'risk';
  heroes: number[];
  value: number;
  pct: number;
  text: string;
  note: string;
}

export interface Suggestion {
  hero: number;
  score: number;
  p_win: number;
  delta: number;
  pos_share: number;
  meta_wr: number;
  pick_rate: number;
  specialist: boolean;
  terms: Term[];
}

export interface SuggestResponse {
  pos: number;
  rank_tier: number;
  positions_source: string;
  p_win_now: number;
  main: Suggestion[];
  offrole: Suggestion[];
}

export interface EvaluateResponse {
  p_win: number;
  rank_tier: number;
  terms: Term[];
}

export interface BanSuggestion {
  hero: number;
  threat: number;
  harm: number;
  pick_rate: number;
  against: number[];
  terms: Term[];
}

export interface DraftRequest {
  allies: number[];
  enemies: number[];
  bans: number[];
  pos?: number;
  side?: 'radiant' | 'dire' | null;
  use_comfort?: boolean;
  comfort_weight?: number;
}

export interface BuildItem {
  key: string;
  name: string;
  cost: number;
  share: number;
  wr?: number | null;
  minute?: number;
  count?: number;
}

export interface Build {
  hero: number;
  pos: number;
  bracket: string;
  week: number;
  matches: number;
  hero_wr: number | null;
  starting: BuildItem[];
  boots: BuildItem[];
  early: BuildItem[];
  core: BuildItem[];
  situational: BuildItem[];
  skills: { key: string; name: string; max_level: number | null; first_level: number | null }[];
  talents: {
    level: number;
    picks: number;
    enough: boolean;
    options: { key: string; name: string; share: number; wr: number | null }[];
  }[];
  facets: { name: string; title: string | null; description: string | null }[];
}

export interface VsItem {
  item: string;
  name: string;
  cost: number;
  score: number;
  hero_share: number | null;
  in_build: boolean;
  rare_on_hero: boolean;
  icon: string;
  reasons: { tag: string; text: string; score: number }[];
}

export interface TierRow {
  hero: number;
  games: number;
  wr: number;
  pick_rate: number;
  score: number;
  ban_share: number | null;
  pos_share: number;
  pos_wr: number | null;
  pos_games: number | null;
  trend: { day: string; wr: number | null; games: number }[];
  trend_delta: number | null;
  tier: 'S' | 'A' | 'B' | 'C' | 'D';
}

export interface TierList {
  tiers: number[];
  pos: number | null;
  days: number;
  until: string;
  matches: number;
  bracket: string | null;
  heroes: TierRow[];
}

export interface Matchup {
  hero: number;
  delta: number;
  games: number;
}

export interface HeroPage {
  hero: Hero & { facets: { name: string; title: string | null; description: string | null }[] };
  rank_tier: number;
  bracket: string;
  positions: number[];
  meta_wr: number;
  pick_rate: number;
  matchups: { counters: Matchup[]; countered_by: Matchup[]; synergy: Matchup[]; anti_synergy: Matchup[] };
  builds_for_positions: number[];
  me: { games: number; wins: number; edge: number; experience: number } | null;
}

export interface Profile {
  account_id: number;
  name: string | null;
  avatar: string | null;
  rank_tier: number | null;
  fetched: number;
  overall: { games: number; wins: number; wr: number } | null;
  experience: { k: number; A: number; c: number; games: number } | null;
  heroes: { hero: number; games: number; wins: number; edge: number; experience: number }[];
}

export interface Health {
  ok: boolean;
  patch: string | null;
  model_trained: string | null;
  matches: number;
  stratz: boolean;
  account_id: number | null;
}

export interface Settings {
  pos: number;
  use_comfort: boolean;
  comfort_weight: number;
  rank_tier: number | null;
  tier_days: number;
}

export interface Job {
  id: string;
  kind: string;
  status: 'running' | 'done' | 'failed';
  started: number;
  finished: number | null;
  log: string[];
  error: string | null;
}
