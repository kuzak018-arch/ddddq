/**
 * Mouse wheel scrolling that always works, and a hidden debug mode for it.
 *
 * In the installed app (WebView2) some scrolling areas did not move on the wheel while dragging
 * their scrollbar worked; the browser preview never showed it. As a safety net every wheel event
 * is watched: if the area under the cursor that can scroll that way has not moved a moment later,
 * we scroll it ourselves. An area that moved by itself is remembered and left to the browser.
 *
 * Ctrl+Alt+Shift+W turns on the debug mode: every wheel event goes to logs/ui-debug.log in the
 * user's data folder (%LOCALAPPDATA%\DotaDrafter\logs) with the element under the cursor, the area
 * that should scroll, whether it moved by itself and whether we scrolled it.
 */
import { api } from '../api/client';

const WAIT_MS = 350;
const LINE_PX = 40;

/**
 * Per scrolling area: 'native' — the engine scrolls it on the wheel (leave it alone); 'broken' —
 * it did not move on a wheel, we scroll it at once from then on. Unknown until the first wheel:
 * then we wait for its 'scroll' event (a slow but working engine still sends one) before acting.
 */
const state = new WeakMap<Element, 'native' | 'broken'>();
let debug = false;
let buffer: string[] = [];

function canScroll(el: Element, dy: number, dx: number): boolean {
  const cs = getComputedStyle(el);
  if (Math.abs(dy) >= Math.abs(dx)) {
    if (!/(auto|scroll|overlay)/.test(cs.overflowY) || el.scrollHeight <= el.clientHeight + 1) return false;
    return dy > 0 ? el.scrollTop + el.clientHeight < el.scrollHeight - 1 : el.scrollTop > 0;
  }
  if (!/(auto|scroll|overlay)/.test(cs.overflowX) || el.scrollWidth <= el.clientWidth + 1) return false;
  return dx > 0 ? el.scrollLeft + el.clientWidth < el.scrollWidth - 1 : el.scrollLeft > 0;
}

/** The nearest area under the element that can scroll in the wheel's direction. */
export function scrollerFor(start: Element | null, dy: number, dx: number): Element | null {
  for (let el = start; el && el !== document.documentElement; el = el.parentElement) {
    if (canScroll(el, dy, dx)) return el;
  }
  return null;
}

const describe = (el: Element | null) => {
  if (!el) return 'none';
  const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).slice(0, 3).join('.') : '';
  return `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''}`;
};
const path = (el: Element | null) => {
  const out: string[] = [];
  for (let e = el, i = 0; e && i < 5; e = e.parentElement, i++) out.push(describe(e));
  return out.join(' < ');
};

function log(line: string) {
  if (!debug) return;
  buffer.push(`${new Date().toISOString()} ${line}`);
}

function flush() {
  if (!buffer.length) return;
  const lines = buffer.splice(0, 400);
  void api('/debug/log', { body: { lines } }).catch(() => undefined);
}

function onWheel(e: WheelEvent) {
  if (e.ctrlKey) return; // zoom gesture
  const k = e.deltaMode === 1 ? LINE_PX : e.deltaMode === 2 ? window.innerHeight * 0.9 : 1;
  const dy = e.deltaY * k;
  const dx = e.deltaX * k;
  const target = e.target instanceof Element ? e.target : null;
  const sc = scrollerFor(target, dy, dx);
  const atPoint = document.elementFromPoint(e.clientX, e.clientY);
  if (!sc) {
    log(`wheel dy=${Math.round(dy)} target=${path(target)} point=${describe(atPoint)} scroller=none`);
    return;
  }
  const top0 = sc.scrollTop;
  const left0 = sc.scrollLeft;
  const cs = getComputedStyle(sc);
  const vertical = Math.abs(dy) >= Math.abs(dx);
  const scrollUs = () => sc.scrollBy({ top: vertical ? dy : 0, left: vertical ? 0 : dx });
  const report = (action: string) =>
    log(
      `wheel dy=${Math.round(dy)} mode=${e.deltaMode} target=${path(target)} point=${describe(atPoint)} ` +
        `scroller=${describe(sc)} top=${Math.round(top0)}→${Math.round(sc.scrollTop)} of ${sc.scrollHeight - sc.clientHeight} ` +
        `overflow=${cs.overflowY} overscroll=${cs.overscrollBehaviorY} ${action}`,
    );
  const known = state.get(sc);
  if (known === 'native') return report('native');
  if (known === 'broken') {
    scrollUs();
    const expected = sc.scrollTop;
    // the engine came back to life: it moved the area on top of us, stop helping
    setTimeout(() => {
      if (Math.abs(sc.scrollTop - expected) > Math.max(8, Math.abs(dy) * 0.5)) state.set(sc, 'native');
      report(state.get(sc) === 'native' ? 'fallback, engine works again' : 'fallback');
    }, WAIT_MS);
    return;
  }
  let scrolled = false;
  const onScroll = () => (scrolled = true);
  sc.addEventListener('scroll', onScroll, { passive: true });
  setTimeout(() => {
    sc.removeEventListener('scroll', onScroll);
    const moved = scrolled || sc.scrollTop !== top0 || sc.scrollLeft !== left0;
    if (moved) {
      state.set(sc, 'native');
      report('native (checked)');
    } else if (e.defaultPrevented) report('prevented');
    else {
      state.set(sc, 'broken');
      scrollUs();
      report('fallback (did not move by itself)');
    }
  }, WAIT_MS);
}

function toggleDebug(on: boolean) {
  debug = on;
  document.documentElement.classList.toggle('wheel-debug', on);
  if (on) {
    const s = window.screen;
    log(
      `debug on: ${navigator.userAgent} dpr=${window.devicePixelRatio} window=${window.innerWidth}x${window.innerHeight} ` +
        `screen=${s.width}x${s.height} ui=${localStorage.getItem('drafter-ui')?.slice(0, 600) ?? ''}`,
    );
    flush();
  } else log('debug off');
}

let installed = false;

export function installWheel() {
  if (installed) return;
  installed = true;
  window.addEventListener('wheel', onWheel, { passive: true, capture: true });
  window.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.altKey && e.shiftKey && e.code === 'KeyW') {
      e.preventDefault();
      toggleDebug(!debug);
    }
  });
  setInterval(flush, 2000);
}

export const wheelDebugOn = () => debug;
