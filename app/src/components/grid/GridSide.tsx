/**
 * The editor's side panel: what is selected (name, size, heroes, glyphs the game will not show)
 * and the heroes to drag onto the grid, found by name or slang like the draft's search.
 */
import { useMemo, useState } from 'react';

import { useHeroes } from '../../api/hooks';
import type { Hero } from '../../api/types';
import { CANVAS_H, CANVAS_W, cleanName, glyphWarnings, HEADER, listSize } from '../../lib/grid/dota';
import { clampItem, type GroupItem, type Item } from '../../lib/grid/doc';
import { searchHeroes } from '../../lib/search';
import { activeGrid, useGrids } from '../../state/grids';
import { Segmented, Slider } from '../ui';
import { Portrait, useHeroDrag } from './GridCanvas';

const ATTRS = [
  { value: 'all-heroes', label: 'Все' },
  { value: 'str', label: 'Сила' },
  { value: 'agi', label: 'Ловк.' },
  { value: 'int', label: 'Инт.' },
  { value: 'all', label: 'Унив.' },
] as const;

export function GridSide({ onEditArt }: { onEditArt: (id: string) => void }) {
  const grid = useGrids(activeGrid);
  const selected = useGrids((s) => s.selected);
  const item = grid.items.find((i) => i.id === selected) ?? null;
  return (
    <div className="gside">
      {item ? <Inspector item={item} onEditArt={onEditArt} /> : <p className="hint">Выбери группу, подпись или арт на сетке, чтобы поменять их. Героев тяни в группы.</p>}
      <Palette group={item?.type === 'group' ? item : null} placed={new Set(grid.items.flatMap((i) => (i.type === 'group' ? i.heroes : [])))} />
    </div>
  );
}

function Warnings({ text }: { text: string }) {
  const w = glyphWarnings(text);
  return (
    <>
      {!!w.invisible.length && <p className="warn small">Дота не показывает: {w.invisible.join(' ')}</p>}
      {!!w.foreign.length && <p className="hint">Нет в шрифте Доты, в игре будут другой ширины: {w.foreign.join(' ')}</p>}
    </>
  );
}

function Inspector({ item, onEditArt }: { item: Item; onEditArt: (id: string) => void }) {
  const { editItems, select } = useGrids.getState();
  const patch = (p: Partial<Item>, merge = false) =>
    editItems((l) => l.map((i) => (i.id === item.id ? clampItem({ ...i, ...p } as Item) : i)), merge);
  const remove = () => {
    editItems((l) => l.filter((i) => i.id !== item.id));
    select(null);
  };
  if (item.type === 'group') return <GroupInspector g={item} patch={patch} remove={remove} />;
  if (item.type === 'text')
    return (
      <div className="gside__box">
        <h3>Подпись</h3>
        <input className="input" value={item.text} maxLength={300} onChange={(e) => patch({ text: cleanName(e.target.value) }, true)} />
        <Warnings text={item.text} />
        <p className="hint">Это пустая категория Доты: в игре видно только её имя.</p>
        <button className="btn btn--sm" onClick={remove}>
          Удалить
        </button>
      </div>
    );
  return (
    <div className="gside__box">
      <h3>{item.source.kind === 'text' ? 'Арт из текста' : 'Арт из картинки'}</h3>
      <p className="hint">
        {item.rows.filter((r) => r.text.trim()).length} категорий, {Math.round(item.w)}×{Math.round(item.h)}. Двигай мышью или стрелками.
      </p>
      <div className="row">
        <button className="btn btn--sm" onClick={() => onEditArt(item.id)}>
          Изменить…
        </button>
        <button className="btn btn--sm" onClick={remove}>
          Удалить
        </button>
      </div>
    </div>
  );
}

