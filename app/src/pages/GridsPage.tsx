/**
 * «Оформление»: the hero-grid editor, and Dota's menu background and fonts («Оформление игры»).
 *
 * The grid editor: an editor of Dota hero grids. The canvas is the game's grid (same size, same card fit,
 * names at the game's glyph widths), several grids in one file, art from text and pictures, import
 * of the file in Steam, export to a file and the safe write into Dota.
 */
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '../api/client';
import { Panel } from '../components/Glass';
import { ArtSheet, type ArtKind } from '../components/grid/ArtSheet';
import { GridCanvas } from '../components/grid/GridCanvas';
import { GridFileBar } from '../components/grid/GridFile';
import { GridSide } from '../components/grid/GridSide';
import { Sheet } from '../components/Sheet';
import { ErrorBox, Loading, plural, Segmented, Toggle } from '../components/ui';
import { Workshop, WorkshopNote } from '../components/workshop/Workshop';
import { BackgroundBuilder } from '../components/mods/BackgroundBuilder';
import { FontBuilder } from '../components/mods/FontBuilder';
import { ModsGate } from '../components/mods/ModsGate';
import { useUi } from '../state/ui';
import { CANVAS_W, SLOW_CATEGORIES } from '../lib/grid/dota';
import { categoryCount, emptyGrid, newGroup, newId, type ArtItem, type Grid, type TextItem } from '../lib/grid/doc';
import { layoutGroups } from '../lib/grid/layout';
import { activeGrid, addGrids, freeName, useGrids } from '../state/grids';

interface TemplatePreview {
  id: string;
  name: string;
  description: string;
  categories: { name: string; heroes: number[] }[];
  heroes: number;
}

