import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, backendImage } from './client';
import type {
  BanSuggestion,
  BuildsResponse,
  DraftRequest,
  EvaluateResponse,
  Health,
  Hero,
  HeroPage,
  LaneOffLane,
  LaneOpponentsResponse,
  LaneResponse,
  MeSummary,
  Profile,
  Settings,
  SuggestResponse,
  TierList,
  VsItem,
} from './types';

export function useHeroes() {
  return useQuery({
    queryKey: ['heroes'],
    queryFn: () => api<{ positions_source: string; heroes: Hero[] }>('/heroes'),
    staleTime: Infinity,
    select: (d) => ({ ...d, byId: new Map(d.heroes.map((h) => [h.id, h])) }),
  });
}

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: () => api<Health>('/health'), refetchInterval: 30_000 });
}

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: () => api<Settings>('/settings'), staleTime: Infinity });
}

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (s: Settings) => api<Settings>('/settings', { method: 'PUT', body: s }),
    onSuccess: (s) => {
      qc.setQueryData(['settings'], s);
      qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'settings' && q.queryKey[0] !== 'heroes' });
    },
  });
}

const draftKey = (d: DraftRequest) => [d.allies, d.enemies, d.bans, d.pos, d.side, d.use_comfort, d.comfort_weight];

export function useEvaluate(d: DraftRequest) {
  return useQuery({
    queryKey: ['evaluate', ...draftKey(d)],
    queryFn: () => api<EvaluateResponse>('/draft/evaluate', { body: d }),
    placeholderData: keepPreviousData,
  });
}

export function useSuggest(d: DraftRequest) {
  return useQuery({
    queryKey: ['suggest', ...draftKey(d)],
    queryFn: () => api<SuggestResponse>('/draft/suggest', { body: d }),
    placeholderData: keepPreviousData,
  });
}

export function useBans(d: DraftRequest) {
  return useQuery({
    queryKey: ['bans', ...draftKey(d)],
    queryFn: () => api<{ pos: number; bans: BanSuggestion[] }>('/draft/bans', { body: d }),
    placeholderData: keepPreviousData,
  });
}

export function useTierList(pos: number | null, tiers: number[] | null, days: number | null) {
  const qs = new URLSearchParams();
  if (pos) qs.set('pos', String(pos));
  if (tiers?.length) qs.set('tiers', tiers.join(','));
  if (days) qs.set('days', String(days));
  return useQuery({
    queryKey: ['tierlist', pos, tiers, days],
    queryFn: () => api<TierList>(`/meta/tierlist?${qs}`),
    placeholderData: keepPreviousData,
  });
}

export function useHeroPage(id: number | null) {
  return useQuery({ queryKey: ['hero', id], queryFn: () => api<HeroPage>(`/heroes/${id}`), enabled: !!id });
}

/** Builds for a hero; polls while matches are loading. fallback: a position the hero is barely
 * played on is replaced by its main one (response.requested_pos tells). */
export function useBuild(hero: number | null, pos: number, enemies: number[], fallback = false, mode: 'all' | 'specialists' = 'all') {
  return useQuery({
    queryKey: ['build', hero, pos, enemies, fallback, mode],
    enabled: !!hero,
    retry: false,
    refetchInterval: (q) => (q.state.data?.build.status === 'loading' ? 3000 : false),
    queryFn: async () => {
      if (enemies.length)
        return api<{ build: BuildsResponse; vs: VsItem[] }>(`/builds/${hero}/vs`, { body: { enemies, pos, fallback, mode } });
      return { build: await api<BuildsResponse>(`/builds/${hero}?pos=${pos}&fallback=${fallback}&mode=${mode}`), vs: [] as VsItem[] };
    },
  });
}

export function useProfile() {
  return useQuery({ queryKey: ['me'], queryFn: () => api<Profile>('/me'), retry: false });
}

export function useMeSummary() {
  return useQuery({ queryKey: ['me', 'summary'], queryFn: () => api<MeSummary>('/me/summary'), retry: false });
}

/** The Steam avatar, served by the backend (the window's CSP blocks the Steam CDN). */
export function useAvatar(path: string | null | undefined, version?: number) {
  const q = useQuery({
    queryKey: ['avatar', path, version],
    queryFn: () => backendImage(path!),
    enabled: !!path,
    staleTime: Infinity,
    retry: false,
  });
  return q.data ?? null;
}

/** Lane matchup; the minute-by-minute part loads in the background, so poll while it does. */
export function useLane(hero: number | null, pos: number, enemy: number | null, enemyPos?: number | null) {
  return useQuery({
    queryKey: ['lane', hero, pos, enemy, enemyPos],
    enabled: !!hero && !!enemy && hero !== enemy,
    retry: false,
    placeholderData: keepPreviousData,
    refetchInterval: (q) => (q.state.data?.status === 'loading' ? 3000 : false),
    queryFn: () =>
      api<LaneResponse | LaneOffLane>(`/lane?hero=${hero}&pos=${pos}&enemy=${enemy}${enemyPos ? `&enemy_pos=${enemyPos}` : ''}`),
  });
}

export function useLaneOpponents(pos: number, enemies: number[], hero: number | null) {
  return useQuery({
    queryKey: ['lane-opponents', pos, enemies, hero],
    enabled: enemies.length > 0,
    staleTime: Infinity,
    queryFn: () => api<LaneOpponentsResponse>('/lane/opponents', { body: { pos, enemies, hero } }),
  });
}
