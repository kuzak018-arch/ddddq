import { useEffect, useState } from 'react';

import type { Theme } from '../state/ui';

const LIGHT = '(prefers-color-scheme: light)';

/** The theme actually shown: «system» follows Windows. Computed from the setting itself, not read
 * back from <html data-theme>, so effects that depend on it never see the previous theme. */
export function useResolvedTheme(theme: Theme): 'light' | 'dark' {
  const [sysLight, setSysLight] = useState(() => window.matchMedia(LIGHT).matches);
  useEffect(() => {
    const mq = window.matchMedia(LIGHT);
    const on = () => setSysLight(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return theme === 'system' ? (sysLight ? 'light' : 'dark') : theme;
}
