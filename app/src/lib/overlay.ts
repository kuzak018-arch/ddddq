/** Bridge to the overlay window commands in Rust (no-ops in a plain browser). */
import { invoke, isTauri } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { create } from 'zustand';

/** Result of the last hotkey registration, shown in Settings. */
export const useHotkeyStatus = create<{ error: string | null; set: (e: string | null) => void }>((set) => ({
  error: null,
  set: (error) => set({ error }),
}));

export async function applyHotkeys(toggle: string, interact: string): Promise<boolean> {
  try {
    await setHotkeys(toggle, interact);
    useHotkeyStatus.getState().set(null);
    return true;
  } catch (e) {
    useHotkeyStatus.getState().set(String(e));
    return false;
  }
}

export const isOverlayWindow = () => location.hash.includes('overlay');

export interface OverlayStatus {
  visible: boolean;
  click_through: boolean;
}

export async function overlayStatus(): Promise<OverlayStatus> {
  if (!isTauri()) return { visible: false, click_through: false };
  const [visible, click_through] = await invoke<[boolean, boolean]>('overlay_status');
  return { visible, click_through };
}

export function onOverlayStatus(cb: (s: OverlayStatus) => void): () => void {
  if (!isTauri()) return () => {};
  const un = listen<OverlayStatus>('overlay-status', (e) => cb(e.payload));
  return () => void un.then((f) => f());
}

export const toggleOverlay = () => (isTauri() ? invoke('overlay_toggle') : Promise.resolve());
export const showOverlay = (show: boolean) => (isTauri() ? invoke('overlay_show', { show }) : Promise.resolve());
export const setClickThrough = (on: boolean) =>
  isTauri() ? invoke('overlay_set_click_through', { on }) : Promise.resolve();

/** Returns the effect actually applied ("acrylic" or "tint"). */
export async function setOverlayEffect(effect: 'acrylic' | 'tint', alpha: number): Promise<'acrylic' | 'tint'> {
  if (!isTauri()) return 'tint';
  return invoke<'acrylic' | 'tint'>('overlay_set_effect', { effect, alpha: Math.round(alpha) });
}

export async function setHotkeys(toggle: string, interact: string): Promise<void> {
  if (!isTauri()) return;
  await invoke('overlay_set_hotkeys', { toggle, interact });
}

/** "Ctrl+Shift+M" from a keydown event; null while only modifiers are held. */
export function comboFromEvent(e: KeyboardEvent): string | null {
  const mods = [e.ctrlKey && 'Ctrl', e.altKey && 'Alt', e.shiftKey && 'Shift'].filter(Boolean) as string[];
  let key: string | null = null;
  if (/^Key[A-Z]$/.test(e.code)) key = e.code.slice(3);
  else if (/^Digit\d$/.test(e.code)) key = e.code.slice(5);
  else if (/^F\d{1,2}$/.test(e.code)) key = e.code;
  else if (['Home', 'End', 'Insert', 'PageUp', 'PageDown', 'Pause', 'Backquote'].includes(e.code)) key = e.code;
  else if (/^Numpad\d$/.test(e.code)) key = e.code;
  if (!key) return null;
  return [...mods, key].join('+');
}

/** Dota's name for the main key of a combo, to compare with the user's Dota bindings. */
export function dotaKeyName(combo: string): string {
  const key = combo.split('+').pop()!;
  const map: Record<string, string> = { PageUp: 'PGUP', PageDown: 'PGDN', Backquote: '`', Insert: 'INS', Home: 'HOME', End: 'END' };
  if (/^Numpad(\d)$/.test(key)) return `KP_${key.slice(6)}`;
  return map[key] ?? key.toUpperCase();
}
