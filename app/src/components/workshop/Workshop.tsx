/**
 * «Оформление → Мастерская»: GridStudio's workshop (gridstudio.me) — grids, ready-made arts and menu
 * backgrounds made by its users. A grid goes into our editor (and from there into Dota), an art into
 * the open grid, a background into the menu background builder. The author is shown on every card
 * and «На сайте» opens the work there. Everything comes through our backend (data/gridstudio.py),
 * which caches it; works tagged 18+ are not shown.
 */
import { useQuery } from '@tanstack/react-query';
import { CalendarDays, Download, Flame, Image, LayoutGrid, Palette, Sparkles } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { create } from 'zustand';

import { api, asset } from '../../api/client';
import { fromDota, type DotaConfig } from '../../lib/grid/doc';
import { artToItems, type WorkshopArt } from '../../lib/workshop';
import { addGrids, useGrids } from '../../state/grids';
import { useUi } from '../../state/ui';
import { ExternalLink } from '../ExternalLink';
import { Ti } from '../Icons';
import { PREFIX } from '../grid/GridFile';
import { takeBackgroundFile } from '../mods/BackgroundBuilder';
import { Empty, ErrorBox, Loading, Segmented } from '../ui';

type Section = 'grids' | 'backgrounds' | 'arts';
type Sort = 'popular' | 'week' | 'downloads' | 'new';

interface Meta {
  grid_tags: string[];
  background_tags: string[];
  aspects: string[];
  site: string;
}
interface GridCard {
  id: string;
  revision: number | null;
  title: string;
  author: string;
  credit: string;
  tags: string[];
  likes: number;
  downloads: number;
  url: string;
}
interface BgCard {
  id: number;
  title: string;
  author: string;
  credit: string;
  tags: string[];
  aspect: string;
  seconds: number | null;
  likes: number;
  downloads: number;
  has_preview: boolean;
  url: string;
}
interface Art extends WorkshopArt {
  category: string;
  author: string;
  credit: string;
}

const SORTS: { value: Sort; label: ReactNode }[] = [
  { value: 'popular', label: <><Ti icon={Flame} />Популярные</> },
  { value: 'week', label: <><Ti icon={CalendarDays} />За неделю</> },
  { value: 'downloads', label: <><Ti icon={Download} />Скачивают</> },
  { value: 'new', label: <><Ti icon={Sparkles} />Новые</> },
];

const q = (o: Record<string, string | number>) =>
  Object.entries(o)
    .filter(([, v]) => v !== '' && v !== undefined)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&');

function Stats({ likes, downloads }: { likes: number; downloads: number }) {
  return (
    <span className="muted small">
      ♥ {likes} · ⤓ {downloads}
    </span>
  );
}

