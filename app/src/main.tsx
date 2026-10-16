import '@fontsource-variable/inter';
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
import { isOverlayWindow } from './lib/overlay';
import { OverlayApp } from './overlay/OverlayApp';
import './overlay/overlay.css';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: false, retry: 1 } },
});

installButtonSheen();

// resolve the backend URL first so icon URLs are absolute from the first render
backend().then(() => {
  ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        {/* one soft spring for every motion animation; honours the OS "reduce motion" setting */}
        <MotionConfig reducedMotion="user" transition={{ type: 'spring', stiffness: 260, damping: 30, mass: 0.9 }}>
          {isOverlayWindow() ? <OverlayApp /> : <App />}
        </MotionConfig>
      </QueryClientProvider>
    </React.StrictMode>,
  );
});
