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

export interface BuildEntry {
  key: string;
  name: string;
  cost: number;
  share: number;
  minute: number | null;
  alternatives?: BuildEntry[];
  games?: number;
  wr?: number | null;
}

/** One whole build: from real purchase sequences, or the aggregated fallback (approximate). */
export interface Build {
  title: string;
  approximate?: boolean;
  games: number;
  wins: number | null;
  wr: number | null;
  reliable: boolean;
  share: number;
  starting: { key: string; name: string; count: number }[];
  starting_share: number | null;
  early: BuildEntry[];
  boots: BuildEntry | null;
  boots_upgrade: BuildEntry | null;
  core: BuildEntry[];
  situational: BuildEntry[];
  skills: { level: number; key: string; name: string; share: number }[];
  skill_order?: { key: string; name: string; max_level: number | null; first_level: number | null }[];
  talents: {
    level: number;
    picks: number;
    enough: boolean;
    options: { key: string; name: string; share: number; wr?: number | null; ability?: string | null }[];
  }[];
}

/** An ability shown in a build: Russian name, short description, cached icon (null: none on the CDN). */
export interface AbilityInfo {
  key: string;
  name: string;
  desc: string;
  innate: boolean;
  icon: string | null;
}

export interface BuildsResponse {
  hero: number;
  abilities?: Record<string, AbilityInfo>;
  pos: number;
  requested_pos: number | null;
  mode: 'all' | 'specialists';
  status: 'loading' | 'ready';
  games: number;
  target: number;
  progress: { have: number; target: number; requests: number; batch?: number };
  error: string | null;
  note?: string | null;
  builds: Build[];
  approximate: Build | null;
  min_games: number;
  reliable_games: number;
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

/** The build of top players on the hero in games against a draft like this one (POST /top-games/vs). */
export interface TopVsItem {
  key: string;
  name: string;
  minute: number | null;
  share: number;
}
export interface TopVs {
  found: boolean;
  reason: 'few_enemies' | 'none' | null;
  loading: boolean;
  error: string | null;
  checked?: number;
  games?: number;
  wins?: number;
  full?: number;
  enemies?: number;
  need?: number;
  sources?: Record<string, number>;
  boots?: TopVsItem | null;
  core?: TopVsItem[];
  matches?: { m: number; win: boolean; overlap: number; label: string; player: string | null; team: string | null; rank: number | null; core: string[] }[];
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
  /** share of all bans in the bracket and the place by bans (1 = banned most); null: not downloaded */
  bans: { share: number; place: number | null; of: number } | null;
  matchups: { counters: Matchup[]; countered_by: Matchup[]; synergy: Matchup[]; anti_synergy: Matchup[] };
  builds_for_positions: number[];
  me: { games: number; wins: number; edge: number; experience: number } | null;
}

/** Points left to the next star and medal (backend data/ranks.py; Valve hides the exact rating). */
export interface RankProgress {
  tier: number;
  name: string;
  mmr: number;
  from_estimate: boolean;
  low: number;
  high: number;
  next_star: { name: string; points: number; games: number } | null;
  next_rank: { name: string; points: number; games: number };
  per_game: number;
}

export interface Profile {
  account_id: number;
  name: string | null;
  avatar: string | null;
  rank_tier: number | null;
  /** place in the leaderboard (Immortal), null when not in it */
  leaderboard?: number | null;
  /** null: no rank, or an Immortal (their rank is a leaderboard place) */
  rank_progress?: RankProgress | null;
  plus?: boolean;
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
  vision_enabled?: boolean;
  vision_collect?: boolean;
  vision_collect_mb?: number;
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

export interface MeSummary {
  form: { match_id: number; hero: number; win: boolean; kills: number | null; deaths: number | null; assists: number | null; duration: number | null; start: number }[];
  positions: { pos: number; games: number; wins: number; wr: number }[];
  positions_estimated?: number;
  positions_games?: number;
  month_heroes: { hero: number; games: number; wins: number; wr: number }[];
  month_games?: number;
}

export interface LaneOutcome {
  bracket: string;
  week: number | null;
  matches: number;
  rated: number;
  win: number;
  draw: number;
  loss: number;
  stomp_win: number;
  stomp_loss: number;
  win_share: number;
  draw_share: number;
  loss_share: number;
  edge: number;
  enough: boolean;
  reliable: boolean;
  min_verdict: number;
}

export interface LanePoint {
  minute: number;
  n: number;
  nw: number;
  nw_lo: number;
  nw_hi: number;
  xp: number;
  xp_lo: number;
  xp_hi: number;
  ahead: number;
  avg_nw: number;
}

export interface LaneWindow {
  metric: 'nw' | 'xp';
  from: number;
  to: number;
  leader: 'hero' | 'enemy';
  per_min: number;
  z: number;
  sure: boolean;
  n: number;
  spike?: string;
}

export interface LaneEvent {
  side: 'hero' | 'enemy';
  hero: number;
  key: string;
  kind: 'level' | 'item';
  name: string;
  minute: number;
  share: number;
  cost?: number;
  spike: boolean;
  window: LaneWindow | null;
}

export interface LaneResponse {
  hero: number;
  pos: number;
  requested_pos: number | null;
  enemy: number;
  enemy_pos: number;
  off_lane: false;
  rare: boolean;
  target: number;
  outcome: LaneOutcome | null;
  outcome_error: string | null;
  status: 'loading' | 'ready';
  games: number;
  progress: { have: number; target: number; requests: number; batch?: number };
  error: string | null;
  note: string | null;
  analysis: {
    games: number;
    reliable: boolean;
    min_games: number;
    wins: number;
    curves?: LanePoint[];
    windows?: LaneWindow[];
    events?: LaneEvent[];
    phases?: { from: number; to: number; leader: 'hero' | 'enemy' | null; peak: number }[];
    at?: { minute: number; nw: number; xp: number; ahead: number } | null;
  };
}

export interface LaneOpponent {
  hero: number;
  /** likely position in this draft */
  pos: number;
  on_lane: boolean;
  /** where it would stand if it came to my lane; null = never plays there */
  lane_pos: number | null;
  main: boolean;
}

export interface LaneOpponentsResponse {
  pos: number;
  requested_pos: number | null;
  opponents: LaneOpponent[];
}

export interface LaneOffLane {
  hero: number;
  pos: number;
  requested_pos: number | null;
  enemy: number;
  enemy_pos: null;
  off_lane: true;
  status: 'ready';
}
