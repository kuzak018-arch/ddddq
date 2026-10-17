import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { useBans, useEvaluate, useHeroes, useSettings, useSuggest } from '../api/hooks';
import type { DraftRequest, Suggestion } from '../api/types';
import { Panel } from '../components/Glass';
import { HeroSearch, type HeroSearchHandle } from '../components/HeroSearch';
import { IconReset } from '../components/Icons';
import { LaneView } from '../components/LaneView';
import { AnimatedPercent, ErrorBox, fmtPct, fmtSigned, HeroIcon, Segmented, TermLine, Toggle, WinBar } from '../components/ui';
import { MAX_BANS, picked, useDraft, type Slot } from '../state/draft';
import { useUi } from '../state/ui';

const POS_LABEL = ['', 'Керри', 'Мид', 'Оффлейн', 'Роумер', 'Саппорт'];

export function DraftPage() {
  const d = useDraft();
  const settings = useSettings().data;
  const search = useRef<HeroSearchHandle>(null);
  const pos = d.pos ?? settings?.pos ?? 1;
  const comfort = d.comfort ?? settings?.use_comfort ?? true;

  const req: DraftRequest = useMemo(
    () => ({ allies: picked(d.allies), enemies: picked(d.enemies), bans: d.bans, pos, side: d.side, use_comfort: comfort }),
    [d.allies, d.enemies, d.bans, pos, d.side, comfort],
  );
  const taken = useMemo(() => new Set([...req.allies, ...req.enemies, ...req.bans]), [req]);

  useDraftHotkeys(search);

  return (
    <div className="draft">
      <Panel className="draft__board" refracting>
        <div className="panel__head">
          <h2>Драфт</h2>
          <Segmented
            small
            value={d.side}
            onChange={d.setSide}
            options={[
              { value: null, label: 'Сторона ?' },
              { value: 'radiant', label: <span className="c-radiant">Radiant</span> },
              { value: 'dire', label: <span className="c-dire">Dire</span> },
            ]}
          />
          <button className="btn btn--icon" onClick={d.reset} title="Очистить драфт (Ctrl+Backspace)">
            <IconReset />
          </button>
        </div>
        <HeroSearch
          ref={search}
          unavailable={taken}
          hint="/"
          onPick={(h, m) => (m.shift ? d.placeIn('enemy', h.id) : m.alt ? d.placeIn('ban', h.id) : d.place(h.id))}
        />
        <p className="hint">Enter — в выбранный слот, Shift+Enter — врагам, Alt+Enter — в баны</p>

        <TeamRow title="Мои" team="ally" heroes={d.allies} />
        <TeamRow title="Враги" team="enemy" heroes={d.enemies} />
        <BanRow />

        <div className="draft__pos">
          <span className="label">Моя позиция</span>
          <Segmented
            value={pos}
            onChange={(p) => d.setPos(p)}
            options={[1, 2, 3, 4, 5].map((p) => ({ value: p, label: String(p), title: POS_LABEL[p] }))}
          />
        </div>
        <DraftLane pos={pos} />
      </Panel>

      <WinPanel req={req} />
      <SuggestPanel req={req} comfort={comfort} onComfort={d.setComfort} />
    </div>
  );
}

/** Lane matchup for my hero: the one GSI reported, or the ally I point at. */
function DraftLane({ pos }: { pos: number }) {
  const d = useDraft();
  const allies = picked(d.allies);
  const enemies = picked(d.enemies);
  const [mine, setMine] = useState<number | null>(null);
  const me = d.myHero ?? (mine && allies.includes(mine) ? mine : allies.length === 1 ? allies[0]! : null);
  return (
    <section className="draft__lane">
      <h3 className="section-title">Линия</h3>
      {!d.myHero && allies.length > 1 && (
        <div className="draft__me">
          <span className="label">Ты играешь на</span>
          {allies.map((h) => (
            <button key={h} className={`lane__opp ${h === me ? 'is-on' : ''}`} onClick={() => setMine(h)}>
              <HeroIcon id={h} size="sm" />
            </button>
          ))}
        </div>
      )}
      <LaneView hero={me} pos={pos} enemies={enemies} />
    </section>
  );
}

