/**
 * The editor and Dota's grid file: import (the file in Steam or any file), export to a file, and
 * the write into Dota through the backend's safe path (closed Dota, backup, only our «Драфтер · »
 * grids added or replaced, read back and rolled back on any difference), backups and their restore.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '../../api/client';
import { fromDota, parseFile, toDota, type DotaConfig, type Grid } from '../../lib/grid/doc';
import { addGrids, useGrids } from '../../state/grids';
import { Sheet } from '../Sheet';
import { ErrorBox, plural } from '../ui';

export const PREFIX = 'Драфтер · ';

interface FileState {
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

export function useFileState() {
  // polled: closing Dota should unlock the button without a click
  return useQuery({ queryKey: ['hero-grids-state'], queryFn: () => api<FileState>('/hero-grids/state'), refetchInterval: 3000, retry: false });
}

/** Grids picked from a file (or Dota's own) before they are added to the editor. */
export function ImportSheet({ configs, onClose }: { configs: (DotaConfig & { ours?: boolean })[] | null; onClose: () => void }) {
  const [off, setOff] = useState<Set<number>>(new Set());
  const take = () => {
    const picked = (configs ?? []).filter((_, i) => !off.has(i)).map((c) => fromDota(c, PREFIX));
    if (picked.length) addGrids(picked);
    setOff(new Set());
    onClose();
  };
  return (
    <Sheet open={!!configs} onClose={onClose} title="Импорт сеток">
      {configs && !configs.length && <p className="hint">В файле нет ни одной сетки.</p>}
      <ul className="gimport">
        {configs?.map((c, i) => (
          <li key={i}>
            <label>
              <input type="checkbox" checked={!off.has(i)} onChange={() => setOff((s) => (s.has(i) ? new Set([...s].filter((x) => x !== i)) : new Set([...s, i])))} />
              <b>{c.config_name || 'Без имени'}</b>
              <span className="muted small">
                {c.categories.length} {plural(c.categories.length, 'категория', 'категории', 'категорий')}
                {c.ours ? ' · наша' : ''}
              </span>
            </label>
          </li>
        ))}
      </ul>
      <p className="hint">
        Сетки добавятся в редактор копиями. Записать в Доту можно только наши сетки: твоя сетка «Имя» запишется рядом как «{PREFIX}Имя», а сама
        останется в файле нетронутой.
      </p>
      <div className="row">
        <button className="btn btn--accent" disabled={!configs?.length || off.size === configs.length} onClick={take}>
          Добавить в редактор
        </button>
        <button className="btn btn--ghost" onClick={onClose}>
          Отмена
        </button>
      </div>
    </Sheet>
  );
}