function Grids({ meta, onNote }: { meta?: Meta; onNote: (s: string) => void }) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [tag, setTag] = useState('');
  const [sort, setSort] = useState<Sort>('popular');
  const [pages, setPages] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const set = useUi((s) => s.set);
  const list = useQuery({
    queryKey: ['ws-grids', query, tag, sort, pages],
    queryFn: async () => {
      const all: GridCard[] = [];
      let total = 0;
      let stale = false;
      for (let page = 0; page < pages; page++) {
        const r = await api<{ items: GridCard[]; total: number; stale: boolean }>(`/workshop/grids?${q({ q: query, tag, sort, page })}`);
        all.push(...r.items);
        total = r.total;
        stale ||= r.stale;
      }
      return { items: all, total, stale };
    },
    retry: false,
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });
  const take = async (g: GridCard) => {
    setBusy(g.id);
    setErr(null);
    try {
      const file = await api<{ configs: DotaConfig[] }>(`/workshop/grids/${g.id}`);
      const grids = file.configs.map((c) => ({ ...fromDota(c, PREFIX), name: g.title }));
      addGrids(grids);
      onNote(`«${g.title}» (автор: ${g.author}) добавлена в редактор сеток.`);
      set({ lookTab: 'grids' });
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <Filters
        search={search}
        setSearch={setSearch}
        onSearch={() => (setQuery(search), setPages(1))}
        tags={meta?.grid_tags ?? []}
        tag={tag}
        setTag={(t) => (setTag(t), setPages(1))}
        sort={sort}
        setSort={(s) => (setSort(s), setPages(1))}
        placeholder="Название или автор сетки"
      />
      {err ? <ErrorBox error={err} /> : null}
      {list.error && <ErrorBox error={list.error} />}
      {list.data?.stale && <p className="hint">GridStudio сейчас не отвечает — показан последний сохранённый список.</p>}
      {list.isPending && <Loading>Загружаю сетки GridStudio…</Loading>}
      {list.data && !list.data.items.length && <Empty>Ничего не нашлось.</Empty>}
      <div className="ws-cards">
        {list.data?.items.map((g) => (
          <article key={g.id} className="ws-card">
            <img className="ws-card__img" src={asset(`/workshop-media/grid/${g.id}.jpg?rev=${g.revision ?? ''}`)} alt="" loading="lazy" />
            <div className="ws-card__body">
              <b className="ws-card__title" title={g.title}>
                {g.title}
              </b>
              <span className="muted small">
                {g.author}
                {g.credit ? ` · по мотивам: ${g.credit}` : ''}
              </span>
              <Stats likes={g.likes} downloads={g.downloads} />
            </div>
            <div className="ws-card__actions">
              <button className="btn btn--sm btn--accent" onClick={() => take(g)} disabled={busy === g.id}>
                {busy === g.id ? 'Скачиваю…' : 'В редактор'}
              </button>
              <ExternalLink className="btn btn--sm btn--ghost" href={g.url}>
                На сайте
              </ExternalLink>
            </div>
          </article>
        ))}
      </div>
      {list.data && list.data.items.length < list.data.total && (
        <button className="btn" onClick={() => setPages((p) => p + 1)} disabled={list.isFetching}>
          {list.isFetching ? 'Загружаю…' : 'Показать ещё'}
        </button>
      )}
    </>
  );
}

