/**
 * Compact window over the game. Draft mode: win chance, top picks for my position, bans and
 * quick hero entry. Build mode (auto once the match starts): items against the enemy draft.
 * Shares the draft with the main window through the backend session.
 */
import { getCurrentWindow } from '@tauri-apps/api/window';
import { useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useMemo, useState } from 'react';

import { api, waitForBackend } from '../api/client';
import { useBans, useBuild, useHeroes, useSettings, useSuggest } from '../api/hooks';
import type { DraftRequest } from '../api/types';
import { HeroSearch } from '../components/HeroSearch';
import { IconClose } from '../components/Icons';
import { AnimatedPercent, fmtPct, fmtSigned, HeroIcon, ItemIcon, Segmented, WinBar } from '../components/ui';
import { useEvaluate } from '../api/hooks';
import { onOverlayStatus, overlayStatus, setClickThrough, setOverlayEffect, showOverlay } from '../lib/overlay';
import { picked, useDraft } from '../state/draft';
import { startSync } from '../state/sync';
import { useUi } from '../state/ui';

export function OverlayApp() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [clickThrough, setCT] = useState(false);
  const [effectInUse, setEffectInUse] = useState<'acrylic' | 'tint'>('tint');
  const ov = useUi((s) => s.overlay);
  const theme = useUi((s) => s.theme);
  const phase = useDraft((s) => s.phase);
  const perf = ov.autoPerf && phase === 'game';

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

  const mode = ov.mode === 'auto' ? (phase === 'game' ? 'build' : 'draft') : ov.mode;
  return (
    <div className={`ov ov--${effectInUse} ${clickThrough ? 'is-through' : ''}`} style={{ opacity: ov.opacity }}>
      <OverlayHeader mode={mode} />
      {!ready ? (
        <div className="ov__body ov__center muted">{error ? `Бэкенд не отвечает: ${error}` : 'Подключаюсь к бэкенду…'}</div>
      ) : (
        <div className="ov__body">
          <DisplayWarning />
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={mode}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.22 }}
            >
              {mode === 'draft' ? <DraftMode /> : <BuildMode />}
            </motion.div>
          </AnimatePresence>
        </div>
      )}
      <footer className="ov__foot">
        {clickThrough ? (
          <span>Клики проходят в игру · {ov.interact} — управлять</span>
        ) : (
          <button className="ov__link" onClick={() => setClickThrough(true)}>
            Пропускать клики в игру ({ov.interact})
          </button>
        )}
        <span className="ov__grip" onPointerDown={() => getCurrentWindow().startResizeDragging('SouthEast')} title="Размер" />
      </footer>
    </div>
  );
}