function GroupInspector({ g, patch, remove }: { g: GroupItem; patch: (p: Partial<GroupItem>, merge?: boolean) => void; remove: () => void }) {
  const [cols, setCols] = useState(Math.min(10, Math.max(1, g.heroes.length || 6)));
  const [scale, setScale] = useState(1);
  const byId = useHeroes().data?.byId;
  const fit = (c = cols, s = scale) => {
    const size = listSize(g.heroes.length || c, c, s);
    patch({ w: Math.min(CANVAS_W, size.w), h: Math.min(CANVAS_H - HEADER, size.h) }, true);
  };
  return (
    <div className="gside__box">
      <h3>Группа</h3>
      <input className="input" value={g.name} maxLength={120} placeholder="Без названия" onChange={(e) => patch({ name: cleanName(e.target.value) }, true)} />
      <Warnings text={g.name} />
      <p className="hint">
        Героев: {g.heroes.length}. Размер {Math.round(g.w)}×{Math.round(g.h)} — Дота сама подгоняет карточки под него. Правый щелчок по герою убирает его.
      </p>
      <Slider label="Столбцов" value={cols} min={1} max={20} step={1} onChange={(v) => (setCols(v), fit(v))} />
      <Slider label="Размер карточек" value={scale} min={0.4} max={1.6} step={0.05} onChange={(v) => (setScale(v), fit(cols, v))} format={(v) => `${Math.round(v * 100)}%`} />
      <div className="row">
        <button
          className="btn btn--sm"
          disabled={!g.heroes.length || !byId}
          onClick={() => patch({ heroes: [...g.heroes].sort((a, b) => (byId?.get(a)?.name ?? '').localeCompare(byId?.get(b)?.name ?? '')) })}
        >
          По алфавиту
        </button>
        <button className="btn btn--sm" disabled={!g.heroes.length} onClick={() => patch({ heroes: [] })}>
          Убрать героев
        </button>
        <button className="btn btn--sm" onClick={remove}>
          Удалить группу
        </button>
      </div>
    </div>
  );
}

function Palette({ group, placed }: { group: GroupItem | null; placed: Set<number> }) {
  const heroes = useHeroes().data?.heroes;
  const [q, setQ] = useState('');
  const [attr, setAttr] = useState<(typeof ATTRS)[number]['value']>('all-heroes');
  const list = useMemo(() => {
    if (!heroes) return [];
    if (q.trim()) return searchHeroes(heroes, q, 40);
    return [...heroes].filter((h) => attr === 'all-heroes' || h.attr === attr).sort((a, b) => a.name.localeCompare(b.name));
  }, [heroes, q, attr]);
  const add = (h: Hero) => {
    if (!group) return;
    useGrids.getState().editItems((l) => l.map((i) => (i.id === group.id && i.type === 'group' ? { ...i, heroes: [...i.heroes, h.id] } : i)));
  };
  return (
    <div className="gside__box gside__palette">
      <h3>Герои</h3>
      <input
        className="input"
        value={q}
        placeholder="Поиск: имя или сленг (пудж, вр, сф)"
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && list[0] && add(list[0])}
      />
      {!q && <Segmented small value={attr} options={ATTRS.map((a) => ({ value: a.value, label: a.label }))} onChange={setAttr} />}
      <p className="hint">{group ? `Щелчок или Enter — в «${group.name || 'группу'}», или тяни в любую группу.` : 'Тяни героя в группу на сетке.'}</p>
      {heroes && placed.size > 0 && placed.size < heroes.length && (
        <p className="hint">
          На сетке {placed.size} из {heroes.length} героев: остальных в этой сетке Доты не будет видно (бледные — уже стоят).
        </p>
      )}
      <div className="gside__heroes">
        {list.map((h) => (
          <button
            key={h.id}
            className={`gside__hero ${placed.has(h.id) ? 'is-placed' : ''}`}
            title={`${h.name}${placed.has(h.id) ? ' — уже на сетке' : ''}`}
            onPointerDown={(e) => e.button === 0 && useHeroDrag.setState({ hero: h.id, from: null, x: e.clientX, y: e.clientY })}
            onClick={() => add(h)}
          >
            <Portrait id={h.id} />
          </button>
        ))}
      </div>
    </div>
  );
}
