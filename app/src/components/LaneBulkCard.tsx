/** Settings card: an option to download lane data for the user's pool in the background. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Route } from 'lucide-react';

import { api } from '../api/client';
import { useHeroes } from '../api/hooks';
import { Ti } from './Icons';
import { Section } from './Section';
import { ErrorBox } from './ui';

interface BulkStatus {
  status?: 'idle' | 'planning' | 'running' | 'waiting' | 'done' | 'stopped' | 'failed';
  total?: number;
  done?: number;
  skipped?: number;
  pool_total?: number;
  index?: number;
  current?: { a: number; pa: number; b: number; pb: number; why: 'pool' | 'all' } | null;
  have?: number;
  requests?: number;
  target: number;
  batch?: { size: number; max_ok: number; refused: number | null };
  resume_at?: number | null;
  error?: string | null;
  /** the user's job is unfinished: it goes on by itself after the app restarts */
  wanted?: boolean;
  resumed?: boolean;
  resume_scheduled?: number;
  limits: { minute?: number; hour?: number; day?: number };
}

const ACTIVE = new Set(['planning', 'running', 'waiting']);

export function LaneBulkCard() {
  const qc = useQueryClient();
  const heroes = useHeroes().data;
  const st = useQuery({
    queryKey: ['lane-bulk'],
    queryFn: () => api<BulkStatus>('/lane/bulk'),
    refetchInterval: (q) => (ACTIVE.has(q.state.data?.status ?? '') || q.state.data?.resume_scheduled ? 3000 : false),
  });
  const act = useMutation({
    mutationFn: (action: 'start' | 'stop') => api<BulkStatus>('/lane/bulk', { body: { action } }),
    onSuccess: (d) => qc.setQueryData(['lane-bulk'], d),
  });
  const s = st.data;
  const active = ACTIVE.has(s?.status ?? '');
  const name = (id: number) => heroes?.byId.get(id)?.name ?? id;
  const pct = s?.total ? Math.round((100 * (s.done ?? 0)) / s.total) : 0;
  return (
    <Section>
      <h2>
        <Ti icon={Route} />
        Данные линий
      </h2>
      <p className="hint">
        Кто выигрывает линию, Stratz отдаёт сразу — одним запросом на героя и позицию. Графики по минутам строятся по {s?.target ?? 25}{' '}
        матчам пары и грузятся сами, когда открываешь пару: несколько матчей в одном запросе, обычно 3–7 запросов на пару, потом —
        мгновенно из кэша.
      </p>
      <p className="hint">
        Необязательно: можно заранее скачать пары твоего пула (твои частые герои против их частых соперников на линии), чтобы и
        первое открытие было мгновенным. Идёт в фоне, оставляет запас запросов для остального, после перезапуска продолжается с
        того же места. По умолчанию выключено.
      </p>
      <div className="row">
        <button className="btn btn--accent" onClick={() => act.mutate('start')} disabled={active || act.isPending}>
          {active ? 'Скачиваю…' : 'Скачать пары моего пула'}
        </button>
        <button className="btn" onClick={() => act.mutate('stop')} disabled={!(active || s?.wanted) || act.isPending}>
          Остановить
        </button>
      </div>
      {s?.batch?.max_ok ? (
        <p className="muted small">
          Stratz отдаёт до {s.batch.size} матчей за запрос{s.batch.refused ? ` (запрос на ${s.batch.refused} он отклонил)` : ''}.
        </p>
      ) : null}
      {act.error && <ErrorBox error={act.error} />}
      {s?.status === 'failed' && s.error && <ErrorBox error={s.error} />}
      {s?.status === 'idle' && s.resume_scheduled && (
        <p className="muted small">
          Скачивание не закончено: продолжу в{' '}
          {new Date(s.resume_scheduled * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}, сначала
          пропущу уже скачанные пары.
        </p>
      )}
      {s && s.status && s.status !== 'idle' && (
        <div className="bulk">
          {s.status === 'planning' && <p className="muted small">Составляю список пар…</p>}
          {s.resumed && active && <p className="muted small">Продолжаю после перезапуска: уже скачанные пары пропускаю.</p>}
          {s.total ? (
            <>
              <div className="lane__progress">
                <i style={{ width: `${pct}%` }} />
              </div>
              <p className="small">
                Пар твоего пула: {s.done} из {s.total} ({pct}%).
                {s.skipped ? ` Уже были: ${s.skipped}.` : ''}
                {s.requests ? ` Запросов Stratz: ${s.requests}.` : ''}
              </p>
            </>
          ) : null}
          {s.current && active && (
            <p className="muted small">
              Сейчас: {name(s.current.a)} ({s.current.pa}) против {name(s.current.b)} ({s.current.pb}) — {s.have ?? 0} из {s.target} матчей.
            </p>
          )}
          {s.status === 'waiting' && s.resume_at && (
            <p className="muted small">
              Лимит запросов на этот час почти исчерпан, продолжу в {new Date(s.resume_at * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}.
            </p>
          )}
          {s.status === 'done' && <p className="small c-good">Готово: все пары пула скачаны.</p>}
          {s.status === 'stopped' && <p className="muted small">Остановлено. Продолжу с того же места, когда нажмёшь снова.</p>}
          {s.limits?.hour !== undefined && (
            <p className="muted small">
              Осталось запросов Stratz: {s.limits.hour} на час, {s.limits.day} на сутки.
            </p>
          )}
        </div>
      )}
    </Section>
  );
}
