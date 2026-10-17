/**
 * The app's own icon: the user's picture (any image, GIF too) shown next to "Dota Drafter" and
 * used as the window's taskbar icon. The file lives in IndexedDB, the choice in the UI state.
 */
import { defaultWindowIcon } from '@tauri-apps/api/app';
import { isTauri } from '@tauri-apps/api/core';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { useEffect, useState } from 'react';

import { loadFile } from '../state/bgstore';
import { useUi } from '../state/ui';

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

/** Square PNG of the picture (centre crop, first frame of a GIF) for the taskbar icon. */
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

/** Main window only: keep the taskbar icon in step with the chosen logo. */
export function useWindowIcon(enabled: boolean) {
  const logo = useUi((s) => s.logo);
  useEffect(() => {
    if (!enabled || !isTauri()) return;
    let cancelled = false;
    (async () => {
      const win = getCurrentWindow();
      const blob = logo.kind === 'file' ? await loadFile(LOGO_KEY) : null;
      if (cancelled) return;
      if (blob) await win.setIcon(await toIconPng(blob));
      else {
        const def = await defaultWindowIcon();
        if (def && !cancelled) await win.setIcon(def);
      }
    })().catch((e) => console.warn('иконка окна не сменилась', e));
    return () => {
      cancelled = true;
    };
  }, [enabled, logo.kind, logo.key]);
}
