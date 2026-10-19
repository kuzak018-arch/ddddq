/**
 * Settings card: write hero grids (roles, meta tiers, my pool, counters) into Dota's own grid file.
 * The backend does the safe part (backup, merge of our own grids only, refusing while Dota runs);
 * this card shows what would be written and what the file holds now.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '../api/client';
import { Panel } from './Glass';
import { ErrorBox, HeroIcon, Loading, plural, Toggle } from './ui';

type GridId = 'roles' | 'meta' | 'pool' | 'counters';

interface GridPreview {
  id: GridId;
  name: string;
  description: string;
  config_name: string;
  categories: { name: string; heroes: number[] }[];
  heroes: number;
}

interface GridsResponse {
  rank_tier: number;
  bracket: string | null;
  days: number;
  prefix: string;
  grids: GridPreview[];
}

interface GridState {
  account_id: number | null;
  dota_running: boolean | null;
  check_error: string | null;
  path: string | null;
  found: boolean;
  exists: boolean;
  ours: string[];
  others: number;
  backups: { name: string; time: number; size: number }[];
  backup_dir: string;
  error: string | null;
}

const when = (ts: number) =>
  new Date(ts * 1000).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });

export function HeroGridCard() {
  const qc = useQueryClient();
  const preview = useQuery({ queryKey: ['hero-grids'], queryFn: () => api<GridsResponse>('/hero-grids'), staleTime: 120_000, retry: false });
  // polled: closing Dota should unlock the button without a click
  const state = useQuery({ queryKey: ['hero-grids-state'], queryFn: () => api<GridState>('/hero-grids/state'), refetchInterval: 3000, retry: false });
  const [picked, setPicked] = useState<Set<GridId>>(new Set(['roles', 'meta', 'pool', 'counters']));
  const [open, setOpen] = useState<GridId | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ['hero-grids-state'] });

  const write = useMutation({
    mutationFn: () => api<{ written: string[]; backup: string | null }>('/hero-grids/write', { body: { grids: [...picked] } }),
    onSuccess: (r) => {
      setNote(`Записано: ${r.written.map((n) => n.replace(/^.*· /, '')).join(', ')}.${r.backup ? ` Копия файла: ${r.backup}.` : ''} Запускай Доту.`);
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => api<{ removed: string[] }>('/hero-grids/remove', { method: 'POST' }),
    onSuccess: (r) => {
      setNote(r.removed.length ? `Убрано сеток: ${r.removed.length}. Твои сетки на месте.` : 'Наших сеток в файле нет.');
      refresh();
    },
  });
  const restore = useMutation({
    mutationFn: (name: string) => api<{ restored: string }>('/hero-grids/restore', { body: { name } }),
    onSuccess: (r) => {
      setNote(`Файл возвращён из копии ${r.restored}.`);
      refresh();
    },
  });

  const s = state.data;
  const running = s?.dota_running === true;
  const busy = write.isPending || remove.isPending || restore.isPending;
  const canWrite = !!s?.found && !s.error && !running && s.dota_running !== null && picked.size > 0 && !busy;
  const toggle = (id: GridId) =>
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const err = write.error ?? remove.error ?? restore.error;

  return (
    <Panel>
      <div className="panel__head">
        <h2>Сетки героев</h2>
        <span className={`pill ${running ? 'warn' : ''}`}>{s ? (running ? 'Дота запущена' : s.dota_running === false ? 'Дота закрыта' : 'не проверено') : '…'}</span>
      </div>
      <p className="hint">
        Приложение собирает сетки из своих данных и записывает их в файл сеток Доты, чтобы они появились в выборе героев. Твои сетки
        не трогаются: заменяются только те, что начинаются с «{preview.data?.prefix ?? 'Драфтер · '}». Перед каждой записью файл
        копируется. Писать можно только при закрытой Доте: она перезаписывает файл при выходе.
      </p>

      {preview.isPending && <Loading>Собираю сетки…</Loading>}
      {preview.error && <ErrorBox error={preview.error} />}
      {preview.data && (
        <>
          <p className="muted small">
            Ранг {preview.data.bracket?.replace('_', '–').toLowerCase().replace(/(^|–)\w/g, (m) => m.toUpperCase()) ?? 'твой'}, тир-лист за {preview.data.days}{' '}
            {plural(preview.data.days, 'день', 'дня', 'дней')}.
          </p>
          <ul className="grids">
            {preview.data.grids.map((g) => (
              <li key={g.id} className={`grids__item ${open === g.id ? 'is-open' : ''}`}>
                <div className="grids__row">
                  <Toggle on={picked.has(g.id) && g.heroes > 0} onChange={() => g.heroes > 0 && toggle(g.id)} label={<b>{g.name}</b>} />
                  <span className="muted small">
                    {g.heroes > 0 ? `${g.categories.length} ${plural(g.categories.length, 'категория', 'категории', 'категорий')}, ${g.heroes} ${plural(g.heroes, 'герой', 'героя', 'героев')}` : 'пусто'}
                  </span>
                  {g.heroes > 0 && (
                    <button className="btn btn--sm btn--ghost" onClick={() => setOpen(open === g.id ? null : g.id)} aria-expanded={open === g.id}>
                      {open === g.id ? 'Скрыть' : 'Что внутри'}
                    </button>
                  )}
                </div>
                <p className="hint">{g.description}</p>
                {open === g.id && (
                  <div className="grids__cats">
                    {g.categories.map((c) => (
                      <div key={c.name} className="grids__cat">
                        <span className="grids__catname">{c.name}</span>
                        <div className="grids__heroes">
                          {c.heroes.map((h) => (
                            <HeroIcon key={h} id={h} size="sm" />
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {s && !s.found && <p className="warn small">Не нашёл папку сеток Доты в Steam: укажи Steam ID в «Настройки → Аккаунт» и проверь, что Steam установлен.</p>}
      {s?.error && <ErrorBox error={s.error} />}
      {s?.check_error && <ErrorBox error={s.check_error} />}
      {running && <p className="warn small">Закрой Доту полностью (в том числе из трея Steam), и кнопка станет доступна.</p>}
      {err && <ErrorBox error={err} />}
      {note && !err && <p className="small c-good">{note}</p>}

      <div className="row">
        <button className="btn btn--accent" onClick={() => { setNote(null); write.mutate(); }} disabled={!canWrite} title={running ? 'Сначала закрой Доту' : undefined}>
          {write.isPending ? 'Записываю…' : 'Записать в Доту'}
        </button>
        <button className="btn" onClick={() => { setNote(null); remove.mutate(); }} disabled={!s?.ours.length || running || busy} title="Убрать наши сетки, твои остаются">
          Убрать наши сетки
        </button>
      </div>

      {s?.found && (
        <p className="muted small">
          В файле сейчас: твоих сеток {s.others}, наших {s.ours.length}.{' '}
          <span title={s.path ?? undefined}>Файл: …\userdata\{s.account_id}\570\remote\cfg\hero_grid_config.json</span>
        </p>
      )}

      {!!s?.backups.length && (
        <details className="grids__backups">
          <summary>Копии файла ({s.backups.length})</summary>
          <p className="hint">Хранятся последние 20 в {s.backup_dir}. Восстановление тоже требует закрытой Доты; текущий файл перед этим копируется.</p>
          <ul>
            {s.backups.slice(0, 8).map((b) => (
              <li key={b.name}>
                <span>{when(b.time)}</span>
                <span className="muted small">{Math.round(b.size / 1024)} КБ</span>
                <button className="btn btn--sm" onClick={() => { setNote(null); restore.mutate(b.name); }} disabled={running || busy}>
                  Восстановить
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Panel>
  );
}