function OverlayHeader({ mode }: { mode: 'draft' | 'build' }) {
  const ov = useUi((s) => s.overlay);
  const set = useUi((s) => s.set);
  return (
    <header className="ov__head" data-tauri-drag-region>
      <span className="ov__title" data-tauri-drag-region>
        <span className="titlebar__logo" /> Драфтер
      </span>
      <Segmented
        small
        value={ov.mode === 'auto' ? mode : ov.mode}
        onChange={(m) => set({ overlay: { ...ov, mode: m } })}
        options={[
          { value: 'draft', label: 'Драфт' },
          { value: 'build', label: 'Билд' },
        ]}
      />
      <input
        className="ov__opacity"
        type="range"
        min={0.35}
        max={1}
        step={0.05}
        value={ov.opacity}
        title={`Прозрачность ${Math.round(ov.opacity * 100)}%`}
        onChange={(e) => set({ overlay: { ...ov, opacity: Number(e.target.value) } })}
      />
      <button className="winbtn" title={`Скрыть (${ov.toggle})`} onClick={() => showOverlay(false)}>
        <IconClose />
      </button>
    </header>
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

function DraftMode() {
  const d = useDraft();
  const req = useDraftRequest();
  const ev = useEvaluate(req);
  const s = useSuggest(req);
  const bans = useBans(req);
  const heroes = useHeroes().data;
  const taken = new Set([...req.allies, ...req.enemies, ...req.bans]);
  const p = ev.data?.p_win ?? 0.5;
  return (
    <div className="ov__draft">
      <HeroSearch
        compact
        unavailable={taken}
        placeholder="Enter — союзник, Shift — враг, Alt — бан"
        onPick={(h, m) => d.placeIn(m.shift ? 'enemy' : m.alt ? 'ban' : 'ally', h.id)}
      />
      <div className="ov__win">
        <AnimatedPercent value={p} className={`ov__pct ${p >= 0.5 ? 'c-good' : 'c-bad'}`} />
        <WinBar p={p} />
      </div>
      <MiniTeam heroes={d.allies} team="ally" />
      <MiniTeam heroes={d.enemies} team="enemy" />
      <div className="ov__row">
        <span className="label">Позиция</span>
        <Segmented
          small
          value={req.pos!}
          onChange={(v) => d.setPos(v)}
          options={[1, 2, 3, 4, 5].map((v) => ({ value: v, label: String(v) }))}
        />
      </div>
      <ul className="ov__list">
        {s.data?.main.slice(0, 5).map((r) => {
          const why = r.terms.find((t) => t.kind !== 'hero') ?? r.terms[0];
          return (
            <motion.li layout="position" key={r.hero} onClick={() => d.placeIn('ally', r.hero)} title={`Взять: ${heroes?.byId.get(r.hero)?.name ?? ''}`}>
              <HeroIcon id={r.hero} size="sm" />
              <span className="ov__why">{why?.text.replace(/\s[+−-]?\d+(\.\d+)?%$/, '')}</span>
              <b className={r.delta >= 0 ? 'c-good' : 'c-bad'}>
                {fmtPct(r.p_win, 0)}
                <small>{fmtSigned(r.delta * 100)}</small>
              </b>
            </motion.li>
          );
        })}
      </ul>
      <div className="ov__bans">
        <span className="label">Банить</span>
        {bans.data?.bans.slice(0, 4).map((b) => (
          <span key={b.hero} onClick={() => d.placeIn('ban', b.hero)} title={`пикают ${fmtPct(b.pick_rate, 0)}`}>
            <HeroIcon id={b.hero} size="sm" />
          </span>
        ))}
      </div>
    </div>
  );
}

function MiniTeam({ heroes, team }: { heroes: (number | null)[]; team: 'ally' | 'enemy' }) {
  const clear = useDraft((s) => s.clear);
  return (
    <div className={`ov__team ov__team--${team}`}>
      {heroes.map((h, i) => (
        <span
          key={i}
          className="ov__slot"
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

function BuildMode() {
  const d = useDraft();
  const req = useDraftRequest();
  const allies = picked(d.allies);
  const [chosen, setChosen] = useState<number | null>(null);
  const hero = d.myHero ?? chosen ?? allies[0] ?? null;
  const build = useBuild(hero, req.pos ?? 1, req.enemies, true);
  if (!hero) return <p className="muted ov__center">Выбери своего героя в драфте — здесь появится билд против врагов.</p>;
  return (
    <div className="ov__build">
      {!d.myHero && allies.length > 1 && (
        <div className="ov__row ov__row--start">
          <span className="label">Мой герой</span>
          {allies.map((a) => (
            <span key={a} className={a === hero ? 'is-on' : ''} onClick={() => setChosen(a)}>
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
                <span className="label">
                  {b.approximate ? 'Популярные предметы (приблизительно)' : `${b.title} · ${b.games} игр · ${Math.round((b.wr ?? 0) * 100)}%`}
                </span>
                <div className="ov__items">
                  {b.boots && <ItemIcon k={b.boots.key} title={`${b.boots.name} ~${Math.round(b.boots.minute ?? 0)} мин`} size={30} />}
                  {b.core.map((it) => (
                    <ItemIcon key={it.key} k={it.key} title={`${it.name} ~${Math.round(it.minute ?? 0)} мин`} size={30} />
                  ))}
                </div>
              </>
            )}
            {build.data.vs.length > 0 && <span className="label">Против этого драфта</span>}
            <ul className="ov__vs">
              {build.data.vs.slice(0, 5).map((v) => (
                <li key={v.item} className={v.rare_on_hero ? 'is-rare' : ''}>
                  <ItemIcon k={v.item} title={v.name} size={26} />
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
