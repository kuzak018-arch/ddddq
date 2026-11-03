/** The widget windows over the game: small glass blocks at the minimap and the gold panel, shown in
 * a match. Clicks go through them into the game; while the overlay is open and managed (its
 * click-through off) they can be dragged and their buttons pressed. */
import { getCurrentWindow } from '@tauri-apps/api/window';
import { isTauri } from '@tauri-apps/api/core';
import { useEffect, useRef, useState } from 'react';
import { LogicalPosition, LogicalSize } from '@tauri-apps/api/dpi';

import { waitForBackend } from '../api/client';
import { useSettingsFromOtherWindow } from '../api/hooks';
import { useResolvedTheme } from '../lib/theme';
import { onWidgetsInteractive, placeOnce, showWidget, WIDGET_KINDS, widgetsInteractiveNow, type WidgetKind } from '../lib/widgets';
import { useDraft } from '../state/draft';
import { startSync } from '../state/sync';
import { useUi } from '../state/ui';
import { NeutralTierLine, ObjectivesRow, SkillNow, WinStrip } from './InGame';
import { Buyback, NextItem, NightLine, PaceLines, TimersRow, useBuildPlan, useGameLive } from './live';

export function WidgetApp({ kind }: { kind: WidgetKind }) {
  const [ready, setReady] = useState(false);
  const [edit, setEdit] = useState(false);
  const opacity = useUi((s) => s.overlay.opacity);
  const theme = useResolvedTheme(useUi((s) => s.theme));
  const box = useRef<HTMLDivElement>(null);
  useSettingsFromOtherWindow();
  useFitToContent(box);
  useEffect(() => {
    document.documentElement.classList.add('is-overlay', 'is-widget');
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    waitForBackend()
      .then(startSync)
      .then(() => setReady(true))
      .catch(() => {});
    void widgetsInteractiveNow().then(setEdit);
    void placeOnce(kind);
    // «Расставить заново» clears the saved place: it is put back the next time the widget shows
    const onShow = () => document.visibilityState === 'visible' && void placeOnce(kind);
    document.addEventListener('visibilitychange', onShow);
    const un = onWidgetsInteractive(setEdit);
    return () => {
      document.removeEventListener('visibilitychange', onShow);
      un();
    };
  }, [kind]);
  return (
    <div className={`wg wg--${kind} ${edit ? 'is-edit' : ''}`} style={{ opacity }}>
      <div
        ref={box}
        className="wg__box"
        onPointerDown={(e) => {
          // drag by any empty part of the box while managing (buttons keep their clicks)
          if (edit && isTauri() && !(e.target as HTMLElement).closest('button')) void getCurrentWindow().startDragging();
        }}
      >
        {edit && <span className="wg__edit">перетащи · {kind === 'timers' ? 'таймеры' : kind === 'now' ? 'сейчас' : 'золото'}</span>}
        {ready && (kind === 'timers' ? <TimersWidget /> : kind === 'now' ? <NowWidget /> : <GoldWidget />)}
      </div>
    </div>
  );
}

/** The window takes the content's height and grows upward: its bottom edge stays where it was
 * put (over the HUD's top), so a longer content never covers the minimap or the gold panel. */
function useFitToContent(box: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const el = box.current;
    if (!el || !isTauri()) return;
    const w = getCurrentWindow();
    let busy = false;
    let want = 0;
    const fit = async () => {
      if (busy) return;
      busy = true;
      try {
        while (want) {
          const h = want;
          want = 0;
          const [size, pos, f] = await Promise.all([w.innerSize(), w.outerPosition(), w.scaleFactor()]);
          const cur = size.height / f;
          if (Math.abs(cur - h) < 2) continue;
          const bottom = pos.y / f + cur;
          await w.setSize(new LogicalSize(size.width / f, h));
          await w.setPosition(new LogicalPosition(pos.x / f, Math.round(bottom - h)));
        }
      } finally {
        busy = false;
      }
    };
    const ro = new ResizeObserver(() => {
      want = Math.max(40, Math.ceil(el.getBoundingClientRect().height) + 8);
      void fit();
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [box]);
}

function TimersWidget() {
  const { hero, pos } = useBuildPlan();
  const g = useGameLive([], [], pos).data;
  if (!g?.live) return null;
  return (
    <>
      <TimersRow g={g} max={5} />
      {g.neutral_tier && <NeutralTierLine t={g.neutral_tier} hero={hero} pos={pos} held={g.live.neutral ?? null} />}
      {g.objectives && <ObjectivesRow o={g.objectives} />}
    </>
  );
}

function NowWidget() {
  const { req, me, hero, plan, skillOrder, ab, pos } = useBuildPlan();
  const phase = useDraft((s) => s.phase);
  const g = useGameLive(plan, skillOrder, pos).data;
  if (!g?.live) return null;
  return (
    <>
      {g.skill?.now && <SkillNow s={g.skill} order={skillOrder} ab={ab} />}
      <NightLine g={g} hero={hero} enemies={req.enemies} />
      <WinStrip req={req} me={me} inGame={phase === 'game'} />
    </>
  );
}

function GoldWidget() {
  const { plan, skillOrder, pos } = useBuildPlan();
  const g = useGameLive(plan, skillOrder, pos).data;
  if (!g?.live) return null;
  return (
    <>
      <NextItem g={g} plan={plan} size={30} />
      <Buyback g={g} />
      {g.pace && <PaceLines pace={g.pace} />}
    </>
  );
}

/** In the overlay page (always loaded, even hidden): shows the enabled widgets while a match runs. */
export function WidgetsController() {
  const phase = useDraft((s) => s.phase);
  const on = useUi((s) => s.overlay.widgets);
  const hints = useUi((s) => s.overlay.hints);
  useEffect(() => {
    for (const k of WIDGET_KINDS) void showWidget(k, phase === 'game' && hints && !!on?.[k]);
  }, [phase, on, hints]);
  useEffect(() => () => WIDGET_KINDS.forEach((k) => void showWidget(k, false)), []);
  return null;
}
