/**
 * The app's own icon: the user's picture (any image, GIF too) shown next to "Dota Drafter" and
 * handed to the shell for the windows, the tray and the shortcuts (src-tauri/src/appicon.rs).
 * The file lives in IndexedDB, the choice in the UI state.
 */
import { invoke, isTauri } from '@tauri-apps/api/core';
import { useEffect, useState } from 'react';
import { create } from 'zustand';

import { loadFile } from '../state/bgstore';
import { useUi } from '../state/ui';
import { buildIco, ICO_SIZES } from './ico';

export const LOGO_KEY = 'logo';
const ICON_SIZE = 256;

/** Object URL of the user's logo, or null for the built-in one. */
export function useLogoUrl(): string | null {
  const logo = useUi((s) => s.logo);
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (logo.kind !== 'file') {
      setUrl(null);
      return;
    }
    let made: string | null = null;
    let alive = true;
    loadFile(LOGO_KEY).then((blob) => {
      if (blob && alive) setUrl((made = URL.createObjectURL(blob)));
    });
    return () => {
      alive = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [logo.kind, logo.key]);
  return url;
}

/** Square PNG of the picture (centre crop, first frame of a GIF) for the icons. */
export async function toIconPng(blob: Blob, size = ICON_SIZE): Promise<Uint8Array> {
  const bmp = await createImageBitmap(blob);
  const side = Math.min(bmp.width, bmp.height);
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const g = canvas.getContext('2d')!;
  g.imageSmoothingQuality = 'high';
  g.drawImage(bmp, (bmp.width - side) / 2, (bmp.height - side) / 2, side, side, 0, 0, size, size);
  bmp.close();
  const png = await new Promise<Blob>((ok, fail) => canvas.toBlob((b) => (b ? ok(b) : fail(new Error('canvas'))), 'image/png'));
  return new Uint8Array(await png.arrayBuffer());
}

export interface IconApplied {
  /** Where a shortcut of ours got the icon: "Рабочий стол", "Пуск", "Панель задач". */
  shortcuts: string[];
  error: string | null;
}

/** The last result of putting the icon on the shortcuts, for the settings card. */
export const useIconResult = create<{ busy: boolean; result: IconApplied | null; error: string | null }>(() => ({
  busy: false,
  result: null,
  error: null,
}));

async function iconFiles(blob: Blob): Promise<{ png: number[]; ico: number[] }> {
  const images = [];
  for (const size of ICO_SIZES) images.push({ size, png: await toIconPng(blob, size) });
  return { png: Array.from(images[images.length - 1].png), ico: Array.from(buildIco(images)) };
}

/**
 * Main window only: the shell keeps the chosen icon on every window, the tray and our shortcuts
 * and restores it at start; here it is handed over when the choice differs from what the shell has.
 */
export function useAppIcon() {
  const logo = useUi((s) => s.logo);
  useEffect(() => {
    if (!isTauri()) return;
    let cancelled = false;
    (async () => {
      const have = await invoke<{ key: string | null }>('app_icon_state');
      const want = logo.kind === 'file' ? (logo.key ?? 'file') : null;
      if (cancelled || have.key === want) return;
      const blob = want ? await loadFile(LOGO_KEY) : null;
      if (cancelled || (want && !blob)) return;
      useIconResult.setState({ busy: true, error: null });
      const files = blob ? await iconFiles(blob) : { png: null, ico: null };
      const result = await invoke<IconApplied>('set_app_icon', { ...files, key: want });
      useIconResult.setState({ busy: false, result, error: null });
    })().catch((e) => {
      console.warn('значок не сменился', e);
      useIconResult.setState({ busy: false, error: String(e) });
    });
    return () => {
      cancelled = true;
    };
  }, [logo.kind, logo.key]);
}