function GridEditor() {
  const grid = useGrids(activeGrid);
  const grids = useGrids((s) => s.grids);
  const canUndo = useGrids((s) => s.past.length > 0);
  const canRedo = useGrids((s) => s.future.length > 0);
  const { edit, editItems, select, undo, redo } = useGrids.getState();
  const [art, setArt] = useState<{ kind: ArtKind; editing: ArtItem | null } | null>(null);
  const [adding, setAdding] = useState(false);
  const [renaming, setRenaming] = useState<string | null>(null);
  const count = categoryCount(grid);

  const addGroup = () => {
    const g = newGroup(20 + ((grid.items.length * 24) % 300), 20 + ((grid.items.length * 24) % 200));
    editItems((l) => [...l, g]);
    select(g.id);
  };
  const addText = () => {
    const t: TextItem = { id: newId(), type: 'text', text: 'Подпись', x: CANVAS_W / 2 - 40, y: 20 };
    editItems((l) => [...l, t]);
    select(t.id);
  };
  const removeGrid = (id: string) =>
    edit((d) => {
      const left = d.grids.filter((g) => g.id !== id);
      const grids = left.length ? left : [emptyGrid()];
      return { grids, active: d.active === id ? grids[0].id : d.active };
    });
  const duplicate = () => addGrids([{ ...structuredClone(grid), name: `${grid.name} (копия)` }]);

  return (
    <>
      <Panel className="geditor">
        <div className="gtabs">
          {grids.map((g) =>
            renaming === g.id ? (
              <input
                key={g.id}
                className="input gtabs__rename"
                autoFocus
                defaultValue={g.name}
                maxLength={60}
                onBlur={(e) => {
                  const name = e.target.value.replace(/[<>&\r\n\t]/g, '').trim() || g.name;
                  edit((d) => ({ ...d, grids: d.grids.map((x) => (x.id === g.id ? { ...x, name: freeName(d.grids.filter((y) => y.id !== g.id), name) } : x)) }));
                  setRenaming(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                  if (e.key === 'Escape') setRenaming(null);
                }}
              />
            ) : (
              <button
                key={g.id}
                className={`gtabs__tab ${g.id === grid.id ? 'is-on' : ''} ${g.game ? '' : 'is-off'}`}
                onClick={() => (edit((d) => ({ ...d, active: g.id })), select(null))}
                onDoubleClick={() => setRenaming(g.id)}
                title="Двойной щелчок — переименовать"
              >
                {g.name}
              </button>
            ),
          )}
          <button className="btn btn--sm btn--ghost" onClick={() => setAdding(true)}>
            + Сетка
          </button>
        </div>

        <div className="gtools">
          <button className="btn btn--sm" onClick={addGroup}>
            + Группа
          </button>
          <button className="btn btn--sm" onClick={addText}>
            + Подпись
          </button>
          <button className="btn btn--sm" onClick={() => setArt({ kind: 'text', editing: null })}>
            Арт из текста
          </button>
          <button className="btn btn--sm" onClick={() => setArt({ kind: 'image', editing: null })}>
            Арт из картинки
          </button>
          <span className="gtools__sep" />
          <button className="btn btn--sm btn--ghost" onClick={undo} disabled={!canUndo} title="Ctrl+Z">
            Отменить
          </button>
          <button className="btn btn--sm btn--ghost" onClick={redo} disabled={!canRedo} title="Ctrl+Y">
            Повторить
          </button>
          <span className="gtools__grow" />
          <Toggle on={grid.game} onChange={(on) => edit((d) => ({ ...d, grids: d.grids.map((g) => (g.id === grid.id ? { ...g, game: on } : g)) }))} label="В Доту" />
          <button className="btn btn--sm btn--ghost" onClick={() => setRenaming(grid.id)}>
            Переименовать
          </button>
          <button className="btn btn--sm btn--ghost" onClick={duplicate}>
            Копия
          </button>
          <button className="btn btn--sm btn--ghost" onClick={() => removeGrid(grid.id)} title="Удалить сетку из редактора (Ctrl+Z вернёт)">
            Удалить
          </button>
        </div>

        <div className="geditor__main">
          <div className="geditor__canvas">
            <GridCanvas />
            <p className={`small ${count > SLOW_CATEGORIES ? 'warn' : 'muted'}`}>
              {count} {plural(count, 'категория', 'категории', 'категорий')}
              {count > SLOW_CATEGORIES ? ` — больше ${SLOW_CATEGORIES}, Дота может тормозить на экране героев` : ''}. Сетка 1193×593 — как на экране героев Доты;
              подписи и арт стоят по ширинам шрифта игры.
            </p>
          </div>
          <GridSide onEditArt={(id) => setArt({ kind: (grid.items.find((i) => i.id === id) as ArtItem).source.kind, editing: grid.items.find((i) => i.id === id) as ArtItem })} />
        </div>

        <GridFileBar />
      </Panel>

      <ArtSheet open={!!art} kind={art?.kind ?? 'text'} editing={art?.editing ?? null} onClose={() => setArt(null)} />
      <NewGridSheet open={adding} onClose={() => setAdding(false)} />
    </>
  );
}

export function GridsPage() {
  const tab = useUi((s) => s.lookTab);
  const set = useUi((s) => s.set);
  return (
    <div className="grids-page">
      <div className="look-tabs">
        <Segmented
          value={tab}
          onChange={(lookTab) => set({ lookTab })}
          options={[
            { value: 'grids', label: 'Сетки героев' },
            { value: 'background', label: 'Фон меню' },
            { value: 'font', label: 'Шрифт' },
            { value: 'workshop', label: 'Мастерская GridStudio' },
          ]}
        />
      </div>
      <WorkshopNote />
      {tab === 'grids' ? (
        <GridEditor />
      ) : tab === 'workshop' ? (
        <Panel className="looks">
          <Workshop />
        </Panel>
      ) : (
        <Panel className="looks">
          <ModsGate />
          {tab === 'background' ? <BackgroundBuilder /> : <FontBuilder />}
        </Panel>
      )}
    </div>
  );
}

function NewGridSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const templates = useQuery({
    queryKey: ['hero-grids'],
    queryFn: () => api<{ grids: TemplatePreview[] }>('/hero-grids'),
    enabled: open,
    staleTime: 120_000,
    retry: false,
  });
  const add = (g: Grid) => {
    addGrids([g]);
    onClose();
  };
  const fromTemplate = (t: TemplatePreview) => {
    const cats = t.categories.filter((c) => c.heroes.length);
    add({ ...emptyGrid(t.name), items: layoutGroups(cats) });
  };
  return (
    <Sheet open={open} onClose={onClose} title="Новая сетка">
      <div className="gnew">
        <button className="gnew__opt glass glass--inset" onClick={() => add(emptyGrid())}>
          <b>Пустая сетка</b>
          <span className="hint">Чистый холст: группы, герои, подписи и арт — сам.</span>
        </button>
        <p className="label">Заготовки из данных приложения (на твоём ранге)</p>
        {templates.isPending && <Loading>Собираю заготовки…</Loading>}
        {templates.error && <ErrorBox error={templates.error} />}
        {templates.data?.grids.map((t) => (
          <button key={t.id} className="gnew__opt glass glass--inset" disabled={!t.heroes} onClick={() => fromTemplate(t)}>
            <b>{t.name}</b>
            <span className="hint">{t.heroes ? t.description : 'пусто — нет данных'}</span>
          </button>
        ))}
        <p className="hint">Заготовка — просто стартовая раскладка: дальше её можно менять как угодно.</p>
      </div>
    </Sheet>
  );
}
