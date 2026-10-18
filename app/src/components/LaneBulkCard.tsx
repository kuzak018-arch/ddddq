/** Settings card: download lane data for many pairs in the background (pool heroes first). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../api/client';
import { useHeroes } from '../api/hooks';
import { Panel } from './Glass';
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
  target: number;
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
    <Panel>
      <h2>Данные линий</h2>
      <p className="hint">
        Кто выигрывает линию, Stratz отдаёт сразу. Графики по минутам строятся по матчам пары (по запросу на матч), поэтому их
        лучше скачать заранее: сначала герои твоего пула против их частых соперников, потом самые частые пары коров (мид против
        мида, керри против оффлейнера). Идёт в фоне, оставляет запас запросов для остального; всё скачивание займёт несколько
        дней работы приложения. Если закрыть приложение или выключить ПК, после следующего запуска скачивание продолжится само с
        того же места. Редкие пары не качаются: для них данных нет.
      </p>
      <div className="row">
        <button className="btn btn--accent" onClick={() => act.mutate('start')} disabled={active || act.isPending}>
          {active ? 'Скачиваю…' : 'Скачать данные линий'}
        </button>
        <button className="btn" onClick={() => act.mutate('stop')} disabled={!(active || s?.wanted) || act.isPending}>
          Остановить
        </button>
      </div>
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
                Пар: {s.done} из {s.total} ({pct}%), из них {s.pool_total} — твой пул.
                {s.skipped ? ` Уже были: ${s.skipped}.` : ''}
              </p>
            </>
          ) : null}
          {s.current && active && (
            <p className="muted small">
              Сейчас: {name(s.current.a)} ({s.current.pa}) против {name(s.current.b)} ({s.current.pb}) — {s.have ?? 0} из {s.target} матчей
              {s.current.why === 'pool' ? ', твой пул' : ''}.
            </p>
          )}
          {s.status === 'waiting' && s.resume_at && (
            <p className="muted small">
              Лимит запросов на этот час почти исчерпан, продолжу в {new Date(s.resume_at * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}.
            </p>
          )}
          {s.status === 'done' && <p className="small c-good">Готово: все запланированные пары скачаны.</p>}
          {s.status === 'stopped' && <p className="muted small">Остановлено. Продолжу с того же места, когда нажмёшь снова.</p>}
          {s.limits?.hour !== undefined && (
            <p className="muted small">
              Осталось запросов Stratz: {s.limits.hour} на час, {s.limits.day} на сутки.
            </p>
          )}
        </div>
      )}
    </Panel>
  );
}
