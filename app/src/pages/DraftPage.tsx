/**
 * The draft. Top: «Мы» and «Враги» at the sides (portrait and position on every row, bans and ban
 * advice at the bottom), the win chance ring with the main reasons between them. Below: the best
 * picks for my position and, at the right, the lane and the build against this draft.
 */
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { useBans, useBuild, useEvaluate, useHeroes, useSettings, useSuggest } from '../api/hooks';
import type { DraftRequest, Suggestion, Term } from '../api/types';
import { Panel } from '../components/Glass';
import { HeroSearch, type HeroSearchHandle } from '../components/HeroSearch';
import { IconReset } from '../components/Icons';
import { LaneCard, LaneView } from '../components/LaneView';
import { Sheet } from '../components/Sheet';
import { Tip } from '../components/Tip';
import { AnimatedPercent, ErrorBox, fmtPct, fmtSigned, HeroIcon, ItemIcon, Loading, TermLine } from '../components/ui';
import { assignPositions } from '../lib/positions';
import { MAX_BANS, picked, useDraft, type Slot } from '../state/draft';
import { useUi } from '../state/ui';

const POS_LABEL = ['', 'Керри', 'Мид', 'Оффлейн', 'Роумер', 'Саппорт'];
const MAIN_REASONS = 4;

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
  const suggest = useSuggest(req);
  const me = useMyHero(pos);
  const top = suggest.data?.main[0]?.hero ?? null;
  const topName = useHeroName(top);
  const forHero = me ?? top; // the lane and the build: my hero, or the best pick while I have none
  const when = !me && top ? `если возьмёшь ${topName}` : undefined;

  useDraftHotkeys(search);

  return (
    <div className="dr">
      <div className="dr__top">
        <TeamPanel team="ally" pos={pos} />
        <WinPanel req={req} search={search} taken={taken} />
        <TeamPanel team="enemy" pos={pos} req={req} />
      </div>
      <div className="dr__bottom">
        <PicksPanel req={req} comfort={comfort} onComfort={d.setComfort} suggest={suggest} />
        <div className="dr__side">
          <LanePanel hero={forHero} pos={pos} enemies={req.enemies} when={when} />
          <VsPanel hero={forHero} pos={pos} enemies={req.enemies} when={when} />
        </div>
      </div>
    </div>
  );
}

function useHeroName(id: number | null) {
  return useHeroes().data?.byId.get(id ?? -1)?.name ?? '';
}

/** Positions of a team's five slots (my position goes to my hero, or to the next pick I make). */
function useTeamPositions(team: 'ally' | 'enemy', pos: number) {
  const heroes = useHeroes().data;
  const d = useDraft();
  const slots = team === 'ally' ? d.allies : d.enemies;
  const myHero = team === 'ally' ? (d.myHero ?? d.myPick) : null;
  return useMemo(
    () =>
      assignPositions(slots, (h) => heroes?.byId.get(h)?.positions, {
        mine: team === 'ally' ? pos : undefined,
        fixed: myHero && slots.includes(myHero) ? { hero: myHero, pos } : null,
      }),
    [slots, heroes, team, pos, myHero],
  );
}

/** My hero: the one GSI reported, the ally I marked, or the ally that plays my position. */
function useMyHero(pos: number): number | null {
  const d = useDraft();
  const positions = useTeamPositions('ally', pos);
  if (d.myHero && d.allies.includes(d.myHero)) return d.myHero;
  if (d.myPick && d.allies.includes(d.myPick)) return d.myPick;
  const i = positions.indexOf(pos);
  return i >= 0 ? (d.allies[i] ?? null) : null;
}