function TeamRow({ title, team, heroes }: { title: string; team: 'ally' | 'enemy'; heroes: (number | null)[] }) {
  const { focus, setFocus, clear } = useDraft();
  const openHero = useUi((s) => s.openHero);
  return (
    <section className={`team team--${team}`}>
      <h3>{title}</h3>
      <div className="team__slots">
        {heroes.map((h, i) => {
          const isFocus = focus.team === team && focus.index === i;
          return (
            <button
              key={i}
              className={`slot glass glass--inset ${isFocus ? 'is-focus' : ''} ${h ? 'is-filled' : ''}`}
              onClick={() => setFocus({ team, index: i })}
              onDoubleClick={() => h && openHero(h)}
              onContextMenu={(e) => {
                e.preventDefault();
                clear({ team, index: i });
              }}
              title={h ? 'Двойной клик — страница героя, правый клик — убрать' : `Слот ${i + 1}`}
            >
              <AnimatePresence mode="popLayout">
                {h ? (
                  <motion.span
                    key={h}
                    initial={{ scale: 0.8, opacity: 0, filter: 'blur(6px)' }}
                    animate={{ scale: 1, opacity: 1, filter: 'blur(0px)' }}
                    exit={{ scale: 0.85, opacity: 0, filter: 'blur(4px)' }}
                    transition={{ type: 'spring', stiffness: 330, damping: 26, mass: 0.9 }}
                  >
                    <HeroIcon id={h} size="md" />
                  </motion.span>
                ) : (
                  <span className="slot__num">{team === 'ally' ? i + 1 : `⇧${i + 1}`}</span>
                )}
              </AnimatePresence>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function BanRow() {
  const { bans, focus, setFocus, clear } = useDraft();
  const isFocus = focus.team === 'ban';
  return (
    <section className="team team--ban">
      <h3>
        Баны <span className="muted">{bans.length}/{MAX_BANS} · B</span>
      </h3>
      <div className={`bans glass glass--inset ${isFocus ? 'is-focus' : ''}`} onClick={() => setFocus({ team: 'ban', index: 0 })}>
        {bans.length === 0 && <span className="muted">кликни и вводи героев</span>}
        {bans.map((h, i) => (
          <span
            key={h}
            className="ban"
            title="Правый клик — убрать"
            onContextMenu={(e) => {
              e.preventDefault();
              e.stopPropagation();
              clear({ team: 'ban', index: i });
            }}
          >
            <HeroIcon id={h} size="sm" />
          </span>
        ))}
      </div>
    </section>
  );
}

function WinPanel({ req }: { req: DraftRequest }) {
  const ev = useEvaluate(req);
  const p = ev.data?.p_win ?? 0.5;
  const empty = !req.allies.length && !req.enemies.length;
  return (
    <Panel className="draft__win" refracting>
      <div className="panel__head">
        <h2>Шанс победы</h2>
        {req.side && <span className={`pill c-${req.side}`}>{req.side === 'radiant' ? 'Radiant' : 'Dire'}</span>}
      </div>
      <div className="win">
        <AnimatedPercent value={p} className={`win__num ${p >= 0.5 ? 'c-good' : 'c-bad'}`} />
        <WinBar p={p} big />
        <div className="win__legend">
          <span>Враги</span>
          <span>50%</span>
          <span>Мы</span>
        </div>
      </div>
      {ev.error && <ErrorBox error={ev.error} />}
      <h3 className="section-title">Почему</h3>
      {empty ? (
        <p className="muted">Добавь героев, и здесь появится разбор: сила героев в мете, синергии, кто кого контрит.</p>
      ) : (
        <ul className="terms">
          {ev.data?.terms.filter((t) => Math.abs(t.pct) >= 0.15).slice(0, 12).map((t, i) => <TermLine key={i} t={t} />)}
        </ul>
      )}
    </Panel>
  );
}

function SuggestPanel({ req, comfort, onComfort }: { req: DraftRequest; comfort: boolean; onComfort: (v: boolean) => void }) {
  const s = useSuggest(req);
  const bans = useBans(req);
  const { placeIn } = useDraft();
  const full = req.allies.length >= 5;
  return (
    <Panel className="draft__suggest" refracting>
      <div className="panel__head">
        <h2>Подбор · позиция {req.pos}</h2>
        <Toggle on={comfort} onChange={onComfort} label="мои комфортные" />
      </div>
      {s.error && <ErrorBox error={s.error} />}
      {full ? (
        <p className="muted">Твоя команда собрана.</p>
      ) : (
        <div className="suggest-list">
          <AnimatePresence initial={false}>
            {s.data?.main.map((r, i) => <SuggestCard key={r.hero} r={r} rank={i + 1} onPick={() => placeIn('ally', r.hero)} />)}
          </AnimatePresence>
          {!!s.data?.offrole.length && (
            <>
              <h3 className="section-title">Нестандартные на эту позицию</h3>
              <AnimatePresence initial={false}>
                {s.data.offrole.map((r) => <SuggestCard key={r.hero} r={r} onPick={() => placeIn('ally', r.hero)} />)}
              </AnimatePresence>
            </>
          )}
        </div>
      )}
      <h3 className="section-title">Кого банить</h3>
      <div className="ban-suggest">
        {bans.data?.bans.map((b) => (
          <button key={b.hero} className="ban-chip" onClick={() => placeIn('ban', b.hero)} title={b.terms.map((t) => t.text).join('\n')}>
            <HeroIcon id={b.hero} size="sm" />
            <span>
              пикают {fmtPct(b.pick_rate, 0)}, вред {fmtSigned((1 / (1 + Math.exp(-b.harm)) - 0.5) * 100)}%
            </span>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function SuggestCard({ r, rank, onPick }: { r: Suggestion; rank?: number; onPick: () => void }) {
  const openHero = useUi((s) => s.openHero);
  const [best, ...rest] = r.terms;
  return (
    <motion.div
      layout="position"
      className="suggest"
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.18 } }}
      transition={{ type: 'spring', stiffness: 220, damping: 30, mass: 1 }}
    >
      <button className="suggest__main" onClick={onPick} title="Взять в мою команду">
        {rank && <span className="suggest__rank">{rank}</span>}
        <HeroIcon id={r.hero} size="md" />
        <span className="suggest__name">
          <HeroName id={r.hero} />
          <span className="muted">
            мета {fmtPct(r.meta_wr)} · на позиции {fmtPct(r.pos_share, 0)}
            {r.specialist && <span className="warn" title="Высокий винрейт за счёт тех, кто на нём специализируется"> · специалисты</span>}
          </span>
        </span>
        <span className={`suggest__p ${r.delta >= 0 ? 'c-good' : 'c-bad'}`}>
          {fmtPct(r.p_win)}
          <small>{fmtSigned(r.delta * 100)}</small>
        </span>
      </button>
      <ul className="terms terms--compact">
        {[best, ...rest].filter(Boolean).slice(0, 3).map((t, i) => <TermLine key={i} t={t!} omit={r.hero} />)}
      </ul>
      <button className="suggest__more" onClick={() => openHero(r.hero)}>
        страница героя →
      </button>
    </motion.div>
  );
}

function HeroName({ id }: { id: number }) {
  const h = useHeroes().data?.byId.get(id);
  return <b>{h?.name ?? '…'}</b>;
}

function useDraftHotkeys(search: React.RefObject<HeroSearchHandle | null>) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      const d = useDraft.getState();
      const digit = /^Digit([1-5])$/.exec(e.code);
      if (e.key === '/') {
        e.preventDefault();
        search.current?.focus();
      } else if (digit && !e.ctrlKey && !e.altKey) {
        const slot: Slot = { team: e.shiftKey ? 'enemy' : 'ally', index: Number(digit[1]) - 1 };
        d.setFocus(slot);
        search.current?.focus();
        e.preventDefault();
      } else if (e.code === 'KeyB' && !e.ctrlKey) {
        d.setFocus({ team: 'ban', index: 0 });
        search.current?.focus();
        e.preventDefault();
      } else if ((e.key === 'Delete' || e.key === 'Backspace') && e.ctrlKey) {
        d.reset();
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (d.focus.team === 'ban') d.clear({ team: 'ban', index: d.bans.length - 1 });
        else d.clear(d.focus);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [search]);
}
