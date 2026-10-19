/**
 * The menu background's picture on the screen: size of the video per screen shape, framing (zoom,
 * place, turn), blur and dim, the video's piece. The builder draws the video's frames and shows its
 * preview with the same numbers, so the result matches the preview.
 *
 * Использовано из GridStudio — https://gridstudio.me, https://github.com/linsisss/dota2-grid-toolkit
 * (GPL-3.0-only): a port of scripts/menu-background.mjs (MENU_SIZES, menuLook, menuFrame,
 * framePlacement, fitPiece, mediaKind). See THIRD_PARTY_NOTICES.md.
 */

export const MENU_LIMITS = { bytes: 50_000_000, seconds: 30, videoBytes: 12_000_000, maxVideoBytes: 14_000_000, bitrate: 4_000_000 };
export type Aspect = '16:9' | '16:10' | '21:9' | '4:3';
export const MENU_SIZES: Record<Aspect, [number, number]> = { '16:9': [1920, 1080], '16:10': [1920, 1200], '21:9': [2560, 1080], '4:3': [1440, 1080] };
export const MIN_PIECE = 1;
/** Blur: a Gaussian σ of up to `blur` px at 1080 lines; dim: a black veil of up to `dim`. */
export const MENU_EFFECTS = { blur: 24, dim: 0.8 };
export const FRAME_ZOOM = 3;

export interface Frame {
  zoom: number;
  x: number;
  y: number;
  rotate: number;
  flipX: boolean;
  flipY: boolean;
}
export const DEFAULT_FRAME: Frame = { zoom: 1, x: 0.5, y: 0.5, rotate: 0, flipX: false, flipY: false };
export type Fit = 'cover' | 'contain';

/** The screen shape closest to this monitor's. */
export function screenAspect(width: number, height: number): Aspect {
  const r = width / height;
  const all: [Aspect, number][] = [['16:9', 16 / 9], ['16:10', 16 / 10], ['21:9', 21 / 9], ['4:3', 4 / 3]];
  return all.sort((a, b) => Math.abs(a[1] - r) - Math.abs(b[1] - r))[0][0];
}

/** A piece of the video (seconds): inside it, at most MENU_LIMITS.seconds, at least MIN_PIECE. */
export function fitPiece(piece: { start: number; end: number }, duration: number, moved: 'start' | 'end'): { start: number; end: number } {
  const limit = Math.min(MENU_LIMITS.seconds, duration);
  let start = Math.max(0, Math.min(piece.start, duration - MIN_PIECE));
  let end = Math.min(duration, Math.max(piece.end, start + MIN_PIECE));
  if (end - start > limit) {
    if (moved === 'start') end = start + limit;
    else start = end - limit;
  }
  return { start, end };
}

/** Blur and dim baked into the video; a blurred picture is enlarged by 2.5σ each side. */
export function menuLook(effects: { blur?: number; dim?: number }, height = 1080) {
  const clamp = (v: unknown) => Math.max(0, Math.min(1, Number(v) || 0));
  const sigma = (clamp(effects.blur) * MENU_EFFECTS.blur * height) / 1080;
  return { sigma, veil: clamp(effects.dim) * MENU_EFFECTS.dim, zoom: 1 + (5 * sigma) / height };
}

const angle = (degrees: number) => {
  const a = ((((Math.round((Number(degrees) || 0) * 10) / 10) % 360) + 540) % 360) - 180;
  return a === -180 ? 180 : a || 0;
};

export function menuFrame(frame?: Partial<Frame> | null): Frame {
  const value = (v: unknown, low: number, high: number, fallback: number) =>
    typeof v === 'number' && Number.isFinite(v) ? Math.min(high, Math.max(low, Math.round(v * 1000) / 1000)) : fallback;
  return {
    zoom: value(frame?.zoom, 1, FRAME_ZOOM, 1),
    x: value(frame?.x, 0, 1, 0.5),
    y: value(frame?.y, 0, 1, 0.5),
    rotate: typeof frame?.rotate === 'number' && Number.isFinite(frame.rotate) ? angle(frame.rotate) : 0,
    flipX: frame?.flipX === true,
    flipY: frame?.flipY === true,
  };
}

/**
 * Where the picture lies on the screen, in fractions of its width and height: filling it (cover) or
 * whole in it (contain), enlarged by the look's zoom and the frame's, placed by the frame (0 puts the
 * picture's left/top edge at the screen's, 1 its right/bottom edge). x, y, w, h: the picture's own
 * rectangle before it is turned about its centre by `rotate`.
 */
export function framePlacement(screenRatio: number, pictureRatio: number, fit: Fit, zoom = 1, frame: Partial<Frame> = DEFAULT_FRAME) {
  const f = menuFrame(frame);
  const a = (f.rotate * Math.PI) / 180;
  const c = Math.abs(Math.cos(a));
  const s = Math.abs(Math.sin(a)) < 1e-12 ? 0 : Math.abs(Math.sin(a));
  const W = screenRatio;
  const scale = fit === 'cover' ? Math.max((W * c + s) / pictureRatio, W * s + c) : Math.min(W / (pictureRatio * c + s), 1 / (pictureRatio * s + c));
  const k = scale * zoom * f.zoom;
  const w = (pictureRatio * k) / W;
  const h = k;
  const bw = (pictureRatio * k * c + k * s) / W;
  const bh = pictureRatio * k * s + k * c;
  const cx = (1 - bw) * f.x + bw / 2;
  const cy = (1 - bh) * f.y + bh / 2;
  return { x: cx - w / 2, y: cy - h / 2, w, h, bw, bh, rotate: f.rotate, flipX: f.flipX, flipY: f.flipY };
}

export const menuBitrate = (seconds: number) => Math.min(MENU_LIMITS.bitrate, Math.floor((MENU_LIMITS.videoBytes * 8) / Math.max(1, seconds)));

export interface MediaKind {
  type: 'image' | 'video';
  mime: string;
  label: string;
}

/** What an upload is, from its first bytes. */
export function mediaKind(bytes: Uint8Array): MediaKind | null {
  const has = (at: number, ...values: number[]) => values.every((v, i) => bytes[at + i] === v);
  const ascii = (at: number, text: string) => [...text].every((ch, i) => bytes[at + i] === ch.charCodeAt(0));
  if (has(0, 0x89, 0x50, 0x4e, 0x47)) return { type: 'image', mime: 'image/png', label: 'PNG' };
  if (has(0, 0xff, 0xd8, 0xff)) return { type: 'image', mime: 'image/jpeg', label: 'JPEG' };
  if (ascii(0, 'GIF8')) return { type: 'image', mime: 'image/gif', label: 'GIF' };
  if (ascii(0, 'RIFF') && ascii(8, 'WEBP')) return { type: 'image', mime: 'image/webp', label: 'WebP' };
  if (has(0, 0x1a, 0x45, 0xdf, 0xa3)) return { type: 'video', mime: 'video/webm', label: 'WebM' };
  if (ascii(4, 'ftyp')) return { type: 'video', mime: 'video/mp4', label: 'MP4' };
  return null;
}