export function GridFileBar() {
  const qc = useQueryClient();
  const grids = useGrids((s) => s.grids);
  const state = useFileState();
  const s = state.data;
  const [importing, setImporting] = useState<(DotaConfig & { ours?: boolean })[] | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ['hero-grids-state'] });
  const game = grids.filter((g) => g.game);
  const configsOf = (list: Grid[]) => list.map((g) => toDota(g));

  const fromDotaFile = useMutation({
    mutationFn: () => api<{ configs: (DotaConfig & { ours: boolean })[] }>('/hero-grids/file'),
    onSuccess: (r) => setImporting(r.configs),
    onError: setErr,
  });
  const write = useMutation({
    mutationFn: () => api<{ written: string[]; backup: string | null }>('/hero-grids/write-configs', { body: { configs: configsOf(game) } }),
    onSuccess: (r) => {
      setConfirm(false);
      setNote(`Записано в Доту: ${r.written.map((n) => n.replace(PREFIX, '')).join(', ')}.${r.backup ? ` Копия прежнего файла: ${r.backup}.` : ''} Запускай Доту.`);
      refresh();
    },
    onError: (e) => {
      setConfirm(false);
      setErr(e);
    },
  });
  const exportFile = useMutation({
    mutationFn: () => api<{ path: string; text: string }>('/hero-grids/export', { body: { configs: configsOf(grids) } }),
    onSuccess: (r) => {
      setNote(`Файл сохранён: ${r.path}`);
      // in the browser it is downloaded as well
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([r.text], { type: 'application/json' }));
      a.download = 'hero_grid_config.json';
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
    },
    onError: setErr,
  });
  const openFolder = useMutation({ mutationFn: () => api('/hero-grids/open-exports', { method: 'POST' }), onError: setErr });
  const remove = useMutation({
    mutationFn: () => api<{ removed: string[] }>('/hero-grids/remove', { method: 'POST' }),
    onSuccess: (r) => {
      setNote(r.removed.length ? `Убрано наших сеток: ${r.removed.length}. Твои на месте.` : 'Наших сеток в файле нет.');
      refresh();
    },
    onError: setErr,
  });
  const restore = useMutation({
    mutationFn: (name: string) => api<{ restored: string }>('/hero-grids/restore', { body: { name } }),
    onSuccess: (r) => {
      setNote(`Файл возвращён из копии ${r.restored}.`);
      refresh();
    },
    onError: setErr,
  });

  const running = s?.dota_running === true;
  const busy = write.isPending || remove.isPending || restore.isPending;
  const canWrite = !!s?.found && !s.error && !running && s.dota_running !== null && game.length > 0 && !busy;
  const dropped = (s?.ours ?? []).filter((n) => !game.some((g) => PREFIX + g.name === n || g.name === n));
  const clear = () => {
    setNote(null);
    setErr(null);
  };

  return (
    <div className="gfile">
      <div className="gfile__row">
        <span className={`pill ${running ? 'warn' : ''}`}>{s ? (running ? 'Дота запущена' : s.dota_running === false ? 'Дота закрыта' : 'не проверено') : '…'}</span>
        <button className="btn btn--sm" onClick={() => (clear(), fromDotaFile.mutate())} disabled={!s?.found || fromDotaFile.isPending}>
          Импорт из Доты
        </button>
        <label className="btn btn--sm">
          Импорт файла…
          <input
            type="file"
            accept=".json,application/json"
            hidden
            onChange={async (e) => {
              const f = e.target.files?.[0];
              e.target.value = '';
              if (!f) return;
              clear();
              try {
                setImporting(parseFile(await f.text()));
              } catch (x) {
                setErr(x instanceof Error ? `Файл не прочитался: ${x.message}` : x);
              }
            }}
          />
        </label>
        <button className="btn btn--sm" onClick={() => (clear(), exportFile.mutate())} disabled={exportFile.isPending} title="Все сетки редактора одним hero_grid_config.json">
          Экспорт в файл
        </button>
        {exportFile.data && (
          <button className="btn btn--sm btn--ghost" onClick={() => openFolder.mutate()}>
            Открыть папку
          </button>
        )}
        <span className="gfile__grow" />
        <button className="btn btn--sm" onClick={() => (clear(), remove.mutate())} disabled={!s?.ours.length || running || busy} title="Убрать наши сетки из Доты, твои остаются">
          Убрать наши из Доты
        </button>
        <button className="btn btn--sm btn--accent" onClick={() => (clear(), setConfirm(true))} disabled={!canWrite} title={running ? 'Сначала закрой Доту' : undefined}>
          {write.isPending ? 'Записываю…' : 'Записать в Доту'}
        </button>
      </div>
      {s && !s.found && <p className="warn small">Не нашёл папку сеток Доты в Steam: укажи Steam ID в «Настройки → Аккаунт» и проверь, что Steam установлен.</p>}
      {running && <p className="warn small">Закрой Доту полностью (в том числе из трея Steam) — запись станет доступна. Иначе Дота перезапишет файл при выходе.</p>}
      {s?.error && <ErrorBox error={s.error} />}
      {s?.check_error && <ErrorBox error={s.check_error} />}
      {!!err && <ErrorBox error={err} />}
      {note && !err && <p className="small c-good">{note}</p>}
      {!!s?.backups.length && (
        <details className="grids__backups">
          <summary>
            Копии файла ({s.backups.length}) · в файле сейчас: твоих сеток {s.others}, наших {s.ours.length}
          </summary>
          <p className="hint">Хранятся последние 20 в {s.backup_dir}. Восстановление тоже требует закрытой Доты; текущий файл перед этим копируется.</p>
          <ul>
            {s.backups.slice(0, 8).map((b) => (
              <li key={b.name}>
                <span>{when(b.time)}</span>
                <span className="muted small">{Math.round(b.size / 1024)} КБ</span>
                <button className="btn btn--sm" onClick={() => (clear(), restore.mutate(b.name))} disabled={running || busy}>
                  Восстановить
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
      <ImportSheet configs={importing} onClose={() => setImporting(null)} />
      <Sheet open={confirm} onClose={() => setConfirm(false)} title="Записать в Доту">
        <p>
          В Доте будут ровно эти наши сетки: <b>{game.map((g) => PREFIX + g.name).join(', ')}</b>.
        </p>
        {!!dropped.length && <p className="warn small">Из файла уйдут наши сетки, которых нет среди отмеченных: {dropped.join(', ')}.</p>}
        <p className="hint">
          Твои сетки (без «{PREFIX}») не трогаются. Перед записью файл копируется, после — проверяется; при любой разнице копия возвращается. Сетка,
          выключенная переключателем «В Доту», не пишется.
        </p>
        <div className="row">
          <button className="btn btn--accent" disabled={!canWrite} onClick={() => write.mutate()}>
            {write.isPending ? 'Записываю…' : 'Записать'}
          </button>
          <button className="btn btn--ghost" onClick={() => setConfirm(false)}>
            Отмена
          </button>
        </div>
      </Sheet>
    </div>
  );
}
