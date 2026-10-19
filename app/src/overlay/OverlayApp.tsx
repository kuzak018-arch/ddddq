/**
 * Compact window over the game: one glass panel ~400px. On top a «Драфт / Билд / Линия» switch,
 * hero search (Ctrl+K), the draft in two rows of five portraits, the win bar, the lane line and the
 * top-5 picks; at the bottom the hotkey hint and whether the draft is read from the screen.
 * «Свернуть» turns it into a small pill: the best pick's portrait and the chances.
 * Build mode (auto once the match starts): items against the enemy draft. Lane mode: the lane.
 * Shares the draft with the main window through the backend session.
 */
import { useQuery } from '@tanstack/react-query';
import { LogicalSize } from '@tauri-apps/api/dpi';
import { isTauri } from '@tauri-apps/api/core';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { api, waitForBackend } from '../api/client';
import { useBans, useBuild, useEvaluate, useHeroes, useSettings, useSuggest } from '../api/hooks';
import type { DraftRequest } from '../api/types';
import { HeroSearch, type HeroSearchHandle } from '../components/HeroSearch';
import { IconClose } from '../components/Icons';
import { LaneCard, LaneView } from '../components/LaneView';
import { fmtPct, fmtSigned, HeroIcon, ItemIcon } from '../components/ui';
import { onOverlayStatus, overlayStatus, setClickThrough, setOverlayEffect, showOverlay } from '../lib/overlay';
import { picked, useDraft } from '../state/draft';
import { startSync } from '../state/sync';
import { useUi } from '../state/ui';

type Mode = 'draft' | 'build' | 'lane';
const FULL = { w: 400, h: 660 };
const PILL = { w: 320, h: 64 };

export function OverlayApp() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clickThrough, setCT] = useState(false);
  const [effectInUse, setEffectInUse] = useState<'acrylic' | 'tint'>('tint');
  const [collapsed, setCollapsed] = useState(false);
  const [mode, setMode] = useState<Mode | null>(null); // null: follow the setting (auto = build in a match)
  const ov = useUi((s) => s.overlay);
  const theme = useUi((s) => s.theme);
  const phase = useDraft((s) => s.phase);
  const perf = ov.autoPerf && phase === 'game';
  const search = useRef<HeroSearchHandle>(null);
  const fullSize = useRef(FULL);

  useEffect(() => {
    document.documentElement.classList.add('is-overlay');
    document.documentElement.dataset.theme = theme === 'light' ? 'light' : 'dark';
  }, [theme]);
  useEffect(() => {
    waitForBackend()
      .then(startSync)
      .then(() => setReady(true))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    overlayStatus().then((s) => setCT(s.click_through));
    return onOverlayStatus((s) => setCT(s.click_through));
  }, []);
  // Acrylic blurs the game behind the window; in a running match (or by choice) a plain tint is cheaper
  useEffect(() => {
    const want = perf ? 'tint' : ov.effect;
    setOverlayEffect(want, 40 + ov.opacity * 80).then(setEffectInUse);
  }, [ov.effect, ov.opacity, perf]);
  useEffect(() => {
    document.documentElement.classList.toggle('perf', perf);
  }, [perf]);
  // the window remembers its size: a pill size left from last time would squeeze the full panel
  useEffect(() => {
    if (!isTauri()) return;
    const w = getCurrentWindow();
    w.innerSize().then(async (s) => {
      const f = await w.scaleFactor();
      if (s.height / f < 300) await w.setSize(new LogicalSize(FULL.w, FULL.h));
    });
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.code === 'KeyK') {
        e.preventDefault();
        if (collapsed) void toggleCollapsed(false);
        setMode('draft');
        setTimeout(() => search.current?.focus(), 30);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  async function toggleCollapsed(on: boolean) {
    if (isTauri()) {
      const w = getCurrentWindow();
      if (on) {
        const s = await w.innerSize();
        const f = await w.scaleFactor();
        fullSize.current = { w: s.width / f, h: s.height / f };
        await w.setSize(new LogicalSize(PILL.w, PILL.h));
      } else {
        await w.setSize(new LogicalSize(fullSize.current.w, Math.max(fullSize.current.h, 420)));
      }
    }
    setCollapsed(on);
  }

  const auto: Mode = ov.mode === 'auto' ? (phase === 'game' ? 'build' : 'draft') : ov.mode;
  const shown = mode ?? auto;
  if (collapsed)
    return (
      <div className={`ov ov--${effectInUse} ov--pill ${clickThrough ? 'is-through' : ''}`} style={{ opacity: ov.opacity }}>
        {ready ? <Pill onOpen={() => toggleCollapsed(false)} /> : <span className="muted">Подключаюсь…</span>}
      </div>
    );
  return (
    <div className={`ov ov--${effectInUse} ${clickThrough ? 'is-through' : ''}`} style={{ opacity: ov.opacity }}>
      <header className="ov__head" data-tauri-drag-region>
        <div className="ov-switch" role="tablist">
          {(['draft', 'build', 'lane'] as Mode[]).map((m) => (
            <button key={m} role="tab" className={`ov-switch__btn ${shown === m ? 'is-on' : ''}`} onClick={() => setMode(m)}>
              {shown === m && <motion.span layoutId="ov-pill" className="ov-switch__pill" transition={{ type: 'spring', stiffness: 380, damping: 34 }} />}
              <span>{m === 'draft' ? 'Драфт' : m === 'build' ? 'Билд' : 'Линия'}</span>
            </button>
          ))}
        </div>
        <button
          className={`ov-round ${clickThrough ? 'is-on' : ''}`}
          title={clickThrough ? `Клики проходят в игру · ${ov.interact} — управлять` : `Пропускать клики в игру (${ov.interact})`}
          onClick={() => setClickThrough(!clickThrough)}
        >
          <CursorIcon />
        </button>
        <button className="ov-round" title="Свернуть в таблетку" onClick={() => toggleCollapsed(true)}>
          <span className="ov-round__min" />
        </button>
        <button className="ov-round" title={`Скрыть (${ov.toggle})`} onClick={() => showOverlay(false)}>
          <IconClose />
        </button>
      </header>
      {!ready ? (
        <div className="ov__body ov__center muted">{error ? `Бэкенд не отвечает: ${error}` : 'Подключаюсь к бэкенду…'}</div>
      ) : (
        <div className="ov__body">
          <DisplayWarning />
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={shown}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
            >
              {shown === 'draft' ? <DraftMode search={search} /> : shown === 'build' ? <BuildMode /> : <LaneMode />}
            </motion.div>
          </AnimatePresence>
        </div>
      )}
      <footer className="ov__foot">
        <span>{ov.toggle} — скрыть</span>
        <input
          className="ov__opacity"
          type="range"
          min={0.35}
          max={1}
          step={0.05}
          value={ov.opacity}
          title={`Прозрачность ${Math.round(ov.opacity * 100)}%`}
          aria-label="Прозрачность"
          onChange={(e) => useUi.getState().set({ overlay: { ...ov, opacity: Number(e.target.value) } })}
        />
        <ReadStatus />
        <span className="ov__grip" onPointerDown={() => getCurrentWindow().startResizeDragging('SouthEast')} title="Размер" />
      </footer>
    </div>
  );
}

function CursorIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden>
      <path d="M5 3l14 7-6 2-2 6z" />
    </svg>
  );
}

