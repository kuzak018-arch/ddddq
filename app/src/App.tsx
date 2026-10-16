import { AnimatePresence, motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { waitForBackend } from './api/client';
import { Dock, TitleBar, Wallpaper } from './components/Chrome';
import { Glass } from './components/Glass';
import { refractionSupported } from './glass/refraction';
import { BuildsPage } from './pages/BuildsPage';
import { DraftPage } from './pages/DraftPage';
import { HeroPage } from './pages/HeroPage';
import { MetaPage } from './pages/MetaPage';
import { ProfilePage } from './pages/ProfilePage';
import { SettingsPage } from './pages/SettingsPage';
import { useUi, type Page } from './state/ui';

const PAGES: Record<Page, () => React.JSX.Element> = {
  draft: DraftPage,
  meta: MetaPage,
  hero: HeroPage,
  builds: BuildsPage,
  profile: ProfilePage,
  settings: SettingsPage,
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
              <Glass className="panel boot" refracting>
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
              </Glass>
            ) : (
              <AnimatePresence mode="wait">
                <motion.div
                  key={page}
                  className="page"
                  initial={{ opacity: 0, y: 10, filter: 'blur(4px)' }}
                  animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                  exit={{ opacity: 0, y: -6, filter: 'blur(3px)' }}
                  transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                >
                  <Current />
                </motion.div>
              </AnimatePresence>
            )}
          </main>
        </div>
      </div>
    </>
  );
}
