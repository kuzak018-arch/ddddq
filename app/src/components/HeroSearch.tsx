import { AnimatePresence, motion } from 'motion/react';
import { forwardRef, useImperativeHandle, useMemo, useRef, useState } from 'react';

import { asset } from '../api/client';
import { useHeroes } from '../api/hooks';
import type { Hero } from '../api/types';
import { searchHeroes } from '../lib/search';
import { IconSearch } from './Icons';

export interface HeroSearchHandle {
  focus: () => void;
}

interface Props {
  placeholder?: string;
  /** Heroes that can't be picked (already taken / banned): shown dimmed, skipped by Enter. */
  unavailable?: Set<number>;
  onPick: (hero: Hero, mods: { shift: boolean; alt: boolean }) => void;
  hint?: string;
  compact?: boolean;
}

export const HeroSearch = forwardRef<HeroSearchHandle, Props>(function HeroSearch(
  { placeholder = 'Герой: «ам», «пудж», «вр»…', unavailable, onPick, hint, compact },
  ref,
) {
  const heroes = useHeroes().data?.heroes ?? [];
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useImperativeHandle(ref, () => ({ focus: () => input.current?.focus() }));

  const results = useMemo(() => searchHeroes(heroes, q, 10), [heroes, q]);
  const pickable = (h: Hero) => !unavailable?.has(h.id);

  const pick = (h: Hero | undefined, mods = { shift: false, alt: false }) => {
    if (!h || !pickable(h)) return;
    onPick(h, mods);
    setQ('');
    setActive(0);
  };

  return (
    <div className={`hero-search ${compact ? 'hero-search--compact' : ''}`}>
      <div className="hero-search__field glass glass--inset">
        <IconSearch />
        <input
          ref={input}
          value={q}
          placeholder={placeholder}
          spellCheck={false}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, results.length - 1));
            } else if (e.key === 'ArrowUp') {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === 'Enter') {
              e.preventDefault();
              const first = results.slice(active).find(pickable) ?? results.find(pickable);
              pick(first, { shift: e.shiftKey, alt: e.altKey });
            } else if (e.key === 'Escape') {
              setQ('');
              input.current?.blur();
            }
            e.stopPropagation();
          }}
        />
        {hint && !q && <kbd className="hero-search__kbd">{hint}</kbd>}
      </div>
      <AnimatePresence>
        {open && q && (
          <motion.div
            className="hero-search__list glass glass--strong"
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32, mass: 0.8 }}
            style={{ transformOrigin: 'top center' }}
          >
            <ul className="hero-search__scroll">
            {results.length === 0 && <li className="hero-search__none">Ничего не нашлось</li>}
            {results.map((h, i) => (
              <li
                key={h.id}
                className={`hero-search__row ${i === active ? 'is-active' : ''} ${pickable(h) ? '' : 'is-taken'}`}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(h, { shift: e.shiftKey, alt: e.altKey });
                }}
              >
                <img src={asset(h.icon)} alt="" />
                <span className="hero-search__name">{h.name}</span>
                <span className="hero-search__ru">{h.ru[0]}</span>
                {!pickable(h) && <span className="hero-search__tag">занят</span>}
              </li>
            ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});
