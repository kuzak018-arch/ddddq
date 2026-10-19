/** The tray and autostart: closing to the tray (a flag in Rust) and launching with Windows. */
import { invoke, isTauri } from '@tauri-apps/api/core';
import { disable, enable, isEnabled } from '@tauri-apps/plugin-autostart';
import { useEffect } from 'react';

import { useUi } from '../state/ui';

/** Main window: tell the shell whether closing the window should hide it into the tray. */
export function useCloseToTray() {
  const on = useUi((s) => s.closeToTray);
  useEffect(() => {
    if (isTauri()) void invoke('set_close_to_tray', { on }).catch(() => undefined);
  }, [on]);
}

/** Launch with Windows (into the tray). The OS keeps the truth: read it, don't cache it. */
export async function autostartEnabled(): Promise<boolean | null> {
  if (!isTauri()) return null;
  try {
    return await isEnabled();
  } catch {
    return null;
  }
}

export async function setAutostart(on: boolean): Promise<void> {
  if (!isTauri()) return;
  if (on) await enable();
  else await disable();
}