/** Whether the draft comes from the screen: «драфт распознан с экрана», waiting, or off. */
function ReadStatus() {
  const phase = useDraft((s) => s.phase);
  const st = useQuery({
    queryKey: ['vision-status-ov'],
    queryFn: () => api<{ enabled: boolean; cautious: boolean; running: boolean; last_read: number | null; locked: number }>('/vision/status'),
    refetchInterval: phase === 'draft' ? 4000 : 20000,
  }).data;
  let text = 'чтение экрана выкл.';
  let on = false;
  if (st?.enabled) {
    const fresh = st.last_read && Date.now() / 1000 - st.last_read < 15;
    if (phase === 'draft' && fresh) {
      text = 'драфт распознан с экрана';
      on = true;
    } else text = phase === 'draft' ? 'читаю экран…' : 'чтение экрана ждёт драфта';
    if (st.cautious) text += ' · учится';
  }
  return (
    <span className={`ov-status ${on ? 'is-on' : ''}`} title={
        st?.enabled
          ? `${st.cautious ? 'Учится: вписывает героя только при уверенности, после трёх одинаковых кадров. ' : ''}Исправленных вручную слотов: ${st.locked}`
          : 'Включается в настройках («Чтение драфта с экрана»)'
      }>
      <i />
      {text}
    </span>
  );
}

function DisplayWarning() {
  const d = useQuery({
    queryKey: ['dota-display'],
    queryFn: () => api<{ found: boolean; fullscreen?: boolean }>('/dota/display'),
    refetchInterval: 60_000,
  });
  if (!d.data?.found || !d.data.fullscreen) return null;
  return (
    <div className="ov__warn">
      Дота в полноэкранном режиме — оверлей поверх неё не виден. В игре: Настройки → Видео → Режим отображения →
      «Окно без рамки».
    </div>
  );
}

function useDraftRequest(): DraftRequest {
  const d = useDraft();
  const settings = useSettings().data;
  return useMemo(
    () => ({
      allies: picked(d.allies),
      enemies: picked(d.enemies),
      bans: d.bans,
      pos: d.pos ?? settings?.pos ?? 1,
      side: d.side,
      use_comfort: d.comfort ?? settings?.use_comfort ?? true,
    }),
    [d.allies, d.enemies, d.bans, d.pos, d.side, d.comfort, settings],
  );
}