function TeamPanel({ team, pos, req }: { team: 'ally' | 'enemy'; pos: number; req?: DraftRequest }) {
  const d = useDraft();
  const openHero = useUi((s) => s.openHero);
  const heroes = useHeroes().data;
  const slots = team === 'ally' ? d.allies : d.enemies;
  const positions = useTeamPositions(team, pos);
  const me = useMyHero(pos);
  const side = team === 'ally' ? d.side : d.side === 'radiant' ? 'dire' : d.side === 'dire' ? 'radiant' : null;
  const cycleSide = () => d.setSide(d.side === null ? 'radiant' : d.side === 'radiant' ? 'dire' : null);
  return (
    <Panel className={`dr-team dr-team--${team}`} refracting>
      <div className="dr-team__head">
        <span className={`kicker ${team === 'ally' ? 'c-radiant' : 'c-dire'}`}>{team === 'ally' ? 'Мы' : 'Враги'}</span>
        <button className="dr-side" onClick={cycleSide} title="Сторона: нажми, чтобы сменить (Radiant / Dire / не знаю)">
          {side === 'radiant' ? 'Radiant' : side === 'dire' ? 'Dire' : 'сторона ?'}
        </button>
      </div>
      <div className="dr-team__rows">
        {slots.map((h, i) => {
          const focus = d.focus.team === team && d.focus.index === i;
          const p = positions[i] ?? 0;
          const mine = team === 'ally' && (h ? h === me : p === pos && !me);
          return (
            <button
              key={i}
              className={`dr-row ${focus ? 'is-focus' : ''} ${h ? 'is-filled' : ''} ${mine ? 'is-mine' : ''}`}
              onClick={() => d.setFocus({ team, index: i })}
              onDoubleClick={() => h && openHero(h)}
              onContextMenu={(e) => {
                e.preventDefault();
                d.clear({ team, index: i });
              }}
              title={
                h
                  ? 'Двойной клик — страница героя, правый клик — убрать'
                  : `Слот ${i + 1}: клавиша ${team === 'ally' ? i + 1 : `Shift+${i + 1}`}`
              }
            >
              <AnimatePresence mode="popLayout" initial={false}>
                {h ? (
                  <motion.span
                    key={h}
                    className="dr-row__icon"
                    initial={{ scale: 0.8, opacity: 0, filter: 'blur(6px)' }}
                    animate={{ scale: 1, opacity: 1, filter: 'blur(0px)' }}
                    exit={{ scale: 0.85, opacity: 0, filter: 'blur(4px)' }}
                    transition={{ type: 'spring', stiffness: 330, damping: 26, mass: 0.9 }}
                  >
                    <HeroIcon id={h} size="md" />
                  </motion.span>
                ) : (
                  <span key="empty" className="dr-row__empty" />
                )}
              </AnimatePresence>
              <span className="dr-row__text">
                <b>{h ? (heroes?.byId.get(h)?.name ?? '…') : 'Выбирается…'}</b>
                <small title={POS_LABEL[p]}>
                  pos {p}
                  {mine && ' · ты'}
                </small>
              </span>
              {team === 'ally' && h && h !== d.myHero && (
                <span
                  role="button"
                  className={`dr-row__me ${h === me ? 'is-on' : ''}`}
                  title={h === me ? 'Это мой герой' : 'Отметить как моего героя'}
                  onClick={(e) => {
                    e.stopPropagation();
                    d.setMyPick(h === d.myPick ? null : h);
                  }}
                >
                  я
                </span>
              )}
            </button>
          );
        })}
      </div>
      {team === 'ally' ? <BanRow /> : req && <BanAdvice req={req} />}
    </Panel>
  );
}

function BanRow() {
  const { bans, focus, setFocus, clear } = useDraft();
  const heroes = useHeroes().data;
  const isFocus = focus.team === 'ban';
  return (
    <div className={`dr-bans ${isFocus ? 'is-focus' : ''}`} onClick={() => setFocus({ team: 'ban', index: 0 })} title="Клавиша B — вводить баны">
      <span className="dr-bans__label">
        Баны <small className="muted">{bans.length}/{MAX_BANS}</small>
      </span>
      {bans.length === 0 && <span className="muted small">кликни и вводи героев</span>}
      {bans.map((h, i) => (
        <span
          key={h}
          className="ban-pill"
          title="Правый клик — убрать"
          onContextMenu={(e) => {
            e.preventDefault();
            e.stopPropagation();
            clear({ team: 'ban', index: i });
          }}
        >
          <HeroIcon id={h} size="xs" />
          <s>{heroes?.byId.get(h)?.name}</s>
        </span>
      ))}
    </div>
  );
}

/** Whom to ban: the heroes most harmful to us right now, one click puts them into the bans. */
function BanAdvice({ req }: { req: DraftRequest }) {
  const bans = useBans(req);
  const { placeIn } = useDraft();
  const heroes = useHeroes().data;
  return (
    <div className="dr-bans dr-bans--advice">
      <span className="dr-bans__label">Кого банить</span>
      {bans.isPending && <Loading inline>Считаю…</Loading>}
      {bans.data?.bans.slice(0, 4).map((b) => (
        <button
          key={b.hero}
          className="ban-pill ban-pill--advice"
          onClick={() => placeIn('ban', b.hero)}
          title={`пикают ${fmtPct(b.pick_rate, 0)}, вред ${fmtSigned((1 / (1 + Math.exp(-b.harm)) - 0.5) * 100)}%\n${b.terms.map((t) => t.text).join('\n')}`}
        >
          <HeroIcon id={b.hero} size="xs" />
          <span>{heroes?.byId.get(b.hero)?.name}</span>
        </button>
      ))}
    </div>
  );
}

