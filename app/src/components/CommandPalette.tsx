/**
 * One search for the whole app (Ctrl+K or the magnifier in the top bar): heroes (Enter opens the
 * overview, the buttons its build and top players' games), a player by Friend ID or a profile link,
 * and every tab and view by name. Arrows move, Enter opens, Esc closes.
 */
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { asset } from '../api/client';
import { useHeroes } from '../api/hooks';
import type { Hero } from '../api/types';
import { DEMO, DEMO_PAGES } from '../demo/api';
import { normalize, searchHeroes } from '../lib/search';
import { useNav, type ProfileTab } from '../state/nav';
import { useUi, type Page } from '../state/ui';
import { AttrIcon } from './DotaIcons';
import {
  ChartColumnIncreasing, ChartLine, Gamepad2, Hammer, LayoutGrid, Palette, ScanEye, ScrollText, Search, Settings, Shield, Skull, Swords,
  Trophy, User, UserSearch, type LucideIcon,
} from './glyphs';
import { Ti } from './Icons';
import { loadRecent } from './PlayerSearch';

interface Place {
  label: string;
  where: string;
  icon: LucideIcon;
  page: Page;
  tab?: ProfileTab;
  words?: string;
}

const PLACES: Place[] = [
  { label: 'Драфт', where: 'вкладка', icon: Swords, page: 'draft', words: 'пики баны советы' },
  { label: 'Герой — обзор', where: 'Герои', icon: Shield, page: 'hero', words: 'матчапы способности контрпики' },
  { label: 'Билд', where: 'Герои', icon: Hammer, page: 'builds', words: 'предметы сборка линия' },
  { label: 'Игры топов', where: 'Герои', icon: Trophy, page: 'top', words: 'иммортал про матчи' },
  { label: 'Тир-лист', where: 'Мета', icon: ChartColumnIncreasing, page: 'meta', words: 'мета винрейт пикрейт' },
  { label: 'Патчи', where: 'Мета', icon: ScrollText, page: 'patches', words: 'патчноуты изменения' },
  { label: 'Статистика', where: 'Профиль', icon: ChartLine, page: 'profile', tab: 'stats', words: 'профиль' },
  { label: 'Матчи', where: 'Профиль', icon: Gamepad2, page: 'profile', tab: 'history', words: 'история игры оценки stratz' },
  { label: 'Кто заруинил', where: 'Профиль', icon: Skull, page: 'profile', tab: 'ruin', words: 'разбор матча' },
  { label: 'Пул героев', where: 'Профиль', icon: LayoutGrid, page: 'profile', tab: 'pool', words: 'мои герои' },
  { label: 'Найти игрока', where: 'Профиль', icon: UserSearch, page: 'profile', tab: 'search', words: 'friend id steam dotabuff' },
  { label: 'Оформление', where: 'кнопка справа', icon: Palette, page: 'grids', words: 'сетки героев фон шрифт vpk' },
  { label: 'Настройки', where: 'кнопка справа', icon: Settings, page: 'settings', words: 'аккаунт оверлей виджеты обновления' },
  { label: 'Распознавание экрана', where: 'Настройки', icon: ScanEye, page: 'vision', words: 'захват драфт по экрану' },
];

/** A Friend ID, a Steam ID64 or a link to a profile. */
export const looksLikePlayer = (q: string) => /^\s*\d{5,20}\s*$/.test(q) || /steamcommunity|dotabuff|stratz|opendota/i.test(q);

interface Row {
  key: string;
  icon: ReactNode;
  label: ReactNode;
  sub?: ReactNode;
  run: () => void;
  extra?: { label: ReactNode; title: string; run: () => void }[];
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && !e.altKey && e.code === 'KeyK') {
        e.preventDefault();
        e.stopPropagation();
        setOpen((o) => !o);
      }
    };
    const onAsk = () => setOpen(true);
    window.addEventListener('keydown', onKey, true); // capture: search fields stop their keys from bubbling
    window.addEventListener('drafter:search', onAsk);
    return () => {
      window.removeEventListener('keydown', onKey, true);
      window.removeEventListener('drafter:search', onAsk);
    };
  }, []);
  return createPortal(<AnimatePresence>{open && <SearchBox onClose={() => setOpen(false)} />}</AnimatePresence>, document.body);
}

/** Opens the search from a button. */
export const openSearch = () => window.dispatchEvent(new Event('drafter:search'));

