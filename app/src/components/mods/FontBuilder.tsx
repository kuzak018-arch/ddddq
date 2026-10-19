/**
 * «Шрифт»: a free font with Cyrillic from the app's set (SIL OFL) or the user's own TTF/OTF, for
 * Dota's text, digits and/or titles. Previews: the menu and a match (FontScene) and the hero grid open
 * in the editor. The backend rewrites the font under Valve's 29 file names and installs it (fonts can
 * only replace Valve's files: Panorama reads them with fontconfig from the folder, not from packs).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { api, apiBytes, apiUpload, backend } from '../../api/client';
import { activeGrid, useGrids } from '../../state/grids';
import { useUi } from '../../state/ui';
import { ErrorBox, Toggle } from '../ui';
import { FitWidth, GridPicture } from './DotaScreens';
import { FontScene } from './FontScene';
import { blocker, useModsStatus } from './ModsGate';

interface CatalogFont {
  id: string;
  family: string;
  style: string;
  license: string;
  files: { weight: number; file: string; bytes: number }[];
}
interface Checked {
  name: string;
  family: string;
  style: string;
  weight: number;
  italic: boolean;
  missing: { latin: string[]; cyrillic: string[] };
  file: File;
}

const ROLES = [
  { key: 'Radiance', label: 'Текст', hint: 'чат, подсказки, названия групп в сетке' },
  { key: 'RadianceM', label: 'Цифры', hint: 'золото, счёт, таймеры' },
  { key: 'Reaver', label: 'Заголовки', hint: 'верхнее меню, заголовки' },
] as const;

/** Loads the faces into the document under one family name for the previews. */
function usePreviewFamily(faces: { url: string | ArrayBuffer; weight: number; italic?: boolean }[] | null, key: string) {
  const [family, setFamily] = useState<string | null>(null);
  useEffect(() => {
    if (!faces?.length) return setFamily(null);
    let alive = true;
    const name = `DrafterPreview-${key}`;
    const loaded = faces.map((f) => new FontFace(name, typeof f.url === 'string' ? `url(${f.url})` : f.url, { weight: String(f.weight), style: f.italic ? 'italic' : 'normal' }));
    Promise.all(loaded.map((f) => f.load()))
      .then((list) => {
        if (!alive) return;
        list.forEach((f) => document.fonts.add(f));
        setFamily(name);
      })
      .catch(() => alive && setFamily(null));
    return () => {
      alive = false;
      loaded.forEach((f) => document.fonts.delete(f));
    };
  }, [faces, key]);
  return family;
}

