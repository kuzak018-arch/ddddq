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
import { LayoutGrid } from '../components/glyphs';
import { onWidgetsInteractive, placeOnce, showWidget, WIDGET_KINDS, WIDGET_NAMES, WIDGET_SHORT, widgetOn, widgetsInteractiveNow, type WidgetKind } from '../lib/widgets';
import { useDraft } from '../state/draft';
import { startSync } from '../state/sync';
import { useUi } from '../state/ui';
import { BuybackHud, CreepsHud, GoldHud, NetworthHud, NeutralHud, NightHud, ObjectivesHud, TimersHud, WinBar } from './HudBits';
import { SkillAnnounce, useElapsed } from './InGame';
import { useBuildPlan, useGameLive } from './live';

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
        {edit && (
          <span className="wg__edit">
            перетащи · {WIDGET_SHORT[kind].toLowerCase()}
            <button
              className="wg__hide"
              title="Убрать этот виджет (вернуть: «Виджеты» в оверлее или в настройках)"
              onClick={() => {
                const ui = useUi.getState();
                ui.set({ overlay: { ...ui.overlay, widgets: { ...ui.overlay.widgets, [kind]: false } } });
              }}
            >
              ×
            </button>
          </span>
        )}
        {ready &&
          (kind === 'timers' ? <TimersWidget /> : kind === 'now' ? <NowWidget /> : kind === 'creeps' ? <CreepsWidget /> : kind === 'networth' ? <NetworthWidget /> : <GoldWidget />)}
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
  const q = useGameLive([], [], pos);
  const elapsed = useElapsed(q.dataUpdatedAt);
  const g = q.data;
  if (!g?.live) return null;
  return (
    <>
      <TimersHud g={g} max={6} elapsed={g.live.paused ? 0 : elapsed} />
      <div className="hud-line">
        {g.neutral_tier && <NeutralHud t={g.neutral_tier} hero={hero} pos={pos} held={g.live.neutral ?? null} />}
        {g.objectives && <ObjectivesHud o={g.objectives} />}
      </div>
    </>
  );
}

function NowWidget() {
  const { req, hero, plan, skillOrder, ab, pos } = useBuildPlan();
  const q = useGameLive(plan, skillOrder, pos);
  const elapsed = useElapsed(q.dataUpdatedAt);
  const g = q.data;
  if (!g?.live) return null;
  return (
    <>
      <SkillAnnounce s={g.skill} order={skillOrder} ab={ab} />
      <div className="hud-line">
        <WinBar req={req} />
        <NightHud g={g} me={hero} enemies={req.enemies} elapsed={g.live.paused ? 0 : elapsed} />
      </div>
    </>
  );
}

function GoldWidget() {
  const { plan, skillOrder, pos } = useBuildPlan();
  const g = useGameLive(plan, skillOrder, pos).data;
  if (!g?.live) return null;
  return (
    <>
      <GoldHud g={g} plan={plan} />
      <div className="hud-line">
        <BuybackHud g={g} />
      </div>
    </>
  );
}

/** Last hits now against what is usual on the hero at this minute (OpenDota benchmarks, pace.py). */
function CreepsWidget() {
  const { plan, skillOrder, pos } = useBuildPlan();
  const g = useGameLive(plan, skillOrder, pos).data;
  return g?.live && g.pace?.last_hits ? <CreepsHud lh={g.pace.last_hits} /> : null;
}

/** Net worth now against the top players of the hero at this minute (pace.py). */
function NetworthWidget() {
  const { plan, skillOrder, pos } = useBuildPlan();
  const g = useGameLive(plan, skillOrder, pos).data;
  return g?.live && g.pace?.networth ? <NetworthHud nw={g.pace.networth} /> : null;
}

/** The overlay's «Виджеты» button: turn each widget on or off right in the game. */
export function WidgetsMenu() {
  const [open, setOpen] = useState(false);
  const on = useUi((s) => s.overlay.widgets);
  const toggle = (k: WidgetKind) => {
    const ui = useUi.getState();
    ui.set({ overlay: { ...ui.overlay, widgets: { ...ui.overlay.widgets, [k]: !widgetOn(ui.overlay.widgets, k) } } });
  };
  return (
    <div className="ov-wmenu">
      <button className={`ov-round ${open ? 'is-on' : ''}`} title="Виджеты поверх игры: добавить или убрать" aria-expanded={open} onClick={() => setOpen(!open)}>
        <LayoutGrid size={15} />
      </button>
      {open && (
        <div className="ov-wmenu__list" role="menu">
          <span className="ov-wmenu__title">Виджеты в матче</span>
          {WIDGET_KINDS.map((k) => (
            <label key={k} className="ov-wmenu__row" title={WIDGET_NAMES[k]}>
              <input type="checkbox" checked={widgetOn(on, k)} onChange={() => toggle(k)} />
              {WIDGET_SHORT[k]}
            </label>
          ))}
          <span className="ov-wmenu__hint">Передвинуть: выключи сквозные клики и тяни виджет мышью.</span>
        </div>
      )}
    </div>
  );
}

/** In the overlay page (always loaded, even hidden): shows the enabled widgets while a match runs. */
export function WidgetsController() {
  const phase = useDraft((s) => s.phase);
  const on = useUi((s) => s.overlay.widgets);
  const hints = useUi((s) => s.overlay.hints);
  useEffect(() => {
    for (const k of WIDGET_KINDS) void showWidget(k, phase === 'game' && hints && widgetOn(on, k));
  }, [phase, on, hints]);
  useEffect(() => () => WIDGET_KINDS.forEach((k) => void showWidget(k, false)), []);
  return null;
}
