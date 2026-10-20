/**
 * «Свои VPK»: the user's own VPK mods put into Dota the same way as our menu background — each into
 * a free pakNN_dir.vpk of the voice language folder (backend/drafter/game_mods/install.py), never
 * over another file, removed one by one or with «Убрать всё».
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FileArchive, Trash2, Upload } from 'lucide-react';
import { useRef, useState } from 'react';

import { api, apiBytes } from '../../api/client';
import { useUi } from '../../state/ui';
import { Ti } from '../Icons';
import { ErrorBox } from '../ui';
import { blocker, useModsStatus } from './ModsGate';

interface Installed {
  id: string;
  name: string;
  path: string;
  files: number;
  bytes: number;
  overlaps: { pack: string; files: number; example: string }[];
}

const MAX = 1_500_000_000;
const size = (n: number) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e8 ? 0 : 1)} МБ` : `${Math.max(1, Math.round(n / 1e3))} КБ`);
const fileName = (p: string) => p.split(/[\\/]/).pop() ?? p;

export function PackManager() {
  const enabled = useUi((s) => s.gameMods);
  const status = useModsStatus();
  const s = status.data;
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [tooBig, setTooBig] = useState<string | null>(null);
  const block = blocker(s, enabled) ?? (s && !s.usable ? 'Дота не читает папку английской озвучки — поставь другой язык озвучки (подробно выше).' : null);
  const add = useMutation({
    mutationFn: (f: File) => apiBytes<Installed>(`/game-mods/packs?accept=true&name=${encodeURIComponent(f.name)}`, f),
    onSettled: () => qc.invalidateQueries({ queryKey: ['game-mods'] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api('/game-mods/remove', { body: { what: 'pack', id } }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['game-mods'] }),
  });
  const packs = s?.packs ?? [];
  return (
    <div className="packs">
      <div className="panel__head">
        <h2>
          <Ti icon={FileArchive} />
          Свои VPK
        </h2>
        <button className="btn btn--sm btn--accent" disabled={!!block || add.isPending} onClick={() => input.current?.click()}>
          <Ti icon={Upload} />
          {add.isPending ? 'Ставлю…' : 'Добавить .vpk'}
        </button>
      </div>
      <p className="hint">
        Готовые моды Доты одним файлом <code>.vpk</code> (например, <code>pak01_dir.vpk</code> из мода). Файл кладётся в папку языка озвучки
        {s?.usable && s.language ? (
          <>
            {' '}
            <code>…\game\dota_{s.language}</code>
          </>
        ) : null}{' '}
        под свободным номером <code>pakNN_dir.vpk</code> — туда же, где лежит фон меню. Файлы Доты и чужие моды не трогаются, убрать можно в любой момент.
        Многотомные моды (<code>_000.vpk</code>, <code>_001.vpk</code>…) не подойдут.
      </p>
      {block && <p className="warn small">{block}</p>}
      <input
        ref={input}
        type="file"
        accept=".vpk"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = '';
          if (!f) return;
          if (f.size > MAX) return setTooBig(`${f.name}: больше 1,5 ГБ`);
          setTooBig(null);
          add.mutate(f);
        }}
      />
      {tooBig && <p className="small c-bad">{tooBig}</p>}
      {add.error && <ErrorBox error={add.error} />}
      {add.data && (
        <div className="small">
          <p className="c-good">
            {add.data.name} поставлен как {fileName(add.data.path)} · {add.data.files} файлов. Запусти Доту — мод подхватится.
          </p>
          {add.data.overlaps.map((o) => (
            <p key={o.pack} className="warn">
              Меняет те же файлы, что и {o.pack} ({o.files}, например <code>{o.example}</code>): в игре сработает один из них.
            </p>
          ))}
        </div>
      )}
      {packs.length > 0 ? (
        <ul className="packs__list">
          {packs.map((p) => (
            <li key={p.id} className="packs__row">
              <Ti icon={FileArchive} />
              <div>
                <b>{p.name}</b>
                <span className="muted small">
                  {fileName(p.path)} · {p.files} файлов · {size(p.bytes)}
                  {p.top.length ? ` · ${p.top.slice(0, 4).join(', ')}` : ''}
                  {p.intact ? '' : ' · файл изменён или удалён'}
                </span>
              </div>
              <button
                className="btn btn--sm btn--ghost"
                disabled={!!s?.running || remove.isPending}
                onClick={() => remove.mutate(p.id)}
                title="Убрать из Доты"
                aria-label={`Убрать ${p.name}`}
              >
                <Ti icon={Trash2} />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted small">Своих VPK пока нет.</p>
      )}
      {remove.error && <ErrorBox error={remove.error} />}
    </div>
  );
}