function WinPanel({ req, search, taken }: { req: DraftRequest; search: React.RefObject<HeroSearchHandle | null>; taken: Set<number> }) {
  const d = useDraft();
  const ev = useEvaluate(req);
  const p = ev.data?.p_win ?? 0.5;
  const empty = !req.allies.length && !req.enemies.length;
  const [all, setAll] = useState(false);
  const terms = ev.data?.terms.filter((t) => Math.abs(t.pct) >= 0.15) ?? [];
  return (
    <Panel className="dr-win" refracting>
      <div className="dr-win__search">
        <HeroSearch
          ref={search}
          unavailable={taken}
          hint="/"
          placeholder="Герой: «ам», «пудж», «вр»…"
          onPick={(h, m) => (m.shift ? d.placeIn('enemy', h.id) : m.alt ? d.placeIn('ban', h.id) : d.place(h.id))}
        />
        <button className="btn btn--icon" onClick={d.reset} title="Очистить драфт (Ctrl+Backspace)" aria-label="Очистить драфт">
          <IconReset />
        </button>
      </div>
      <Ring p={p} />
      {ev.error && <ErrorBox error={ev.error} />}
      {empty ? (
        <p className="muted small dr-win__empty">
          Добавь героев: Enter — в выбранный слот, Shift+Enter — врагам, Alt+Enter — в баны. Здесь появится разбор.
        </p>
      ) : (
        <div className="dr-reasons">
          {terms.slice(0, all ? undefined : MAIN_REASONS).map((t, i) => (
            <TermLine key={i} t={t} />
          ))}
          {terms.length > MAIN_REASONS && (
            <button className="dr-reasons__more" onClick={() => setAll((v) => !v)}>
              {all ? 'Свернуть' : `Все причины (${terms.length})`}
            </button>
          )}
        </div>
      )}
    </Panel>
  );
}

/** The win chance as a ring: green is us, red the enemy, the number in the middle. */
function Ring({ p }: { p: number }) {
  const r = 70;
  const c = 2 * Math.PI * r;
  return (
    <div className="ring" title={`Шанс на победу ${fmtPct(p)}`}>
      <svg viewBox="0 0 170 170" aria-hidden>
        <circle className="ring__bad" cx="85" cy="85" r={r} />
        <motion.circle
          className="ring__good"
          cx="85"
          cy="85"
          r={r}
          strokeDasharray={c}
          initial={false}
          animate={{ strokeDashoffset: c * (1 - p) }}
          transition={{ type: 'spring', stiffness: 120, damping: 22 }}
        />
      </svg>
      <div className="ring__text">
        <AnimatedPercent value={p} className="ring__num" digits={0} />
        <span>шанс на победу</span>
      </div>
    </div>
  );
}