function Backgrounds({ meta, onNote }: { meta?: Meta; onNote: (s: string) => void }) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [tag, setTag] = useState('');
  const [aspect, setAspect] = useState('');
  const [sort, setSort] = useState<Sort>('popular');
  const [pages, setPages] = useState(1);
  const [hover, setHover] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const set = useUi((s) => s.set);
  const list = useQuery({
    queryKey: ['ws-bgs', query, tag, aspect, sort, pages],
    queryFn: async () => {
      const all: BgCard[] = [];
      let total = 0;
      let stale = false;
      for (let page = 0; page < pages; page++) {
        const r = await api<{ items: BgCard[]; total: number; stale: boolean }>(`/workshop/backgrounds?${q({ q: query, tag, aspect, sort, page })}`);
        all.push(...r.items);
        total = r.total;
        stale ||= r.stale;
      }
      return { items: all, total, stale };
    },
    retry: false,
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });
  const take = async (b: BgCard) => {
    setBusy(b.id);
    setErr(null);
    try {
      const res = await fetch(asset(`/workshop-media/bg/${b.id}/video.webm`));
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? 'видео фона не скачалось');
      const blob = await res.blob();
      await takeBackgroundFile(new File([blob], `${b.title}.webm`, { type: 'video/webm' }));
      onNote(`Фон «${b.title}» (автор: ${b.author}) открыт в конструкторе: выбери кадр и эффекты, потом «Собрать и установить».`);
      set({ lookTab: 'background' });
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(null);
    }
  };
  return (
    <>
      <Filters
        search={search}
        setSearch={setSearch}
        onSearch={() => (setQuery(search), setPages(1))}
        tags={meta?.background_tags ?? []}
        tag={tag}
        setTag={(t) => (setTag(t), setPages(1))}
        sort={sort}
        setSort={(s) => (setSort(s), setPages(1))}
        placeholder="Название или автор фона"
      >
        <select className="select ws-aspect" value={aspect} onChange={(e) => (setAspect(e.target.value), setPages(1))} title="Формат экрана">
          <option value="">Любой экран</option>
          {meta?.aspects.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
      </Filters>
      {err ? <ErrorBox error={err} /> : null}
      {list.error && <ErrorBox error={list.error} />}
      {list.data?.stale && <p className="hint">GridStudio сейчас не отвечает — показан последний сохранённый список.</p>}
      {list.isPending && <Loading>Загружаю фоны GridStudio…</Loading>}
      {list.data && !list.data.items.length && <Empty>Ничего не нашлось.</Empty>}
      <div className="ws-cards">
        {list.data?.items.map((b) => (
          <article key={b.id} className="ws-card" onMouseEnter={() => setHover(b.id)} onMouseLeave={() => setHover(null)}>
            <div className="ws-card__media">
              <img className="ws-card__img" src={asset(`/workshop-media/bg/${b.id}/poster.jpg`)} alt="" loading="lazy" />
              {hover === b.id && b.has_preview && (
                <video className="ws-card__img ws-card__video" src={asset(`/workshop-media/bg/${b.id}/preview.webm`)} autoPlay loop muted playsInline />
              )}
              <span className="ws-card__badge">
                {b.aspect}
                {b.seconds ? ` · ${b.seconds} с` : ''}
              </span>
            </div>
            <div className="ws-card__body">
              <b className="ws-card__title" title={b.title}>
                {b.title}
              </b>
              <span className="muted small">{b.author}</span>
              <Stats likes={b.likes} downloads={b.downloads} />
            </div>
            <div className="ws-card__actions">
              <button className="btn btn--sm btn--accent" onClick={() => take(b)} disabled={busy === b.id}>
                {busy === b.id ? 'Скачиваю…' : 'В конструктор фона'}
              </button>
              <ExternalLink className="btn btn--sm btn--ghost" href={b.url}>
                На сайте
              </ExternalLink>
            </div>
          </article>
        ))}
      </div>
      {list.data && list.data.items.length < list.data.total && (
        <button className="btn" onClick={() => setPages((p) => p + 1)} disabled={list.isFetching}>
          {list.isFetching ? 'Загружаю…' : 'Показать ещё'}
        </button>
      )}
    </>
  );
}

function Arts({ onNote }: { onNote: (s: string) => void }) {
  const [search, setSearch] = useState('');
  const [cat, setCat] = useState('');
  const set = useUi((s) => s.set);
  const list = useQuery({ queryKey: ['ws-arts'], queryFn: () => api<{ items: Art[]; stale: boolean }>('/workshop/arts'), retry: false, staleTime: 30 * 60_000 });
  const cats = [...new Set((list.data?.items ?? []).map((a) => a.category).filter(Boolean))];
  const shown = (list.data?.items ?? []).filter(
    (a) => (!cat || a.category === cat) && (!search.trim() || `${a.name} ${a.author}`.toLowerCase().includes(search.trim().toLowerCase())),
  );
  const take = (a: Art) => {
    const { items } = artToItems(a);
    if (!items.length) return onNote(`В арте «${a.name}» нет символов, которые нарисует Дота.`);
    const s = useGrids.getState();
    s.editItems((l) => [...l, ...items]);
    onNote(`Арт «${a.name}» (${a.author || 'GridStudio'}) вставлен в открытую сетку: ${items.length} строк — перетащи его куда нужно.`);
    set({ lookTab: 'grids' });
  };
  return (
    <>
      <div className="ws-filters">
        <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Название или автор арта" />
        <div className="ws-tags">
          <button className={`chip-btn ${!cat ? 'is-on' : ''}`} onClick={() => setCat('')}>
            Все
          </button>
          {cats.map((c) => (
            <button key={c} className={`chip-btn ${cat === c ? 'is-on' : ''}`} onClick={() => setCat(c)}>
              {c}
            </button>
          ))}
        </div>
      </div>
      {list.error && <ErrorBox error={list.error} />}
      {list.isPending && <Loading>Загружаю арты GridStudio…</Loading>}
      {list.data && !shown.length && <Empty>Ничего не нашлось.</Empty>}
      <div className="ws-arts">
        {shown.slice(0, 120).map((a) => (
          <article key={a.id} className="ws-art">
            <pre className="ws-art__text">{a.rows?.length ? a.rows.map((r) => r.text).join('\n') : a.text}</pre>
            <div className="ws-card__body">
              <b className="ws-card__title">{a.name}</b>
              <span className="muted small">{[a.category, a.author, a.credit && `по мотивам: ${a.credit}`].filter(Boolean).join(' · ')}</span>
            </div>
            <button className="btn btn--sm btn--accent" onClick={() => take(a)}>
              В открытую сетку
            </button>
          </article>
        ))}
      </div>
      {shown.length > 120 && <p className="hint">Показаны первые 120 — уточни поиск.</p>}
    </>
  );
}

