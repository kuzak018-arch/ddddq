/**
 * Page switch animations (Настройки → Оформление → «Переход между вкладками»). Only the glass
 * panels animate, never the page wrapper (see App.tsx): a transform or opacity on the wrapper would
 * cut the panels off from the wallpaper blur for the whole transition.
 */
import type { Page } from '../state/ui';

export type PageAnim = 'none' | 'fade' | 'rise' | 'slide' | 'zoom' | 'blur';

export const PAGE_ANIMS: { value: PageAnim; label: string; title: string }[] = [
  { value: 'none', label: 'Нет', title: 'Вкладка сменяется сразу' },
  { value: 'fade', label: 'Затухание', title: 'Старая вкладка тает, новая проявляется' },
  { value: 'rise', label: 'Подъём', title: 'Панели проявляются, чуть поднимаясь, одна за другой' },
  { value: 'slide', label: 'Слайд', title: 'Вкладки сдвигаются в сторону перехода, как страницы' },
  { value: 'zoom', label: 'Глубина', title: 'Старая вкладка уходит вперёд, новая приближается из глубины (на слабом ПК может подтормаживать)' },
  { value: 'blur', label: 'Фокус', title: 'Новая вкладка наводится на резкость из размытия (на слабом ПК может подтормаживать)' },
];

/** How long the page being left stays on screen (ms): its panels animate out meanwhile. */
export const LEAVE_MS: Record<PageAnim, number> = { none: 0, fade: 220, rise: 220, slide: 300, zoom: 260, blur: 260 };

/** Tab order of the top bar; builds sit under «Герои», the screen reader under the settings. */
const ORDER: Page[] = ['draft', 'meta', 'hero', 'top', 'grids', 'profile', 'settings'];
const place = (p: Page) => ORDER.indexOf(p === 'builds' ? 'hero' : p === 'vision' ? 'settings' : p);

/** Which way a slide goes: to a tab further right the new page comes in from the right. */
export function slideDir(from: Page | null, to: Page): 'fwd' | 'back' {
  if (!from) return 'fwd';
  const a = place(from);
  const b = place(to);
  return b < a || (b === a && to === 'hero' && from === 'builds') ? 'back' : 'fwd';
}

/** Plays the current page's entrance again, so a newly picked animation can be seen at once. */
export function replayPageIn(): void {
  const el = document.querySelector<HTMLElement>('.app__main > .page--in');
  if (!el) return;
  el.classList.remove('page--in');
  void el.offsetWidth; // restart the CSS animations
  el.classList.add('page--in');
}