function PicksPanel({ req, comfort, onComfort, suggest: s }: {
  req: DraftRequest;
  comfort: boolean;
  onComfort: (v: boolean) => void;
  suggest: ReturnType<typeof useSuggest>;
}) {
  const { placeIn } = useDraft();
  const full = req.allies.length >= 5;
  const [offrole, setOffrole] = useState(false);
  return (
    <Panel className="dr-picks" refracting>
      <div className="panel__head">
        <h2>Кого взять на pos {req.pos}</h2>
        <label className="check" title="Твой опыт на героях сдвигает оценку (вес — в настройках)">
          <input type="checkbox" checked={comfort} onChange={(e) => onComfort(e.target.checked)} />
          учитывать мой пул
        </label>
      </div>
      {s.error && <ErrorBox error={s.error} />}
      {full ? (
        <p className="muted">Твоя команда собрана.</p>
      ) : s.isPending ? (
        <Loading>Подбираю героев…</Loading>
      ) : (
        <>
          <div className="pick-grid">
            <AnimatePresence initial={false}>
              {s.data?.main.map((r) => <PickCard key={r.hero} r={r} onPick={() => placeIn('ally', r.hero)} />)}
            </AnimatePresence>
          </div>
          {!!s.data?.offrole.length && (
            <>
              <button className="dr-reasons__more" onClick={() => setOffrole((v) => !v)}>
                {offrole ? 'Скрыть нестандартные' : `Нестандартные на эту позицию (${s.data.offrole.length})`}
              </button>
              {offrole && (
                <div className="pick-grid pick-grid--small">
                  {s.data.offrole.map((r) => (
                    <PickCard key={r.hero} r={r} onPick={() => placeIn('ally', r.hero)} />
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </Panel>
  );
}

function PickCard({ r, onPick }: { r: Suggestion; onPick: () => void }) {
  const openHero = useUi((s) => s.openHero);
  const name = useHeroName(r.hero);
  const reason = mainReason(r.terms, name);
  return (
    <motion.div
      layout="position"
      className="pick"
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.18 } }}
      transition={{ type: 'spring', stiffness: 220, damping: 30, mass: 1 }}
    >
      <Tip
        content={
          <div className="pick-tip">
            <b>{name}</b>
            <span className="muted">
              мета {fmtPct(r.meta_wr)} · на позиции {fmtPct(r.pos_share, 0)} · пикают {fmtPct(r.pick_rate, 0)}
            </span>
            {r.specialist && <span className="warn">Высокий винрейт за счёт тех, кто на нём специализируется</span>}
            <ul className="terms terms--compact">
              {r.terms.slice(0, 5).map((t, i) => (
                <TermLine key={i} t={t} omit={r.hero} />
              ))}
            </ul>
          </div>
        }
      >
        <button className="pick__main" onClick={onPick} onDoubleClick={() => openHero(r.hero)} title="">
          <span className="pick__who">
            <HeroIcon id={r.hero} size="sm" />
            <b>{name}</b>
            {r.specialist && <span className="pill warn">спец.</span>}
          </span>
          <span className="pick__p">
            <span className="display">{fmtPct(r.p_win)}</span>
            <small className={r.delta >= 0 ? 'c-good' : 'c-bad'}>{fmtSigned(r.delta * 100)}</small>
          </span>
          <span className="pick__why">{reason}</span>
        </button>
      </Tip>
      <button className="pick__more" onClick={() => openHero(r.hero)} title="Страница героя">
        →
      </button>
    </motion.div>
  );
}

/** One short reason for a pick card: «Хорош против Anti-Mage», «Силён в мете», «Синергия с Lion». */
function mainReason(terms: Term[], name: string): string {
  const t = [...terms].sort((x, y) => y.pct - x.pct)[0];
  if (!t || t.pct <= 0) return t ? 'Без явных плюсов в этом драфте' : '';
  let s = t.text.replace(/\s*[+−-]\d+(?:[.,]\d+)?%$/, '');
  if (t.kind === 'hero') return 'Силён в мете';
  if (t.kind === 'synergy') {
    const pair = s.replace(/^синергия\s+/i, '').split(' + ');
    const other = pair.find((x) => x !== name);
    if (pair.length === 2 && other) return `Синергия с ${other}`;
  }
  if (name) s = s.split(name).join('');
  s = s.replace(/\s+/g, ' ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function LanePanel({ hero, pos, enemies, when }: { hero: number | null; pos: number; enemies: number[]; when?: string }) {
  const [open, setOpen] = useState(false);
  const name = useHeroName(hero);
  return (
    <Panel className="dr-lane" refracting>
      <LaneCard hero={hero} pos={pos} enemies={enemies} when={when} onMore={() => setOpen(true)} />
      <Sheet open={open} onClose={() => setOpen(false)} title={`Линия: ${name}`}>
        <LaneView hero={hero} pos={pos} enemies={enemies} />
      </Sheet>
    </Panel>
  );
}

/** Items against this draft for my hero (or the best pick): the item and why. */
function VsPanel({ hero, pos, enemies, when }: { hero: number | null; pos: number; enemies: number[]; when?: string }) {
  const build = useBuild(hero, pos, enemies, true);
  const openBuild = useUi((s) => s.openBuild);
  const vs = build.data?.vs ?? [];
  return (
    <Panel className="dr-vs" refracting>
      <div className="lane-card__head">
        <span className="kicker">Билд против драфта</span>
        {when && <span className="muted small">{when}</span>}
      </div>
      {!hero ? (
        <p className="muted small">Появится, когда будет твой герой или лучший пик.</p>
      ) : !enemies.length ? (
        <p className="muted small">Добавь врагов — подберу предметы против них.</p>
      ) : build.isPending ? (
        <Loading inline>Собираю…</Loading>
      ) : build.error ? (
        <ErrorBox error={build.error} />
      ) : (
        <ul className="vs-list">
          {vs.slice(0, 3).map((v) => (
            <li key={v.item}>
              <ItemIcon k={v.item} title={v.name} size={38} />
              <span>
                <b>{v.name}</b>
                <small className="muted">{v.reasons[0]?.text ?? ''}</small>
              </span>
            </li>
          ))}
          {!vs.length && <li className="muted small">Против этих врагов ничего особенного не нужно — обычный билд.</li>}
        </ul>
      )}
      {hero && (
        <button className="btn btn--sm" onClick={() => openBuild(hero, pos)}>
          Весь билд
        </button>
      )}
    </Panel>
  );
}

function useDraftHotkeys(search: React.RefObject<HeroSearchHandle | null>) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      const d = useDraft.getState();
      const digit = /^Digit([1-5])$/.exec(e.code);
      if (e.key === '/' || (e.ctrlKey && e.code === 'KeyK')) {
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
