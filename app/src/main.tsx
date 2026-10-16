import '@fontsource-variable/inter';
import './styles/tokens.css';
import './styles/glass.css';
import './styles/app.css';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import ReactDOM from 'react-dom/client';

import { backend } from './api/client';
import App from './App';
import { installButtonSheen } from './components/Glass';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: false, retry: 1 } },
});

installButtonSheen();

// resolve the backend URL first so icon URLs are absolute from the first render
backend().then(() => {
  ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
    <React.StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </React.StrictMode>,
  );
});