export function FontBuilder() {
  const enabled = useUi((s) => s.gameMods);
  const status = useModsStatus().data;
  const qc = useQueryClient();
  const grid = useGrids(activeGrid);
  const catalog = useQuery({ queryKey: ['mod-fonts'], queryFn: () => api<{ fonts: CatalogFont[]; base: string }>('/game-mods/fonts'), staleTime: Infinity });
  const [base, setBase] = useState('');
  useEffect(() => {
    void backend().then((b) => setBase(b.url));
  }, []);
  const [picked, setPicked] = useState<string>('libre-franklin');
  const [own, setOwn] = useState<Checked[]>([]);
  const [roles, setRoles] = useState<Record<string, boolean>>({ Radiance: true, RadianceM: true, Reaver: true });
  const [keepGrid, setKeepGrid] = useState(true);
  const [err, setErr] = useState<unknown>(null);

  const faces = useMemo(() => {
    if (picked === 'own') return own.length ? own.map((f) => ({ url: URL.createObjectURL(f.file), weight: f.weight, italic: f.italic })) : null;
    const font = catalog.data?.fonts.find((f) => f.id === picked);
    if (!font || !base) return null;
    return font.files.map((f) => ({ url: `${base}${catalog.data!.base}/${font.id}/${f.file}`, weight: f.weight }));
  }, [picked, own, catalog.data, base]);
  const family = usePreviewFamily(faces, picked + own.length);

  const check = async (files: FileList) => {
    setErr(null);
    const out: Checked[] = [];
    for (const file of Array.from(files)) {
      if (!/\.(ttf|otf)$/i.test(file.name)) {
        setErr(new Error(`${file.name}: нужен файл .ttf или .otf`));
        continue;
      }
      try {
        const r = await apiBytes<Omit<Checked, 'name' | 'file'>>('/game-mods/font-check', file);
        out.push({ ...r, name: file.name, file });
      } catch (e) {
        setErr(new Error(`${file.name}: ${e instanceof Error ? e.message : e}`));
      }
    }
    if (out.length) {
      setOwn(out);
      setPicked('own');
    }
  };

  const install = useMutation({
    mutationFn: async () => {
      const families = Object.keys(roles).filter((r) => roles[r]);
      const meta = { accept: true, catalog: picked === 'own' ? null : picked, families, keep_grid: keepGrid && roles.Radiance };
      const files = picked === 'own' ? await Promise.all(own.map(async (f) => new Uint8Array(await f.file.arrayBuffer()))) : [];
      return apiUpload<{ files: number; folder: string }>('/game-mods/fonts', meta, files);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['game-mods'] }),
  });

  const block = blocker(status, enabled);
  const none = !Object.values(roles).some(Boolean);
  const missing = picked === 'own' ? own.flatMap((f) => f.missing.cyrillic) : [];

  return (
    <div className="fontb">
      <div className="fontb-preview">
        <FontScene family={family} roles={roles} />
        <div className="fontb-grid">
          <FitWidth width={1193}>
            <GridPicture grid={grid} fontFamily={family && roles.Radiance && !keepGrid ? `'${family}'` : undefined} />
          </FitWidth>
        </div>
        <p className="hint">
          Слева — главное меню, справа — матч (черту можно двигать); ниже — сетка «{grid.name}» из редактора. Буквы ставятся по одной, как в Доте, но
          итог в игре может немного отличаться.
        </p>
      </div>
      <div className="fontb-side">
        <h3>Шрифт</h3>
        <div className="fontb-list">
          {catalog.data?.fonts.map((f) => (
            <button key={f.id} className={`fontb-item ${picked === f.id ? 'is-on' : ''}`} onClick={() => setPicked(f.id)}>
              <b>{f.family}</b>
              <span className="muted small">
                {f.style} · {f.files.length} {f.files.length === 1 ? 'начертание' : 'начертаний'}
              </span>
            </button>
          ))}
          <label className={`fontb-item ${picked === 'own' ? 'is-on' : ''}`}>
            <b>Свой шрифт…</b>
            <span className="muted small">{own.length ? own.map((f) => `${f.family} ${f.weight}`).join(', ') : 'TTF или OTF, можно несколько начертаний'}</span>
            <input type="file" accept=".ttf,.otf" multiple hidden onChange={(e) => e.target.files && void check(e.target.files)} />
          </label>
        </div>
        <p className="hint">Подборка — свободные шрифты с кириллицей (SIL Open Font License), их лицензии лежат рядом с файлами в программе.</p>
        {!!missing.length && <p className="warn small">В твоём шрифте нет букв: {[...new Set(missing)].join(' ')} — Дота покажет их другим шрифтом.</p>}
        <span className="label">Что заменить</span>
        {ROLES.map((r) => (
          <Toggle key={r.key} on={roles[r.key]} onChange={(on) => setRoles({ ...roles, [r.key]: on })} label={<span>{r.label} <span className="muted small">— {r.hint}</span></span>} />
        ))}
        {roles.Radiance && (
          <>
            <Toggle on={keepGrid} onChange={setKeepGrid} label="Рисунки в сетке героев не съедут" />
            <p className="hint">
              Арт в сетке собран по ширинам шрифта Доты: с другим шрифтом он разъедется. Включено — названия групп в сетке (и часть подписей меню тем
              же начертанием) остаются шрифтом Доты.
            </p>
          </>
        )}
        {!!err && <ErrorBox error={err} />}
        {install.error && <ErrorBox error={install.error} />}
        {install.data && <p className="small c-good">Готово: заменено файлов Доты — {install.data.files}. Оригиналы сохранены, «Убрать всё» их вернёт. Запускай Доту.</p>}
        <button className="btn btn--accent" disabled={!!block || none || install.isPending || (picked === 'own' && !own.length)} onClick={() => install.mutate()}>
          {install.isPending ? 'Ставлю…' : 'Поставить шрифт в Доту'}
        </button>
        {block && <p className="hint">{block}</p>}
      </div>
    </div>
  );
}
