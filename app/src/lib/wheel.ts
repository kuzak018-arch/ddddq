/**
 * Hidden debug mode for mouse-wheel scrolling (the settings column would not scroll with the wheel
 * in the installed app, and the browser preview never showed it).
 *
 * Off, it does nothing: no wheel listener at all. Ctrl+Alt+Shift+W turns it on, and from then on
 * logs/ui-debug.log in the user's data folder (%LOCALAPPDATA%\DotaDrafter\logs) gets:
 *  * every wheel event: the element it was sent to, the element under the cursor, every area of
 *    its ancestors that can scroll with their positions, and the same positions 300 ms later
 *    (the engine may scroll before this listener runs, so compare with the previous wheel line);
 *  * every scroll that happened anywhere (which element, from where to where);
 *  * once a second, which element the pointer is over — so a log with pointer lines but no wheel
 *    lines means the wheel never reached the page.
 * Listeners are passive and never scroll anything themselves.
 */
import { api } from '../api/client';

let debug = false;
let buffer: string[] = [];
let lastPointer = 0;

const describe = (el: Element | null) => {
  if (!el) return 'none';
  const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).slice(0, 3).join('.') : '';
  return `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''}`;
};
const path = (el: Element | null, n = 6) => {
  const out: string[] = [];
  for (let e = el, i = 0; e && i < n; e = e.parentElement, i++) out.push(describe(e));
  return out.join(' < ');
};

/** Ancestors that can scroll at all (either way), with their positions. */
function scrollers(start: Element | null): Element[] {
  const out: Element[] = [];
  for (let el = start; el; el = el.parentElement) {
    const cs = getComputedStyle(el);
    const y = /(auto|scroll|overlay)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight;
    const x = /(auto|scroll|overlay)/.test(cs.overflowX) && el.scrollWidth > el.clientWidth;
    if (y || x || el === document.scrollingElement) out.push(el);
  }
  return out;
}

const pos = (el: Element) => `${describe(el)} y=${Math.round(el.scrollTop)}/${el.scrollHeight - el.clientHeight} x=${Math.round(el.scrollLeft)}/${el.scrollWidth - el.clientWidth}`;

function log(line: string) {
  buffer.push(`${new Date().toISOString()} ${line}`);
}

function flush() {
  if (!buffer.length) return;
  const lines = buffer.splice(0, 400);
  void api('/debug/log', { body: { lines } }).catch(() => undefined);
}

function onWheel(e: WheelEvent) {
  const target = e.target instanceof Element ? e.target : null;
  const at = document.elementFromPoint(e.clientX, e.clientY);
  const chain = scrollers(target);
  log(
    `wheel dy=${e.deltaY} dx=${e.deltaX} mode=${e.deltaMode} ctrl=${e.ctrlKey} at=(${e.clientX},${e.clientY}) ` +
      `cancelable=${e.cancelable} target=${path(target)} point=${path(at, 3)} chain=[${chain.map(pos).join(' | ')}]`,
  );
  setTimeout(() => log(`  300ms later: defaultPrevented=${e.defaultPrevented} chain=[${chain.map(pos).join(' | ')}]`), 300);
}

function onScroll(e: Event) {
  const el = e.target instanceof Element ? e.target : document.scrollingElement;
  if (el) log(`scroll ${pos(el)}`);
}

function onPointer(e: PointerEvent) {
  const now = Date.now();
  if (now - lastPointer < 1000) return;
  lastPointer = now;
  log(`pointer at=(${e.clientX},${e.clientY}) over=${path(document.elementFromPoint(e.clientX, e.clientY), 4)}`);
}

/** The column that would not scroll: its size and every style that could matter. */
function snapshot() {
  const col = document.querySelector('.settings-scroll');
  if (!col) return 'settings column not open';
  const cs = getComputedStyle(col);
  const layered = [...col.querySelectorAll('*')].filter((el) => {
    const c = getComputedStyle(el);
    return c.backdropFilter !== 'none' || c.transform !== 'none' || c.animationName !== 'none' || c.maskImage !== 'none' || /(auto|scroll)/.test(c.overflowY);
  });
  return (
    `settings column ${col.clientWidth}x${col.clientHeight} content=${col.scrollHeight} overflowY=${cs.overflowY} ` +
    `overscroll=${cs.overscrollBehaviorY} layered children=${layered.length} [${layered.slice(0, 8).map((el) => describe(el)).join(', ')}]`
  );
}

function toggleDebug(on: boolean) {
  debug = on;
  document.documentElement.classList.toggle('wheel-debug', on);
  const opts = { passive: true, capture: true } as const;
  if (on) {
    window.addEventListener('wheel', onWheel, opts);
    document.addEventListener('scroll', onScroll, opts);
    window.addEventListener('pointermove', onPointer, opts);
    const s = window.screen;
    log(
      `debug on: ${navigator.userAgent} dpr=${window.devicePixelRatio} window=${window.innerWidth}x${window.innerHeight} ` +
        `screen=${s.width}x${s.height} page=${document.documentElement.className} ui=${localStorage.getItem('drafter-ui')?.slice(0, 600) ?? ''}`,
    );
    log(snapshot());
    flush();
  } else {
    window.removeEventListener('wheel', onWheel, opts);
    document.removeEventListener('scroll', onScroll, opts);
    window.removeEventListener('pointermove', onPointer, opts);
    log('debug off');
    flush();
  }
}

let installed = false;

export function installWheelDebug() {
  if (installed) return;
  installed = true;
  window.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.altKey && e.shiftKey && e.code === 'KeyW') {
      e.preventDefault();
      toggleDebug(!debug);
    }
  });
  setInterval(() => debug && flush(), 2000);
}

export const wheelDebugOn = () => debug;