function SearchBox({ onClose }: { onClose: () => void }) {
  const heroes = useHeroes().data?.heroes ?? [];
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  useEffect(() => input.current?.focus(), []);

  const rows = useMemo(() => {
    const ui = useUi.getState();
    const done = (f: () => void) => () => {
      f();
      onClose();
    };
    const openPlace = (p: Place) =>
      done(() => {
        if (p.tab) useNav.getState().set({ profileTab: p.tab });
        ui.go(p.page);
      });
    const lookUp = (v: string) =>
      done(() => {
        useNav.getState().set({ profileTab: 'search', playerQuery: v });
        ui.go('profile');
      });
    const heroRow = (h: Hero): Row => ({
      key: `h${h.id}`,
      icon: <img className="cmdk__hero" src={asset(h.icon)} alt="" />,
      label: (
        <>
          <AttrIcon attr={h.attr} size={14} /> {h.name}
        </>
      ),
      sub: h.ru[0],
      run: done(() => ui.openHero(h.id)),
      extra: [
        { label: <><Ti icon={Hammer} />Билд</>, title: 'Билд на моей позиции', run: done(() => ui.openBuild(h.id)) },
        ...(DEMO ? [] : [{ label: <><Ti icon={Trophy} />Топы</>, title: 'Игры топов на этом герое', run: done(() => (ui.pickHero(h.id), ui.go('top'))) }]),
      ],
    });
    const places = PLACES.filter((p) => !DEMO || DEMO_PAGES.includes(p.page));
    const placeRow = (p: Place): Row => ({ key: `p${p.label}`, icon: <Ti icon={p.icon} />, label: p.label, sub: p.where, run: openPlace(p) });
    const out: { title: string; rows: Row[] }[] = [];
    const t = normalize(q);
    if (!t) {
      const recent = DEMO ? [] : loadRecent().slice(0, 4);
      if (recent.length)
        out.push({
          title: 'Недавние игроки',
          rows: recent.map((r) => ({ key: `r${r.q}`, icon: <Ti icon={User} />, label: r.name ?? r.q, sub: r.q, run: lookUp(r.q) })),
        });
      out.push({ title: 'Разделы', rows: places.map(placeRow) });
      return out;
    }
    if (!DEMO && looksLikePlayer(q))
      out.push({ title: 'Игрок', rows: [{ key: 'player', icon: <Ti icon={UserSearch} />, label: `Найти игрока «${q.trim()}»`, sub: 'Профиль → Найти игрока', run: lookUp(q.trim()) }] });
    const hs = searchHeroes(heroes, q, 7);
    if (hs.length) out.push({ title: 'Герои', rows: hs.map(heroRow) });
    const ps = places.filter((p) => normalize(`${p.label} ${p.where} ${p.words ?? ''}`).includes(t));
    if (ps.length) out.push({ title: 'Разделы', rows: ps.map(placeRow) });
    return out;
  }, [q, heroes, onClose]);
  const flat = rows.flatMap((g) => g.rows);
  const cur = Math.min(active, Math.max(0, flat.length - 1));

  useEffect(() => {
    list.current?.querySelector<HTMLElement>('.is-active')?.scrollIntoView({ block: 'nearest' });
  }, [cur]);

  let i = -1;
  return (
    <motion.div
      className="sheet cmdk"
      onPointerDown={(e) => e.target === e.currentTarget && onClose()}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.14 }}
    >
      <motion.div
        className="cmdk__card glass glass--strong"
        role="dialog"
        aria-modal
        aria-label="Поиск"
        initial={{ y: -10, opacity: 0, scale: 0.98 }}
        animate={{ y: 0, opacity: 1, scale: 1 }}
        exit={{ y: -6, opacity: 0 }}
        transition={{ type: 'spring', stiffness: 380, damping: 32 }}
      >
        <div className="cmdk__field">
          <Ti icon={Search} className="cmdk__lead" />
          <input
            ref={input}
            value={q}
            spellCheck={false}
            placeholder={DEMO ? 'Герой или раздел…' : 'Герой, игрок (Friend ID, ссылка) или раздел…'}
            onChange={(e) => {
              setQ(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                setActive(Math.min(cur + 1, flat.length - 1));
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setActive(Math.max(cur - 1, 0));
              } else if (e.key === 'Enter') {
                e.preventDefault();
                flat[cur]?.run();
              } else if (e.key === 'Escape') {
                e.preventDefault();
                onClose();
              }
              e.stopPropagation();
            }}
          />
          <kbd className="cmdk__kbd">Esc</kbd>
        </div>
        <ul className="cmdk__list" ref={list}>
          {!flat.length && <li className="cmdk__none muted">Ничего не нашлось</li>}
          {rows.map((g) => (
            <li key={g.title} className="cmdk__group">
              <span className="cmdk__title">{g.title}</span>
              <ul>
                {g.rows.map((r) => {
                  i += 1;
                  const n = i;
                  return (
                    <li
                      key={r.key}
                      className={`cmdk__row ${n === cur ? 'is-active' : ''}`}
                      onMouseMove={() => n !== cur && setActive(n)}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        r.run();
                      }}
                    >
                      <span className="cmdk__icon">{r.icon}</span>
                      <span className="cmdk__label">{r.label}</span>
                      {r.sub && <span className="cmdk__sub muted small">{r.sub}</span>}
                      {r.extra?.map((x) => (
                        <button
                          key={x.title}
                          className="btn btn--sm btn--ghost cmdk__act"
                          title={x.title}
                          onMouseDown={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            x.run();
                          }}
                        >
                          {x.label}
                        </button>
                      ))}
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
        <div className="cmdk__foot muted small">
          <span><kbd>↑</kbd><kbd>↓</kbd> выбрать</span>
          <span><kbd>Enter</kbd> открыть</span>
          <span><kbd>Ctrl</kbd>+<kbd>K</kbd> из любого места</span>
        </div>
      </motion.div>
    </motion.div>
  );
}