function Filters({ search, setSearch, onSearch, tags, tag, setTag, sort, setSort, placeholder, children }: {
  search: string;
  setSearch: (s: string) => void;
  onSearch: () => void;
  tags: string[];
  tag: string;
  setTag: (t: string) => void;
  sort: Sort;
  setSort: (s: Sort) => void;
  placeholder: string;
  children?: ReactNode;
}) {
  return (
    <div className="ws-filters">
      <form
        className="ws-search"
        onSubmit={(e) => {
          e.preventDefault();
          onSearch();
        }}
      >
        <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={placeholder} />
        <button className="btn" type="submit">
          Найти
        </button>
        {children}
      </form>
      <div className="ws-tags">
        <Segmented small value={sort} onChange={setSort} options={SORTS} />
        <button className={`chip-btn ${!tag ? 'is-on' : ''}`} onClick={() => setTag('')}>
          Все
        </button>
        {tags.map((t) => (
          <button key={t} className={`chip-btn ${tag === t ? 'is-on' : ''}`} onClick={() => setTag(t)}>
            {t}
          </button>
        ))}
      </div>
    </div>
  );
}

/** What the last «В редактор» / «В конструктор» did: shown on the «Оформление» page it switched to. */
export const useWorkshopNote = create<{ note: string | null; set: (note: string | null) => void }>((set) => ({
  note: null,
  set: (note) => set({ note }),
}));

export function WorkshopNote() {
  const { note, set } = useWorkshopNote();
  if (!note) return null;
  return (
    <p className="ws-note small" onClick={() => set(null)} title="Скрыть">
      {note} <span className="muted">×</span>
    </p>
  );
}

export function Workshop() {
  const [section, setSection] = useState<Section>('grids');
  const setNote = useWorkshopNote((s) => s.set);
  const meta = useQuery({ queryKey: ['ws-meta'], queryFn: () => api<Meta>('/workshop/meta'), staleTime: Infinity }).data;
  return (
    <div className="ws">
      <div className="ws-head">
        <Segmented
          value={section}
          onChange={setSection}
          options={[
            { value: 'grids', label: <><Ti icon={LayoutGrid} />Сетки</> },
            { value: 'backgrounds', label: <><Ti icon={Image} />Фоны меню</> },
            { value: 'arts', label: <><Ti icon={Palette} />Арты</> },
          ]}
        />
        <p className="hint">
          Работы пользователей мастерской{' '}
          <ExternalLink href="https://gridstudio.me/workshop">GridStudio</ExternalLink>. По её правилам опубликованные сетки и арты можно
          скачивать и менять; автор указан на каждой карточке.
        </p>
      </div>
      {section === 'grids' && <Grids meta={meta} onNote={setNote} />}
      {section === 'backgrounds' && <Backgrounds meta={meta} onNote={setNote} />}
      {section === 'arts' && <Arts onNote={setNote} />}
    </div>
  );
}
