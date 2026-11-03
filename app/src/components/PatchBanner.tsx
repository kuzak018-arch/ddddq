/** «Вышел патч 7.42 — данные с 7.41f»: Dota has a newer patch than the app's data (backend
 * patch_watch.py). One button starts the usual refresh job and opens Settings to watch it. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, X } from 'lucide-react';
import { useEffect, useState } from 'react';

import { api, subscribe } from '../api/client';
import { useUi } from '../state/ui';
import { Ti } from './Icons';

interface PatchStatus {
  latest: { name: string; ts: number } | null;
  data_patch: string | null;
  model_patch: string | null;
  behind: boolean;
  model_behind: boolean;
}

export function PatchBanner() {
  const qc = useQueryClient();
  const go = useUi((s) => s.go);
  const [hidden, setHidden] = useState<string | null>(() => {
    try {
      return sessionStorage.getItem('drafter-patch-banner-hidden');
    } catch {
      return null;
    }
  });
  const q = useQuery({ queryKey: ['patch-status'], queryFn: () => api<PatchStatus>('/data/patch-status'), refetchInterval: 30 * 60_000 });
  useEffect(() => subscribe((e) => (e.type === 'patch' || (e.type === 'job' && e.kind === 'refresh' && e.status !== 'running')) && void qc.invalidateQueries({ queryKey: ['patch-status'] })), [qc]);
  const start = useMutation({
    mutationFn: () => api('/data/refresh', { method: 'POST' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      useUi.getState().set({ settingsTab: 'more' });   // the refresh log is in «Данные»
      go('settings');
    },
  });
  const s = q.data;
  if (!s) return null;
  if (s.behind && s.latest && hidden !== s.latest.name)
    return (
      <div className="patch-banner" role="status">
        <span>
          <b>Вышел патч {s.latest.name}</b> — данные программы с {s.data_patch}: мета, билды и подсказки пока по старому патчу.
        </span>
        <button className="btn btn--sm btn--accent" onClick={() => start.mutate()} disabled={start.isPending}>
          <Ti icon={RefreshCw} />
          {start.isPending ? 'Запускаю…' : 'Обновить данные'}
        </button>
        <button
          className="btn btn--sm btn--ghost"
          title="Скрыть до следующего запуска"
          onClick={() => {
            setHidden(s.latest!.name);
            try {
              sessionStorage.setItem('drafter-patch-banner-hidden', s.latest!.name);
            } catch {
              /* ignore */
            }
          }}
        >
          <Ti icon={X} />
        </button>
      </div>
    );
  let modelHidden: string | null = null;
  try {
    modelHidden = localStorage.getItem('drafter-model-note-hidden');
  } catch {
    /* ignore */
  }
  if (s.model_behind && hidden !== `model-${s.data_patch}` && modelHidden !== `model-${s.data_patch}`)
    return (
      <div className="patch-banner is-soft" role="status">
        <span>
          Данные с патча {s.data_patch}, а модель драфта обучена на {s.model_patch}: матчей нового патча пока мало, она переобучится при
          следующем обновлении данных.
        </span>
        <button
          className="btn btn--sm btn--ghost"
          title="Больше не показывать для этого патча"
          onClick={() => {
            setHidden(`model-${s.data_patch}`);
            try {
              localStorage.setItem('drafter-model-note-hidden', `model-${s.data_patch}`);
            } catch {
              /* ignore */
            }
          }}
        >
          <Ti icon={X} />
        </button>
      </div>
    );
  return null;
}