/** My hero: GSI knows it; otherwise the ally I clicked, or the only ally. */
function useMe(req: DraftRequest) {
  const d = useDraft();
  if (d.myHero) return d.myHero;
  if (d.myPick && req.allies.includes(d.myPick)) return d.myPick;
  return req.allies.length === 1 ? req.allies[0]! : null;
}

function DraftMode({ search }: { search: React.RefObject<HeroSearchHandle | null> }) {
  const d = useDraft();
  const req = useDraftRequest();
  const ev = useEvaluate(req);
  const s = useSuggest(req);
  const bans = useBans(req);
  const heroes = useHeroes().data;
  const taken = new Set([...req.allies, ...req.enemies, ...req.bans]);
  const p = ev.data?.p_win ?? 0.5;
  const me = useMe(req);
  const top = s.data?.main[0]?.hero ?? null;
  const laneHero = me ?? top;
  const name = (h: number | null) => (h ? (heroes?.byId.get(h)?.name ?? '') : '');
  return (
    <div className="ov__draft">
      <div className="ov-search">
        <HeroSearch
          ref={search}
          compact
          unavailable={taken}
          placeholder="Герой: ам, пудж, вр…"
          onPick={(h, m) => d.placeIn(m.shift ? 'enemy' : m.alt ? 'ban' : 'ally', h.id)}
        />
        <kbd>Ctrl K</kbd>
      </div>
      <div className="ov-board">
        <MiniTeam heroes={d.allies} team="ally" mine={me} />
        <MiniTeam heroes={d.enemies} team="enemy" />
        <div className="ov-winbar">
          <b className="c-good">{fmtPct(p)}</b>
          <span className="ov-winbar__track">
            <motion.i className="is-us" animate={{ width: `${p * 100}%` }} transition={{ type: 'spring', stiffness: 120, damping: 22 }} />
          </span>
          <b className="c-bad">{fmtPct(1 - p)}</b>
        </div>
      </div>
      {req.enemies.length > 0 && laneHero && (
        <div className="ov-lanebox">
          <LaneCard hero={laneHero} pos={req.pos!} enemies={req.enemies} when={!me && top ? `если возьмёшь ${name(top)}` : undefined} />
        </div>
      )}
      <div className="ov-picks__head">
        <span className="kicker">Лучшие пики · pos {req.pos}</span>
        <span className="ov-pos">
          {[1, 2, 3, 4, 5].map((v) => (
            <button key={v} className={v === req.pos ? 'is-on' : ''} onClick={() => d.setPos(v)} title={`Моя позиция ${v}`}>
              {v}
            </button>
          ))}
        </span>
      </div>
      <ul className="ov__list">
        {s.data?.main.slice(0, 5).map((r, i) => {
          const why = r.terms.find((t) => t.kind === 'comfort') ?? r.terms.find((t) => t.kind !== 'hero') ?? r.terms[0];
          return (
            <motion.li
              layout="position"
              key={r.hero}
              className={i === 0 ? 'is-best' : ''}
              onClick={() => d.placeIn('ally', r.hero)}
              title={`Взять: ${name(r.hero)} (${fmtSigned(r.delta * 100)})`}
            >
              <HeroIcon id={r.hero} size="sm" />
              <span className="ov__who">
                <b>{name(r.hero)}</b>
                <small>{shortWhy(why?.text ?? '', name(r.hero))}</small>
              </span>
              <span className="ov__p">{fmtPct(r.p_win)}</span>
            </motion.li>
          );
        })}
      </ul>
      {!!bans.data?.bans.length && (
        <div className="ov__bans">
          <span className="label">Банить</span>
          {bans.data.bans.slice(0, 4).map((b) => (
            <span key={b.hero} onClick={() => d.placeIn('ban', b.hero)} title={`${name(b.hero)}: пикают ${fmtPct(b.pick_rate, 0)}`}>
              <HeroIcon id={b.hero} size="sm" />
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** «Lone Druid хорош против Anti-Mage +4.0%» → «хорош против Anti-Mage». */
function shortWhy(text: string, name: string): string {
  let s = text.replace(/\s*[+−-]?\d+(?:[.,]\d+)?%$/, '');
  if (name) s = s.split(name).join('').replace(/\s+/g, ' ').trim();
  return s.replace(/^синергия \+ /, 'синергия с ').replace(/^сила в мете$/, 'силён в мете');
}

function MiniTeam({ heroes, team, mine }: { heroes: (number | null)[]; team: 'ally' | 'enemy'; mine?: number | null }) {
  const { clear, myHero, setMyPick, setFocus } = useDraft();
  return (
    <div className={`ov__team ov__team--${team}`}>
      <span className="ov__team-label">{team === 'ally' ? 'Мы' : 'Враги'}</span>
      {heroes.map((h, i) => (
        <span
          key={i}
          className={`ov__slot ${h ? 'is-filled' : ''} ${h && h === mine ? 'is-me' : ''}`}
          title={
            h
              ? team === 'ally' && !myHero
                ? 'Клик — это мой герой (для линии), правый клик — убрать'
                : 'Правый клик — убрать'
              : `Слот ${i + 1}: клик — вводить сюда`
          }
          onClick={() => (h ? team === 'ally' && !myHero && setMyPick(h) : setFocus({ team, index: i }))}
          onContextMenu={(e) => {
            e.preventDefault();
            clear({ team, index: i });
          }}
        >
          {h ? <HeroIcon id={h} size="sm" /> : null}
        </span>
      ))}
    </div>
  );
}

/** The collapsed overlay: the best pick's portrait, its chance and ours. */
function Pill({ onOpen }: { onOpen: () => void }) {
  const req = useDraftRequest();
  const ev = useEvaluate(req);
  const s = useSuggest(req);
  const heroes = useHeroes().data;
  const best = s.data?.main[0];
  return (
    <button className="ov-pill" onClick={onOpen} title="Развернуть" data-tauri-drag-region>
      {best ? <HeroIcon id={best.hero} size="sm" /> : <span className="ov-pill__dot" />}
      <span>
        <b>{best ? `${heroes?.byId.get(best.hero)?.name ?? ''} ${fmtPct(best.p_win)}` : 'Драфтер'}</b>
        <small> · шансы {fmtPct(ev.data?.p_win ?? 0.5, 0)}</small>
      </span>
    </button>
  );
}

function LaneMode() {
  const req = useDraftRequest();
  const me = useMe(req);
  const s = useSuggest(req);
  const hero = me ?? s.data?.main[0]?.hero ?? null;
  if (!hero) return <p className="muted ov__center">Возьми своего героя — здесь появится линия.</p>;
  return (
    <div className="ov__lane-mode">
      <LaneView hero={hero} pos={req.pos ?? 1} enemies={req.enemies} />
    </div>
  );
}

function BuildMode() {
  const d = useDraft();
  const req = useDraftRequest();
  const allies = picked(d.allies);
  const me = useMe(req);
  const hero = me ?? allies[0] ?? null;
  const build = useBuild(hero, req.pos ?? 1, req.enemies, true);
  if (!hero) return <p className="muted ov__center">Выбери своего героя в драфте — здесь появится билд против врагов.</p>;
  return (
    <div className="ov__build">
      {!d.myHero && allies.length > 1 && (
        <div className="ov__row ov__row--start">
          <span className="label">Мой герой</span>
          {allies.map((a) => (
            <span key={a} className={a === hero ? 'is-on' : ''} onClick={() => d.setMyPick(a)}>
              <HeroIcon id={a} size="sm" />
            </span>
          ))}
        </div>
      )}
      {build.error && <p className="muted">{(build.error as Error).message}</p>}
      {build.data && (() => {
        const r = build.data.build;
        const b = r.builds[0] ?? r.approximate;
        return (
          <>
            {r.requested_pos && (
              <p className="hint">
                На позиции {r.requested_pos} этого героя почти не играют — билд для позиции {r.pos}.
              </p>
            )}
            {r.status === 'loading' && <p className="hint">Загружаю матчи: {r.progress.have} из {r.target}…</p>}
            {b && (
              <>
                <span className="kicker">
                  {b.approximate ? 'Популярные предметы (приблизительно)' : `${b.title} · ${b.games} игр · ${Math.round((b.wr ?? 0) * 100)}%`}
                </span>
                <div className="ov__items">
                  {b.boots && <ItemIcon k={b.boots.key} title={`${b.boots.name} ~${Math.round(b.boots.minute ?? 0)} мин`} size={34} />}
                  {b.core.map((it) => (
                    <ItemIcon key={it.key} k={it.key} title={`${it.name} ~${Math.round(it.minute ?? 0)} мин`} size={34} />
                  ))}
                </div>
              </>
            )}
            {build.data.vs.length > 0 && <span className="kicker">Против этого драфта</span>}
            <ul className="ov__vs">
              {build.data.vs.slice(0, 5).map((v) => (
                <li key={v.item} className={v.rare_on_hero ? 'is-rare' : ''}>
                  <ItemIcon k={v.item} title={v.name} size={30} />
                  <span>
                    <b>{v.name}</b> {v.reasons[0]?.text}
                  </span>
                </li>
              ))}
            </ul>
          </>
        );
      })()}
    </div>
  );
}
