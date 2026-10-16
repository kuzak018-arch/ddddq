import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from './client';
import type {
  BanSuggestion,
  Build,
  DraftRequest,
  EvaluateResponse,
  Health,
  Hero,
  HeroPage,
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

/** fallback: if the hero is barely played on `pos`, use its most played position (build.requested_pos is set). */
export function useBuild(hero: number | null, pos: number, enemies: number[], fallback = false) {
  return useQuery({
    queryKey: ['build', hero, pos, enemies, fallback],
    enabled: !!hero,
    retry: false,
    queryFn: async () => {
      if (enemies.length)
        return api<{ build: Build; vs: VsItem[] }>(`/builds/${hero}/vs`, { body: { enemies, pos, fallback } });
      return { build: await api<Build>(`/builds/${hero}?pos=${pos}&fallback=${fallback}`), vs: [] as VsItem[] };
    },
  });
}

export function useProfile() {
  return useQuery({ queryKey: ['me'], queryFn: () => api<Profile>('/me'), retry: false });
}
