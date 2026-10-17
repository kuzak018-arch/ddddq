/**
 * App updates from GitHub releases (Tauri updater): a quiet check after start and every few hours,
 * a notice in the title bar, and "update and restart" in Settings. The release build (CI) sets
 * where to look; a local build has no endpoint and says so instead of failing.
 */
import { getVersion } from '@tauri-apps/api/app';
import { isTauri } from '@tauri-apps/api/core';
import { relaunch } from '@tauri-apps/plugin-process';
import { check, type Update } from '@tauri-apps/plugin-updater';
import { useEffect } from 'react';
import { create } from 'zustand';

type Status = 'idle' | 'checking' | 'none' | 'available' | 'downloading' | 'ready' | 'unconfigured' | 'error';

interface UpdatesState {
  status: Status;
  current: string | null;
  version: string | null;
  notes: string | null;
  error: string | null;
  progress: number | null;   // 0..1 while downloading
  checkedAt: number | null;
}

let pending: Update | null = null;

export const useUpdates = create<UpdatesState>(() => ({
  status: 'idle',
  current: null,
  version: null,
  notes: null,
  error: null,
  progress: null,
  checkedAt: null,
}));

const set = useUpdates.setState;

export async function checkForUpdates(): Promise<void> {
  if (!isTauri()) return set({ status: 'unconfigured', error: 'обновления работают только в установленном приложении' });
  const s = useUpdates.getState();
  if (s.status === 'checking' || s.status === 'downloading') return;
  set({ status: 'checking', error: null, current: s.current ?? (await getVersion().catch(() => null)) });
  try {
    const u = await check();
    pending = u;
    set(
      u
        ? { status: 'available', version: u.version, notes: u.body ?? null, checkedAt: Date.now() }
        : { status: 'none', version: null, notes: null, checkedAt: Date.now() },
    );
  } catch (e) {
    const msg = String(e);
    // a build made on the PC has no update address: that is not an error worth showing in red
    if (/endpoint/i.test(msg)) set({ status: 'unconfigured', error: null, checkedAt: Date.now() });
    else set({ status: 'error', error: msg, checkedAt: Date.now() });
  }
}

export async function installUpdate(): Promise<void> {
  if (!pending) return;
  let total = 0;
  let got = 0;
  set({ status: 'downloading', progress: 0, error: null });
  try {
    await pending.downloadAndInstall((ev) => {
      if (ev.event === 'Started') total = ev.data.contentLength ?? 0;
      if (ev.event === 'Progress') {
        got += ev.data.chunkLength;
        set({ progress: total ? got / total : null });
      }
      if (ev.event === 'Finished') set({ progress: 1 });
    });
    set({ status: 'ready' });
    await relaunch();
  } catch (e) {
    set({ status: 'error', error: String(e), progress: null });
  }
}

const FIRST_CHECK_MS = 20_000;
const EVERY_MS = 6 * 3600_000;

/** Main window only: check quietly after start and then every few hours. */
export function useUpdateChecks(enabled: boolean) {
  useEffect(() => {
    if (!enabled || !isTauri()) return;
    getVersion().then((current) => set({ current })).catch(() => undefined);
    const first = setTimeout(checkForUpdates, FIRST_CHECK_MS);
    const every = setInterval(checkForUpdates, EVERY_MS);
    return () => {
      clearTimeout(first);
      clearInterval(every);
    };
  }, [enabled]);
}
