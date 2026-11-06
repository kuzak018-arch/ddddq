/** The small widget windows over the game (Rust: overlay.rs WIDGETS). No-ops in a plain browser. */
import { invoke, isTauri } from '@tauri-apps/api/core';
import { LogicalPosition } from '@tauri-apps/api/dpi';
import { listen } from '@tauri-apps/api/event';
import { currentMonitor, getCurrentWindow } from '@tauri-apps/api/window';

export type WidgetKind = 'timers' | 'now' | 'gold' | 'creeps' | 'networth';
export const WIDGET_KINDS: WidgetKind[] = ['timers', 'now', 'gold', 'creeps', 'networth'];
export const WIDGET_NAMES: Record<WidgetKind, string> = {
  timers: 'Таймеры (над миникартой): руны, лотосы, ночь, тир нейтралок, Рошан и Терзатель',
  now: 'Сейчас (над таймерами): какой скилл качать, ночь для героев, шанс драфта',
  gold: 'Золото (справа снизу): следующий предмет, тайминг, выкуп',
  creeps: 'Крипы: добивания к этой минуте против обычного на твоём герое',
  networth: 'Нетворс: насколько ты впереди или позади топов на твоём герое к этой минуте',
};
/** Short names for the overlay's «Виджеты» menu. */
export const WIDGET_SHORT: Record<WidgetKind, string> = { timers: 'Таймеры', now: 'Сейчас', gold: 'Золото', creeps: 'Крипы', networth: 'Нетворс' };
/** On unless turned off: the widgets added later are on for those who never touched them. */
export const widgetOn = (on: Partial<Record<WidgetKind, boolean>> | undefined, k: WidgetKind) => on?.[k] ?? true;
// window sizes in overlay.rs build_widget (the content sits at the bottom of the window)
const SIZE: Record<WidgetKind, { w: number; h: number }> = {
  timers: { w: 270, h: 150 },
  now: { w: 270, h: 86 },
  gold: { w: 290, h: 150 },
  creeps: { w: 230, h: 80 },
  networth: { w: 230, h: 80 },
};
// Dota's HUD at its default scale: the minimap is about 27% of the screen height square in the
// bottom-left corner; the gold and the shop button are in the bottom-right, the same height
const HUD_BOTTOM = 0.27;
const GAP = 6;

export const widgetKind = (): WidgetKind | null => {
  const m = location.hash.match(/widget-(timers|now|gold|creeps|networth)/);
  return m ? (m[1] as WidgetKind) : null;
};

export const showWidget = (kind: WidgetKind, show: boolean) =>
  isTauri() ? invoke('widget_show', { label: `w-${kind}`, show }).catch(() => {}) : Promise.resolve();

export async function widgetsInteractiveNow(): Promise<boolean> {
  return isTauri() ? invoke<boolean>('widgets_interactive_now') : true;
}

export function onWidgetsInteractive(cb: (on: boolean) => void): () => void {
  if (!isTauri()) return () => {};
  const un = listen<boolean>('widgets-interactive', (e) => cb(e.payload));
  return () => void un.then((f) => f());
}

/** Where a widget goes on the monitor (logical px), at Dota's default HUD. */
export function defaultPlace(kind: WidgetKind, screen: { x: number; y: number; w: number; h: number }) {
  const hud = Math.round(screen.h * HUD_BOTTOM);
  const timersY = screen.y + screen.h - hud - SIZE.timers.h - GAP;
  if (kind === 'timers') return { x: screen.x + 8, y: timersY };
  if (kind === 'now') return { x: screen.x + 8, y: timersY - SIZE.now.h - GAP };
  // over the gold panel, above the «Золото» widget: net worth, then creeps above it
  const goldY = screen.y + screen.h - hud - SIZE.gold.h - GAP;
  if (kind === 'networth') return { x: screen.x + screen.w - SIZE.networth.w - 8, y: goldY - SIZE.networth.h - GAP };
  if (kind === 'creeps') return { x: screen.x + screen.w - SIZE.creeps.w - 8, y: goldY - SIZE.networth.h - SIZE.creeps.h - 2 * GAP };
  return { x: screen.x + screen.w - SIZE.gold.w - 8, y: screen.y + screen.h - hud - SIZE.gold.h - GAP };
}

/** The first time a widget opens it is put at its place over the HUD; later the saved position stays
 * (the window-state plugin keeps it after the user drags it). */
export async function placeOnce(kind: WidgetKind): Promise<void> {
  if (!isTauri()) return;
  const key = `drafter-widget-placed-${kind}`;
  try {
    if (localStorage.getItem(key)) return;
  } catch {
    return;
  }
  const m = await currentMonitor();
  if (!m) return;
  const f = m.scaleFactor;
  const p = defaultPlace(kind, { x: m.position.x / f, y: m.position.y / f, w: m.size.width / f, h: m.size.height / f });
  await getCurrentWindow().setPosition(new LogicalPosition(Math.round(p.x), Math.round(p.y)));
  try {
    localStorage.setItem(key, '1');
  } catch {
    /* private storage: placed again next time */
  }
}

/** «Расставить заново»: forget the saved places; each widget is put back at its default when shown. */
export function resetWidgetPlaces(): void {
  for (const k of WIDGET_KINDS) {
    try {
      localStorage.removeItem(`drafter-widget-placed-${k}`);
    } catch {
      /* ignore */
    }
  }
}
