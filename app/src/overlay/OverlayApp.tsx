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
import { useEffect, useRef, useState } from 'react';

import { api, waitForBackend } from '../api/client';
import { useBans, useEvaluate, useHeroes, usePlan, useSettingsFromOtherWindow, useSuggest } from '../api/hooks';
import type { GamePlan, TopVs } from '../api/types';
import { Skills } from '../components/BuildView';
import { HeroSearch, type HeroSearchHandle } from '../components/HeroSearch';
import { NeutralItems } from '../components/NeutralItems';
import { EnemiesMode, WinStrip } from './InGame';
import { LiveHints, useBuildPlan, useDraftRequest, useMe } from './live';
import { WidgetsController } from './Widgets';
import { SteamGuideCompact } from '../components/SteamGuides';
import { IconClose } from '../components/Icons';
import { POS_ROLE } from '../components/DotaIcons';
import { LaneCard, LaneView } from '../components/LaneView';
import { fmtPct, fmtSigned, HeroIcon, HowTo, ItemIcon, plural } from '../components/ui';
import { onOverlayStatus, overlayStatus, setClickThrough, setOverlayEffect, showOverlay } from '../lib/overlay';
import { useResolvedTheme } from '../lib/theme';
import { useDraft } from '../state/draft';
import { startSync } from '../state/sync';
import { useUi } from '../state/ui';

