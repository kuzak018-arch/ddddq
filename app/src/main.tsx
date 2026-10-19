import '@fontsource-variable/onest';
import '@fontsource-variable/unbounded';
import '@fontsource-variable/jetbrains-mono';
import './styles/tokens.css';
import './styles/glass.css';
import './styles/app.css';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MotionConfig } from 'motion/react';
import React from 'react';
import ReactDOM from 'react-dom/client';

import { backend } from './api/client';
import App from './App';
import { installButtonSheen } from './components/Glass';
import { installWheelDebug } from './lib/wheel';
import { isOverlayWindow } from './lib/overlay';
import { OverlayApp } from './overlay/OverlayApp';
import { useUi } from './state/ui';
import './overlay/overlay.css';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: false, retry: 1 } },
});

installButtonSheen();
installWheelDebug(); // hidden wheel-scrolling debug log (Ctrl+Alt+Shift+W), off: no listeners

// Never leave the user with a blank window: if the UI crashes or doesn't start, say why.
function showFatal(message: string) {
  const root = document.getElementById('root');
  if (!root || root.querySelector('.app, .ov')) return;
  root.innerHTML = '';
  const box = document.createElement('pre');
  box.className = 'fatal';
  box.textContent = `Интерфейс не запустился.\n\n${message}\n\nЛог бэкенда: %LOCALAPPDATA%\\DotaDrafter\\logs\\backend.log`;
  root.append(box);
}
window.addEventListener('error', (e) => showFatal(`${e.message}\n${e.error?.stack ?? ''}`));
window.addEventListener('unhandledrejection', (e) => showFatal(String(e.reason?.stack ?? e.reason)));
let started = false;
setTimeout(() => !started && showFatal('Нет ответа от оболочки (backend_info) за 40 секунд.'), 40_000);

/** One soft spring for every motion animation. It honours the OS "reduce motion" setting, and the
 * app's performance mode turns motion off the same way (CSS animations stop via .perf). */
function Motion({ children }: { children: React.ReactNode }) {
  const perf = useUi((s) => s.performance);
  return (
    <MotionConfig reducedMotion={perf ? 'always' : 'user'} transition={{ type: 'spring', stiffness: 260, damping: 30, mass: 0.9 }}>
      {children}
    </MotionConfig>
  );
}

// resolve the backend URL first so icon URLs are absolute from the first render
backend().then(() => {
  started = true;
  ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <Motion>{isOverlayWindow() ? <OverlayApp /> : <App />}</Motion>
      </QueryClientProvider>
    </React.StrictMode>,
  );
});
