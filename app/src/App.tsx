import { useEffect, useRef, useState } from 'react';

import { waitForBackend } from './api/client';
import { Dock, TitleBar, Wallpaper } from './components/Chrome';
import { Panel } from './components/Glass';
import { refractionSupported } from './glass/refraction';
import { BuildsPage } from './pages/BuildsPage';
import { DraftPage } from './pages/DraftPage';
import { HeroPage } from './pages/HeroPage';
import { MetaPage } from './pages/MetaPage';
import { ProfilePage } from './pages/ProfilePage';
import { SettingsPage } from './pages/SettingsPage';
import { VisionPage } from './pages/VisionPage';
import { applyHotkeys, showOverlay } from './lib/overlay';
import { useDraft } from './state/draft';
import { startSync } from './state/sync';
import { useUi, type Page } from './state/ui';

const PAGES: Record<Page, () => React.JSX.Element> = {
  draft: DraftPage,
  meta: MetaPage,
  hero: HeroPage,
  builds: BuildsPage,
  profile: ProfilePage,
  settings: SettingsPage,
  vision: VisionPage,
};
const ORDER: Page[] = ['draft', 'meta', 'hero', 'builds', 'profile', 'settings'];

function useAppearance() {
  const { theme, performance, refraction } = useUi();
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
    document.documentElement.classList.toggle('perf', performance);
    document.documentElement.classList.toggle('has-refraction', refractionSupported && refraction && !performance);
  }, [performance, refraction]);
}

export default function App() {
  const page = useUi((s) => s.page);
  const go = useUi((s) => s.go);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useAppearance();

  useEffect(() => {
    waitForBackend()
      .then(startSync)
      .then(() => setReady(true))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const m = /^Digit([1-6])$/.exec(e.code);
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

  const Current = PAGES[page];
  return (
    <>
      <Wallpaper />
      <div className="app">
        <TitleBar />
        <div className="app__body">
          <Dock />
          <main className="app__main">
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
              // Panels fade in themselves (CSS .panel animation, staggered).
              <div key={page} className="page">
                <Current />
              </div>
            )}
          </main>
        </div>
      </div>
    </>
  );
}
