/**
 * Cards with depth: an element with the class .tilt leans towards the pointer and a glare follows
 * it (CSS: --rx, --ry, --gx, --gy; see .tilt in app.css). One listener for the whole app; off in
 * performance mode, with Windows' "reduce motion", and when the user turns it off
 * (Настройки → Оформление → «Карточки с объёмом»: html.no-tilt).
 */

/** Lean angles (degrees) for a pointer at (x, y) inside a w×h card: the side under the pointer
 * goes down, up to `max` at the edges. */
export function tiltAngles(x: number, y: number, w: number, h: number, max = 7): { rx: number; ry: number } {
  const nx = Math.min(1, Math.max(0, x / w)) * 2 - 1;
  const ny = Math.min(1, Math.max(0, y / h)) * 2 - 1;
  const r = (v: number) => +v.toFixed(2) || 0; // no -0
  return { rx: r(-ny * max), ry: r(nx * max) };
}

let current: HTMLElement | null = null;

function reset(el: HTMLElement) {
  el.classList.remove('is-tilting');
  el.style.removeProperty('--rx');
  el.style.removeProperty('--ry');
}

export function installTilt(): void {
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  document.addEventListener('pointermove', (e) => {
    const root = document.documentElement;
    const el = (e.target as HTMLElement | null)?.closest?.('.tilt') as HTMLElement | null;
    if (current && current !== el) reset(current);
    current = el;
    if (!el || e.pointerType === 'touch' || reduced.matches || root.classList.contains('perf') || root.classList.contains('no-tilt')) return;
    const r = el.getBoundingClientRect();
    const { rx, ry } = tiltAngles(e.clientX - r.left, e.clientY - r.top, r.width, r.height, Number(el.dataset.tilt) || 7);
    el.classList.add('is-tilting');
    el.style.setProperty('--rx', `${rx}deg`);
    el.style.setProperty('--ry', `${ry}deg`);
    el.style.setProperty('--gx', `${e.clientX - r.left}px`);
    el.style.setProperty('--gy', `${e.clientY - r.top}px`);
  });
  document.addEventListener('pointerleave', () => current && reset(current));
}