type Mode = 'draft' | 'build' | 'lane' | 'plan' | 'enemies';
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
  const theme = useResolvedTheme(useUi((s) => s.theme));
  const phase = useDraft((s) => s.phase);
  const perf = ov.autoPerf && phase === 'game';
  const search = useRef<HeroSearchHandle>(null);
  useSettingsFromOtherWindow();
  const fullSize = useRef(FULL);

  useEffect(() => {
    document.documentElement.classList.add('is-overlay');
    document.documentElement.dataset.theme = theme;
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
  // (the tint follows the opacity slider once it stops moving: re-applying Acrylic makes it flash)
  useEffect(() => {
    const want = perf ? 'tint' : ov.effect;
    const t = setTimeout(() => void setOverlayEffect(want, 40 + ov.opacity * 80).then(setEffectInUse), 300);
    return () => clearTimeout(t);
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
        <WidgetsController />
      </div>
    );
  return (
    <div className={`ov ov--${effectInUse} ${clickThrough ? 'is-through' : ''}`} style={{ opacity: ov.opacity }}>
      <header className="ov__head" data-tauri-drag-region>
        <div className="ov-switch" role="tablist">
          {(['draft', 'build', 'lane', 'plan', 'enemies'] as Mode[]).map((m) => (
            <button key={m} role="tab" className={`ov-switch__btn ${shown === m ? 'is-on' : ''}`} onClick={() => setMode(m)}>
              {shown === m && <motion.span layoutId="ov-pill" className="ov-switch__pill" transition={{ type: 'spring', stiffness: 380, damping: 34 }} />}
              <span>{m === 'draft' ? 'Драфт' : m === 'build' ? 'Билд' : m === 'lane' ? 'Линия' : m === 'plan' ? 'План' : 'Враги'}</span>
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
          <WidgetsController />
          {shown !== 'draft' && <WinStripHere />}
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={shown}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.2 }}
            >
              {shown === 'draft' ? (
                <DraftMode search={search} />
              ) : shown === 'build' ? (
                <BuildMode />
              ) : shown === 'lane' ? (
                <LaneMode />
              ) : shown === 'plan' ? (
                <PlanMode />
              ) : (
                <EnemiesHere />
              )}
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

/** My hero: GSI knows it; otherwise the ally I clicked, or the only ally. */
function WinStripHere() {
  const req = useDraftRequest();
  const me = useMe(req);
  const phase = useDraft((s) => s.phase);
  return <WinStrip req={req} me={me} inGame={phase === 'game'} />;
}

function EnemiesHere() {
  const req = useDraftRequest();
  return <EnemiesMode enemies={req.enemies} />;
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
          onPick={(h, m) => {
            // into the empty slot the user clicked, else by the modifier (Shift — enemy, Alt — ban)
            const f = d.focus;
            const list = f.team === 'ally' ? d.allies : f.team === 'enemy' ? d.enemies : null;
            if (!m.shift && !m.alt && list && list[f.index] === null) d.place(h.id);
            else d.placeIn(m.shift ? 'enemy' : m.alt ? 'ban' : 'ally', h.id);
          }}
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
        <span className="kicker">Лучшие пики{req.pos ? ` · ${req.pos} ${POS_ROLE[req.pos]}` : ''}</span>
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

/** The build of top players (Divine+, Immortal, pros) from games where the enemy team had a draft
 * like this one (backend topgames.vs_draft). */
function TopVsBuild({ vs, title }: { vs: TopVs; title: React.ReactNode }) {
  const games = vs.games ?? 0;
  const who = Object.entries(vs.sources ?? {}).map(([label, n]) => `${label} ${n}`).join(' · ');
  const items = [...(vs.boots ? [vs.boots] : []), ...(vs.core ?? [])];
  return (
    <div className="ov__topvs">
      <span className="kicker">{title}</span>
      <p className="hint">
        {games} {plural(games, 'игра', 'игры', 'игр')}, {vs.wins ?? 0} {plural(vs.wins ?? 0, 'победа', 'победы', 'побед')}
        {vs.full ? ` · ${vs.full} с тем же драфтом` : ''} · {who}
      </p>
      <div className="ov__items">
        {items.map((it) => (
          <ItemIcon key={it.key} k={it.key} title={`${it.name} ~${Math.round(it.minute ?? 0)} мин · ${Math.round(it.share * 100)}% игр`} size={36} />
        ))}
      </div>
    </div>
  );
}

function BuildMode() {
  const { d, req, allies, hero, build, topVs, found, laneVs, shownVs, plan, skillOrder, at } = useBuildPlan();
  const hints = useUi((s) => s.overlay.hints);
  if (!hero) return <p className="muted ov__center">Выбери своего героя в драфте — здесь появится билд против врагов.</p>;
  return (
    <div className="ov__build">
      {d.phase === 'game' && hints && (
        <LiveHints
          plan={plan}
          pos={build.data?.build.pos ?? req.pos ?? 1}
          order={skillOrder}
          ab={build.data?.build.abilities ?? {}}
          hero={hero}
          enemies={req.enemies}
        />
      )}
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
            {found && <TopVsBuild vs={found} title="Игры топов против такого драфта" />}
            {laneVs && (
              <TopVsBuild
                vs={laneVs}
                title={
                  <>
                    Игры топов против твоей линии{' '}
                    {laneVs.lane.map((h) => (
                      <HeroIcon key={h} id={h} size="xs" />
                    ))}
                  </>
                }
              />
            )}
            {!shownVs && (topVs?.loading || topVs?.lane?.loading) && <p className="hint">Ищу игры топов против такого драфта…</p>}
            {b && (
              <>
                <span className="kicker">
                  {found ? 'Обычный билд героя' : b.approximate ? 'Популярные предметы (приблизительно)' : `${b.title} · ${b.games} игр · ${Math.round((b.wr ?? 0) * 100)}%`}
                </span>
                <div className="ov__items">
                  {b.boots && <ItemIcon k={b.boots.key} title={`${b.boots.name} ~${Math.round(at(b.boots.key, b.boots.minute))} мин`} size={found ? 26 : 34} />}
                  {b.core.map((it) => (
                    <ItemIcon key={it.key} k={it.key} title={`${it.name} ~${Math.round(at(it.key, it.minute))} мин`} size={found ? 26 : 34} />
                  ))}
                </div>
                {(b.skills.length > 0 || (b.skill_order?.length ?? 0) > 0) && (
                  <>
                    <span className="kicker">Прокачка</span>
                    <div className="ov__skills">
                      <Skills b={b} ab={r.abilities ?? {}} size={20} legend={false} />
                    </div>
                  </>
                )}
              </>
            )}
            {hero && <NeutralItems hero={hero} pos={r.pos} compact />}
            {hero && <SteamGuideCompact hero={hero} />}
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

const KILL: Record<'kill' | 'team' | 'avoid', { text: string; cls: string }> = {
  kill: { text: 'можно убить', cls: 'c-good' },
  team: { text: 'с командой', cls: 'muted' },
  avoid: { text: 'не трогай один', cls: 'c-bad' },
};

/** «План»: when we are strongest, how to play and how to finish this draft, whom my hero can kill. */
function PlanMode() {
  const d = useDraft();
  const req = useDraftRequest();
  const me = useMe(req);
  const plan = usePlan(req.allies, req.enemies, me, d.phase === 'game');
  const p = plan.data;
  if (!req.allies.length && !req.enemies.length) return <p className="muted ov__center">Заполни драфт — здесь появится план на игру.</p>;
  return (
    <div className="ov__plan">
      {plan.error && <p className="muted">{(plan.error as Error).message}</p>}
      {p?.timing && <TimingBar t={p.timing} />}
      {p?.tips.map((t, i) => (
        <p key={i} className={`ov__tip is-${t.kind}`}>
          {t.text}
        </p>
      ))}
      {me && p && p.kill.length > 0 && (
        <div className="ov__kill">
          <span className="kicker">
            Кого ловить{p.minute != null ? ` · ${Math.floor(p.minute)} мин` : ''}
          </span>
          {p.kill.map((k) => (
            <div key={k.hero} className="ov__kill-row">
              <HeroIcon id={k.hero} size="sm" />
              <b className={KILL[k.verdict].cls}>{KILL[k.verdict].text}</b>
              <span className="muted small">{k.reasons.join(', ')}</span>
            </div>
          ))}
        </div>
      )}
      {!me && req.allies.length > 0 && <p className="hint">Отметь своего героя (в «Билде» или кликом по союзнику) — появится, кого ловить.</p>}
      <HowTo>
        Окна — по винрейту героев в коротких и длинных играх, «кого ловить» — по контрпикам, живучести и побегу героев. Предметов и уровней
        в настоящей игре программа не видит.
      </HowTo>
    </div>
  );
}

/** Who is stronger in each part of the game: above the line — us. */
function TimingBar({ t }: { t: NonNullable<GamePlan['timing']> }) {
  const max = Math.max(0.03, ...t.diff.map(Math.abs));
  return (
    <div className="ov__timing">
      {t.diff.map((v, i) => (
        <div key={i} className={`ov__timing-col ${t.now === i ? 'is-now' : ''}`} title={`${t.buckets[i]}: ${v > 0 ? 'сильнее мы' : v < 0 ? 'сильнее враги' : 'ровно'}`}>
          <span className="ov__timing-bar">
            <i className={v >= 0 ? 'is-us' : 'is-them'} style={{ height: `${(Math.abs(v) / max) * 50}%` }} />
          </span>
          <span className="small muted">{t.buckets[i]}</span>
        </div>
      ))}
    </div>
  );
}
