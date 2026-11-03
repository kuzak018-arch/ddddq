/**
 * «Патчи»: Valve's patch notes in Russian (from the game's localisation file, see
 * backend/drafter/data/patchnotes.py), newest first. A patch opens grouped by general changes,
 * heroes (their own lines, abilities, talents) and items; the heroes the user plays come first and
 * are marked in the list of patches.
 */
import { useQuery } from '@tanstack/react-query';
import { CalendarDays, Globe, Package, RefreshCw, ScrollText, Search, Shield, Star } from 'lucide-react';
import { useMemo, useState } from 'react';

import { api, asset } from '../api/client';
import { useHeroes } from '../api/hooks';
import { TalentIcon } from '../components/Ability';
import { AttrIcon } from '../components/DotaIcons';
import { Panel } from '../components/Glass';
import { Ti } from '../components/Icons';
import { Empty, ErrorBox, HeroIcon, ItemIcon, Loading, plural, Segmented } from '../components/ui';
import { useUi } from '../state/ui';

interface PatchRow {
  version: string;
  date: number | null;
  lines: number;
  heroes: number;
  items: number;
  mine: number[];
}
interface PatchHero {
  id: number;
  key: string;
  name: string;
  notes: string[];
  talents: string[];
  abilities: { key: string; name: string; icon?: string | null; notes: string[] }[];
}
interface Patch {
  version: string;
  date: number | null;
  general: { title: string | null; notes: string[] }[];
  items: { key: string; name: string; icon: string; notes: string[] }[];
  heroes: PatchHero[];
  mine: number[];
  stale: boolean;
}
type Filter = 'all' | 'mine' | 'heroes' | 'items' | 'general';

const fmtDate = (ts: number | null) => (ts ? new Date(ts * 1000).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }) : '');

