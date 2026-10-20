/**
 * Backend access. Inside Tauri the shell starts the Python API and tells us its URL and
 * per-launch token; in a plain browser (vite dev) we talk to a backend started by hand
 * (`python -m drafter.api`, no token) at VITE_API or http://127.0.0.1:47900.
 */
import { invoke, isTauri } from '@tauri-apps/api/core';

export interface BackendInfo {
  url: string;
  token: string;
  source: string;
}

let infoPromise: Promise<BackendInfo> | null = null;

/** Ask the shell until it has started the backend (a window can load before that). */
async function askShell(): Promise<BackendInfo> {
  for (let i = 0; ; i++) {
    try {
      return await invoke<BackendInfo>('backend_info');
    } catch (e) {
      // the shell could not start the backend at all (e.g. an antivirus took drafter-backend.exe)
      if (String(e).startsWith('не удалось запустить бэкенд')) throw new Error(String(e));
      if (i >= 150) throw new Error(`оболочка не сообщила адрес бэкенда: ${e}`);
      await new Promise((r) => setTimeout(r, 200));
    }
  }
}

export function backend(): Promise<BackendInfo> {
  if (!infoPromise) {
    infoPromise = isTauri()
      ? askShell()
      : Promise.resolve({ url: import.meta.env.VITE_API ?? 'http://127.0.0.1:47900', token: '', source: 'browser' });
  }
  return infoPromise;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function detail(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x) => (x as { msg?: string }).msg ?? String(x)).join('; ');
  }
  return 'ошибка сервера';
}

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const { url, token } = await backend();
  const res = await fetch(url + path, {
    method: init.method ?? (init.body === undefined ? 'GET' : 'POST'),
    headers: {
      ...(token ? { 'X-Drafter-Token': token } : {}),
      ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detail(body));
  return body as T;
}

/**
 * A raw upload: 4-byte length + JSON `meta`, then 4-byte length + data per file (the backend has no
 * multipart parser in the bundle).
 */
export async function apiUpload<T>(path: string, meta: unknown, files: Uint8Array[]): Promise<T> {
  const json = new TextEncoder().encode(JSON.stringify(meta));
  const parts: Uint8Array[] = [];
  const length = (n: number) => {
    const b = new Uint8Array(4);
    new DataView(b.buffer).setUint32(0, n, true);
    return b;
  };
  parts.push(length(json.length), json);
  for (const f of files) parts.push(length(f.length), f);
  const { url, token } = await backend();
  const res = await fetch(url + path, {
    method: 'POST',
    headers: { ...(token ? { 'X-Drafter-Token': token } : {}), 'Content-Type': 'application/octet-stream' },
    body: new Blob(parts as BlobPart[]),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detail(body));
  return body as T;
}

/** Raw bytes in, JSON out (a font to check). */
export async function apiBytes<T>(path: string, data: Blob): Promise<T> {
  const { url, token } = await backend();
  const res = await fetch(url + path, { method: 'POST', headers: { ...(token ? { 'X-Drafter-Token': token } : {}), 'Content-Type': 'application/octet-stream' }, body: data });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detail(body));
  return body as T;
}

let assetBase = '';
/** Absolute URL for backend static files (icons). main.tsx resolves the backend before rendering. */
export function asset(path: string): string {
  return assetBase + path;
}
backend().then((b) => (assetBase = b.url));

export async function waitForBackend(timeoutMs = 60_000): Promise<void> {
  const t0 = Date.now();
  for (;;) {
    try {
      await api('/health');
      return;
    } catch (e) {
      if (Date.now() - t0 > timeoutMs) throw e;
      await new Promise((r) => setTimeout(r, 400));
    }
  }
}

/** Events from the backend (job progress, later GSI and screen reading). Reconnects on its own. */
export function subscribe(onEvent: (e: { type: string; [k: string]: unknown }) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let retry = 0;
  const connect = async () => {
    const { url, token } = await backend();
    if (closed) return;
    ws = new WebSocket(url.replace(/^http/, 'ws') + '/events' + (token ? `?token=${token}` : ''));
    ws.onmessage = (m) => onEvent(JSON.parse(m.data));
    ws.onopen = () => (retry = 0);
    ws.onclose = () => {
      if (!closed) setTimeout(connect, Math.min(5000, 300 * 2 ** retry++));
    };
  };
  connect();
  return () => {
    closed = true;
    ws?.close();
  };
}

/** An image from the backend behind the token (avatar, snapshots) as an object URL. */
export async function backendImage(path: string): Promise<string> {
  const { url, token } = await backend();
  const res = await fetch(url + path, { headers: token ? { 'X-Drafter-Token': token } : {} });
  if (!res.ok) throw new ApiError(res.status, 'картинка не загрузилась');
  return URL.createObjectURL(await res.blob());
}
