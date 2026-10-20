/**
 * Updates of the app (backend/drafter/updates.py downloads and checks the installer,
 * src-tauri/src/update.rs runs it). By hand from Settings → «Версия и обновления», or by itself:
 * a check soon after the start and every 6 hours, the download in the background, and the
 * installer runs when the app is closed (the next start is the new version).
 */
import { getVersion } from '@tauri-apps/api/app';
import { invoke, isTauri } from '@tauri-apps/api/core';
import { useEffect } from 'react';
import { create } from 'zustand';

import { api } from '../api/client';
import { useUi } from '../state/ui';

export interface UpdateCheck {
  current: string;
  latest: string;
  newer: boolean;
  notes: string;
  published: string | null;
  page: string | null;
  size: number | null;
  ready: Ready | null;
  repo: string;
}
interface Job {
  id: string;
  status: 'running' | 'done' | 'failed';
  log: string[];
  error: string | null;
}
export interface Ready {
  version: string;
  path: string;
}

interface UpdateState {
  version: string | null;
  checking: boolean;
  check: UpdateCheck | null;
  checkedAt: number | null;
  error: string | null;
  downloading: boolean;
  progress: string | null;
  ready: Ready | null;
  set: (p: Partial<UpdateState>) => void;
}

export const useUpdate = create<UpdateState>((set) => ({
  version: null,
  checking: false,
  check: null,
  checkedAt: null,
  error: null,
  downloading: false,
  progress: null,
  ready: null,
  set,
}));

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

export async function appVersion(): Promise<string | null> {
  const s = useUpdate.getState();
  if (s.version) return s.version;
  if (!isTauri()) return null;
  const v = await getVersion().catch(() => null);
  s.set({ version: v });
  return v;
}

/** Tells the shell which installer to run when the app quits (automatic updates only). */
async function armOnExit(ready: Ready | null) {
  if (!isTauri()) return;
  const path = ready && useUi.getState().autoUpdate ? ready.path : null;
  await invoke('set_pending_update', { path }).catch(() => undefined);
}

export async function checkForUpdate(): Promise<UpdateCheck | null> {
  const s = useUpdate.getState();
  const current = await appVersion();
  if (!current || s.checking) return s.check;
  s.set({ checking: true, error: null });
  try {
    const check = await api<UpdateCheck>(`/update/check?current=${encodeURIComponent(current)}`);
    s.set({ check, checkedAt: Date.now(), ready: check.ready });
    void armOnExit(check.ready);
    return check;
  } catch (e) {
    s.set({ error: errText(e), checkedAt: Date.now() });
    return null;
  } finally {
    s.set({ checking: false });
  }
}

export async function downloadUpdate(): Promise<Ready | null> {
  const s = useUpdate.getState();
  if (s.downloading) return null;
  s.set({ downloading: true, progress: null, error: null });
  try {
    // the job's own state, polled: nothing is missed if it ends before an event connection would open
    let job = await api<Job>('/update/download', { method: 'POST' });
    while (job.status === 'running') {
      await new Promise((r) => setTimeout(r, 700));
      job = await api<Job>(`/jobs/${job.id}`);
      useUpdate.getState().set({ progress: job.log[job.log.length - 1] ?? null });
    }
    if (job.status === 'failed') throw new Error((job.error ?? 'не скачалось').replace(/^\w+Error: /, ''));
    const { ready } = await api<{ ready: Ready | null }>('/update/ready');
    s.set({ ready });
    void armOnExit(ready);
    return ready;
  } catch (e) {
    s.set({ error: errText(e) });
    return null;
  } finally {
    s.set({ downloading: false, progress: null });
  }
}

/** Quits the app and installs the update now; the new version starts by itself. */
export async function installNow(ready: Ready): Promise<void> {
  await invoke('install_update', { path: ready.path });
}

const FIRST_CHECK_MS = 20_000;
const EVERY_MS = 6 * 3600_000;

/** Automatic updates (App): check, download in the background, install when the app is closed. */
export function useAutoUpdates() {
  const auto = useUi((s) => s.autoUpdate);
  useEffect(() => {
    if (!isTauri()) return;
    void armOnExit(useUpdate.getState().ready);
    if (!auto) return;
    const run = async () => {
      const c = await checkForUpdate();
      if (c?.newer && !c.ready) await downloadUpdate();
    };
    const first = window.setTimeout(run, FIRST_CHECK_MS);
    const every = window.setInterval(run, EVERY_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(every);
    };
  }, [auto]);
}