export function PatchesPage() {
  const [refresh, setRefresh] = useState(0);
  const list = useQuery({
    queryKey: ['patches', refresh],
    queryFn: () => api<{ patches: PatchRow[]; stale: boolean }>(`/patches${refresh ? '?refresh=true' : ''}`),
    staleTime: 30 * 60_000,
  });
  const [picked, setPicked] = useState<string | null>(null);
  const version = picked ?? list.data?.patches[0]?.version ?? null;
  return (
    <div className="patches">
      <Panel className="patches__list" refracting>
        <div className="panel__head">
          <h2>
            <Ti icon={ScrollText} />
            Патчи
          </h2>
          <button className="btn btn--sm btn--ghost" onClick={() => setRefresh((n) => n + 1)} disabled={list.isFetching} title="Скачать свежие патчноуты">
            <Ti icon={RefreshCw} />
          </button>
        </div>
        {list.isPending && <Loading>Загружаю патчноуты…</Loading>}
        {list.error && <ErrorBox error={list.error} />}
        {list.data?.stale && <p className="muted small">Нет сети — показан последний скачанный список.</p>}
        <ul className="patches__rows">
          {list.data?.patches.map((p) => (
            <li key={p.version}>
              <button className={`patches__row ${p.version === version ? 'is-on' : ''}`} onClick={() => setPicked(p.version)}>
                <b className="display">{p.version}</b>
                <span className="muted small">{fmtDate(p.date) || `${p.lines} изменений`}</span>
                <span className="patches__counts small">
                  {p.heroes} {plural(p.heroes, 'герой', 'героя', 'героев')} · {p.items} {plural(p.items, 'предмет', 'предмета', 'предметов')}
                </span>
                {p.mine.length > 0 && (
                  <span className="patches__mine" title="Изменились твои герои">
                    <Star size={12} strokeWidth={2.4} /> {p.mine.length}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
        <p className="hint">Тексты — из файлов локализации Доты (их выкладывает dotabuff/d2vpkr на GitHub), на русском, как в клиенте.</p>
      </Panel>
      <Panel className="patches__body">{version ? <PatchView version={version} /> : !list.isPending && <Empty>Патчноутов нет.</Empty>}</Panel>
    </div>
  );
}

function PatchView({ version }: { version: string }) {
  const q = useQuery({ queryKey: ['patch', version], queryFn: () => api<Patch>(`/patches/${version}`), staleTime: 30 * 60_000 });
  const heroes = useHeroes().data;
  const [filter, setFilter] = useState<Filter>('all');
  const [text, setText] = useState('');
  const p = q.data;
  const needle = text.trim().toLowerCase();
  const shown = useMemo(() => {
    if (!p) return null;
    const hit = (name: string, notes: string[]) => !needle || name.toLowerCase().includes(needle) || notes.some((n) => n.toLowerCase().includes(needle));
    const heroHit = (h: PatchHero) => {
      const ru = heroes?.byId.get(h.id)?.ru ?? [];
      return hit(h.name, [...h.notes, ...h.talents, ...h.abilities.flatMap((a) => [a.name, ...a.notes]), ...ru]);
    };
    return {
      general: filter === 'all' || filter === 'general' ? p.general.filter((g) => hit(g.title ?? '', g.notes)) : [],
      heroes: filter === 'all' || filter === 'heroes' || filter === 'mine' ? p.heroes.filter((h) => (filter !== 'mine' || p.mine.includes(h.id)) && heroHit(h)) : [],
      items: filter === 'all' || filter === 'items' ? p.items.filter((i) => hit(i.name, i.notes)) : [],
    };
  }, [p, filter, needle, heroes]);
  if (q.isPending) return <Loading>Открываю патч {version}…</Loading>;
  if (q.error) return <ErrorBox error={q.error} />;
  if (!p || !shown) return null;
  const empty = !shown.general.length && !shown.heroes.length && !shown.items.length;
  return (
    <div className="patch">
      <div className="panel__head panel__head--wrap">
        <h2>
          Патч {p.version}
          {p.date && (
            <span className="muted patch__date">
              <CalendarDays size={14} /> {fmtDate(p.date)}
            </span>
          )}
        </h2>
        <Segmented
          small
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'all', label: 'Всё' },
            { value: 'mine', label: <><Ti icon={Star} />Мои герои · {p.mine.length}</>, title: 'Герои, на которых ты играешь чаще всего' },
            { value: 'heroes', label: <><Ti icon={Shield} />Герои · {p.heroes.length}</> },
            { value: 'items', label: <><Ti icon={Package} />Предметы · {p.items.length}</> },
            { value: 'general', label: <><Ti icon={Globe} />Общее</> },
          ]}
        />
        <label className="patch__search">
          <Search size={15} />
          <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Герой, предмет или слово…" spellCheck={false} />
        </label>
      </div>
      {p.mine.length > 0 && filter === 'all' && !needle && (
        <div className="patch__minebar">
          <span className="label">
            <Ti icon={Star} />
            Изменились твои герои
          </span>
          {p.mine.map((id) => (
            <a key={id} href={`#hero-${id}`} onClick={(e) => (e.preventDefault(), document.getElementById(`hero-${id}`)?.scrollIntoView({ behavior: 'smooth' }))}>
              <HeroIcon id={id} size="sm" />
            </a>
          ))}
        </div>
      )}
      {empty && <Empty>Ничего не нашлось.</Empty>}
      {shown.general.length > 0 && (
        <section className="patch__sec">
          <h3 className="section-title">
            <Ti icon={Globe} />
            Общие изменения
          </h3>
          {shown.general.map((g, i) => (
            <div key={i} className="patch__general">
              {g.title && <h4>{g.title}</h4>}
              <ul>
                {g.notes.map((n, j) => (
                  <li key={j}>{n}</li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      )}
      {shown.heroes.length > 0 && (
        <section className="patch__sec">
          <h3 className="section-title">
            <Ti icon={Shield} />
            Герои
          </h3>
          <div className="patch__heroes">
            {shown.heroes.map((h) => (
              <HeroChanges key={h.id} h={h} mine={p.mine.includes(h.id)} />
            ))}
          </div>
        </section>
      )}
      {shown.items.length > 0 && (
        <section className="patch__sec">
          <h3 className="section-title">
            <Ti icon={Package} />
            Предметы
          </h3>
          <div className="patch__items">
            {shown.items.map((it) => (
              <div key={it.key} className="patch__item">
                <ItemIcon k={it.key} size={30} title={it.name} />
                <div>
                  <b>{it.name}</b>
                  <ul>
                    {it.notes.map((n, j) => (
                      <li key={j}>{n}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function HeroChanges({ h, mine }: { h: PatchHero; mine: boolean }) {
  const hero = useHeroes().data?.byId.get(h.id);
  const openHero = useUi((s) => s.openHero);
  return (
    <article id={`hero-${h.id}`} className={`patch__hero ${mine ? 'is-mine' : ''}`}>
      <button className="patch__herohead" onClick={() => openHero(h.id)} title="Страница героя">
        <HeroIcon id={h.id} size="sm" />
        {hero && <AttrIcon attr={hero.attr} size={14} />}
        <b>{h.name}</b>
        {mine && (
          <span className="pill">
            <Star size={11} strokeWidth={2.4} /> твой
          </span>
        )}
      </button>
      {h.notes.length > 0 && (
        <ul>
          {h.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
      {h.abilities.map((a) => (
        <div key={a.key} className="patch__ability">
          {a.icon ? <img src={asset(a.icon)} alt="" /> : <span className="patch__abicon" />}
          <div>
            <b>{a.name}</b>
            <ul>
              {a.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </div>
        </div>
      ))}
      {h.talents.length > 0 && (
        <div className="patch__ability">
          <TalentIcon size={26} />
          <div>
            <b>Таланты</b>
            <ul>
              {h.talents.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </article>
  );
}
