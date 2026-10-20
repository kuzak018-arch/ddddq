import { useEffect, useRef, useState } from 'react';

import { waitForBackend } from './api/client';
import { TitleBar, useCalmBackground, Wallpaper } from './components/Chrome';
import { Effects } from './components/Effects';
import { Panel } from './components/Glass';
import { Onboarding } from './components/Onboarding';
import { refractionSupported } from './glass/refraction';
import { BuildsPage } from './pages/BuildsPage';
import { DraftPage } from './pages/DraftPage';
import { GridsPage } from './pages/GridsPage';
import { HeroPage } from './pages/HeroPage';
import { MetaPage } from './pages/MetaPage';
import { ProfilePage } from './pages/ProfilePage';
import { SettingsPage } from './pages/SettingsPage';
import { TopGamesPage } from './pages/TopGamesPage';
import { VisionPage } from './pages/VisionPage';
import { useAppIcon } from './lib/appIcon';
import { LEAVE_MS, slideDir } from './lib/pageAnim';
import { useCloseToTray } from './lib/tray';
import { applyHotkeys, showOverlay } from './lib/overlay';
import { useDraft } from './state/draft';
import { startSync } from './state/sync';
import { useUi, type Page } from './state/ui';

const PAGES: Record<Page, () => React.JSX.Element> = {
  draft: DraftPage,
  meta: MetaPage,
  hero: HeroPage,
  builds: BuildsPage,
  top: TopGamesPage,
  grids: GridsPage,
  profile: ProfilePage,
  settings: SettingsPage,
  vision: VisionPage,
};
const ORDER: Page[] = ['draft', 'meta', 'hero', 'top', 'grids', 'profile', 'settings'];

function useAppearance() {
  const { theme, refraction, tilt } = useUi();
  const calm = useCalmBackground(); // performance mode or a running match: no blur, no animations
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: light)');
    const apply = () => {
      const t = theme === 'system' ? (mq.matches ? 'light' : 'dark') : theme;
      document.documentElement.dataset.theme = t;
    };
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, [theme]);
  useEffect(() => {
    document.documentElement.classList.toggle('perf', calm);
    document.documentElement.classList.toggle('has-refraction', refractionSupported && refraction && !calm);
    document.documentElement.classList.toggle('no-tilt', !tilt);
  }, [calm, refraction, tilt]);
}

/** Calm motion: the system's "reduce motion" or the app's performance mode. */
function useCalmMotion(): boolean {
  const perf = useUi((s) => s.performance);
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return perf || reduced;
}

/**
 * Page switch: the page being left stays mounted for a moment as a layer under the new one while
 * its panels animate out, and the new page's panels animate in over it (the chosen animation,
 * lib/pageAnim.ts and the CSS under .page--in / .page--out). Both stay the same React elements
 * (keyed by page), so nothing remounts or refetches mid-animation.
 */
function usePageStack(page: Page, calm: boolean) {
  const anim = useUi((s) => s.pageAnim);
  const [stack, setStack] = useState<{ cur: Page; prev: Page | null; dir: 'fwd' | 'back' }>({ cur: page, prev: null, dir: 'fwd' });
  if (stack.cur !== page) setStack({ cur: page, prev: calm || anim === 'none' ? null : stack.cur, dir: slideDir(stack.cur, page) });
  useEffect(() => {
    if (!stack.prev) return;
    const t = setTimeout(() => setStack((s) => ({ ...s, prev: null })), LEAVE_MS[anim]);
    return () => clearTimeout(t);
  }, [stack, anim]);
  return stack;
}

export default function App() {
  const page = useUi((s) => s.page);
  const calm = useCalmMotion();
  const stack = usePageStack(page, calm);
  const go = useUi((s) => s.go);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useAppearance();
  useAppIcon();
  useEffect(() => {
    document.documentElement.classList.toggle('page-settings', page === 'settings');
  }, [page]);
  useCloseToTray();

  useEffect(() => {
    waitForBackend()
      .then(startSync)
      .then(() => setReady(true))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const m = /^Digit([1-7])$/.exec(e.code);
      if (e.ctrlKey && m) {
        e.preventDefault();
        go(ORDER[Number(m[1]) - 1]!);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go]);

  // global hotkeys live in Rust; the main window (re)registers them from the saved settings
  const ov = useUi((s) => s.overlay);
  useEffect(() => {
    void applyHotkeys(ov.toggle, ov.interact);
  }, [ov.toggle, ov.interact]);

  // GSI: hero selection started -> bring up the overlay (once per transition, the user can hide it)
  const phase = useDraft((s) => s.phase);
  const prevPhase = useRef(phase);
  useEffect(() => {
    if (prevPhase.current !== 'draft' && phase === 'draft' && useUi.getState().overlay.autoShow) void showOverlay(true);
    prevPhase.current = phase;
  }, [phase]);

  const pages = stack.prev ? [stack.prev, stack.cur] : [stack.cur];
  const anim = useUi((s) => s.pageAnim);
  return (
    <>
      <Wallpaper />
      {ready && <Onboarding />}
      <div className="app">
        <TitleBar />
        <div className="app__body">
          <main className="app__main" data-anim={anim} data-dir={stack.dir}>
            {!ready ? (
              <Panel className="boot" refracting>
                {error ? (
                  <>
                    <h2>Бэкенд не отвечает</h2>
                    <p className="muted">{error}</p>
                    <p className="hint">Лог: data/api.log. Проверь, что создан .venv и установлены зависимости.</p>
                  </>
                ) : (
                  <>
                    <div className="spinner" />
                    <h2>Запускаю бэкенд…</h2>
                    <p className="muted">Загружаю модель и данные, это несколько секунд.</p>
                  </>
                )}
              </Panel>
            ) : (
              // No opacity/filter on the page wrapper: in Chromium that turns it into a "backdrop root"
              // and every glass panel inside loses the wallpaper blur for the whole transition.
              // The panels fade themselves (CSS: .page--in / .page--out).
              pages.map((p) => {
                const Page = PAGES[p];
                const leaving = p !== stack.cur;
                return (
                  <div key={p} className={`page ${leaving ? 'page--out' : 'page--in'}`} inert={leaving} aria-hidden={leaving || undefined}>
                    <Page />
                  </div>
                );
              })
            )}
          </main>
        </div>
      </div>
      {/* over the panels, not under them: under the glass the effect only showed in the gaps */}
      <Effects />
    </>
  );
}
