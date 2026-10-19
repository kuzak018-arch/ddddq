/**
 * The upload becomes the menu's WebM right here (WebCodecs through Mediabunny): VP9, or VP8 where
 * there is no VP9 encoder, no sound (Dota has no Opus decoder), 30 fps, at most 30 seconds and about
 * 14 MB (Dota shows a black menu for big videos). Frames are drawn on a black screen of the chosen
 * size: «cover» crops the edges, «contain» letterboxes; transparency becomes black. A picture is a
 * 10-second clip at 1 fps, a GIF or animated WebP keeps its frame timing, a video gives the chosen
 * piece resampled to 30 fps. Blur, dim and the framing are drawn into every frame.
 *
 * Использовано из GridStudio — https://gridstudio.me, https://github.com/linsisss/dota2-grid-toolkit
 * (GPL-3.0-only): a port of src/customize/menu-video.js (its quality notes: docs/customize.md there).
 */
import { ALL_FORMATS, BlobSource, BufferTarget, CanvasSource, Input, Output, VideoSampleSink, WebMOutputFormat, canEncodeVideo } from 'mediabunny';

import { framePlacement, mediaKind, MENU_LIMITS, menuBitrate, menuLook, type Fit, type Frame, type MediaKind } from './frame';

export class MenuVideoError extends Error {}
const STILL_SECONDS = 10;
const FPS = 30;
const KEY_FRAMES = 10;
const MIN_BITRATE = 300_000;

type Look = ReturnType<typeof menuLook> & { frame: Partial<Frame> | null; small?: OffscreenCanvas };
type Ctx = OffscreenCanvasRenderingContext2D;

function place(ctx: Ctx, source: CanvasImageSource, x: number, y: number, w: number, h: number, at: { rotate: number; flipX: boolean; flipY: boolean }) {
  if (!at.rotate && !at.flipX && !at.flipY) return ctx.drawImage(source, x, y, w, h);
  ctx.save();
  ctx.translate(x + w / 2, y + h / 2);
  ctx.rotate((at.rotate * Math.PI) / 180);
  ctx.scale(at.flipX ? -1 : 1, at.flipY ? -1 : 1);
  ctx.drawImage(source, -w / 2, -h / 2, w, h);
  ctx.restore();
}

function paint(ctx: Ctx, source: CanvasImageSource, sw: number, sh: number, fit: Fit, look: Look, ground = true) {
  const { width, height } = ctx.canvas;
  if (ground) {
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, width, height);
  }
  const at = framePlacement(width / height, sw / sh, fit, look.zoom, look.frame ?? undefined);
  const w = at.w * width;
  const h = at.h * height;
  const x = at.x * width;
  const y = at.y * height;
  ctx.imageSmoothingQuality = 'high';
  if (!look.sigma) return place(ctx, source, x, y, w, h, at);
  // the blur runs on a copy k times smaller (σ/k ≥ 4 px there): the same look, many times faster
  const k = Math.max(1, Math.floor(look.sigma / 4));
  if (k === 1) {
    ctx.filter = `blur(${look.sigma}px)`;
    place(ctx, source, x, y, w, h, at);
    ctx.filter = 'none';
    return;
  }
  const small = (look.small ??= new OffscreenCanvas(Math.ceil(width / k), Math.ceil(height / k)));
  const tiny = small.getContext('2d')!;
  tiny.clearRect(0, 0, small.width, small.height);
  tiny.imageSmoothingQuality = 'high';
  tiny.filter = `blur(${look.sigma / k}px)`;
  place(tiny, source, x / k, y / k, w / k, h / k, at);
  tiny.filter = 'none';
  ctx.imageSmoothingQuality = 'low';
  ctx.drawImage(small, 0, 0, small.width * k, small.height * k);
}

const veil = (ctx: Ctx, look: Look) => {
  if (!look.veil) return;
  ctx.fillStyle = `rgba(0,0,0,${look.veil})`;
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
};

async function pickCodec(width: number, height: number, bitrate: number) {
  if (typeof VideoEncoder === 'undefined') throw new MenuVideoError('Здесь нет кодировщика видео (WebCodecs): обнови Windows и WebView2.');
  for (const codec of ['vp9', 'vp8'] as const) {
    if (await canEncodeVideo(codec, { width, height, bitrate, hardwareAcceleration: 'prefer-software' })) return { codec, hardwareAcceleration: 'prefer-software' as const };
    if (await canEncodeVideo(codec, { width, height, bitrate })) return { codec };
  }
  throw new MenuVideoError('Не получается кодировать WebM (VP9/VP8): обнови WebView2.');
}

interface Tune {
  bitrate?: number;
  bitrateMode?: 'variable' | 'constant';
}

async function encoderOptions(canvas: OffscreenCanvas, seconds: number, tune: Tune) {
  const bitrate = tune.bitrate ?? menuBitrate(seconds);
  const picked = await pickCodec(canvas.width, canvas.height, bitrate);
  return { ...picked, bitrate, bitrateMode: tune.bitrateMode ?? ('variable' as const), keyFrameInterval: KEY_FRAMES };
}

interface PictureFrame {
  image: CanvasImageSource;
  width: number;
  height: number;
  duration: number | null;
  close: () => void;
}

async function* pictureFrames(file: Blob, kind: MediaKind): AsyncGenerator<PictureFrame> {
  if (typeof ImageDecoder !== 'undefined' && ['image/gif', 'image/webp'].includes(kind.mime) && (await ImageDecoder.isTypeSupported(kind.mime))) {
    const decoder = new ImageDecoder({ data: await file.arrayBuffer(), type: kind.mime });
    try {
      await decoder.tracks.ready;
      const track = decoder.tracks.selectedTrack;
      if (track?.animated && track.frameCount > 1) {
        for (let index = 0; index < track.frameCount; index++) {
          const { image } = await decoder.decode({ frameIndex: index });
          // GIF delays under 20 ms are shown as 100 ms by browsers; so is the result
          const seconds = (image.duration || 0) / 1e6;
          yield { image, width: image.displayWidth, height: image.displayHeight, duration: seconds >= 0.02 ? seconds : 0.1, close: () => image.close() };
        }
        return;
      }
    } finally {
      decoder.close();
    }
  }
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new MenuVideoError(`Не получилось открыть ${kind.label}: пересохрани картинку или выбери другую.`);
  }
  yield { image: bitmap, width: bitmap.width, height: bitmap.height, duration: null, close: () => bitmap.close() };
}

export interface EncodeResult {
  video: Uint8Array;
  seconds: number;
  codec: string;
  bitrate: number;
}

type Progress = (share: number) => void;

async function encodePicture(file: Blob, kind: MediaKind, canvas: OffscreenCanvas, fit: Fit, look: Look, onProgress: Progress, signal: AbortSignal | undefined, tune: Tune): Promise<EncodeResult> {
  const ctx = canvas.getContext('2d')!;
  const frames = pictureFrames(file, kind);
  const first = (await frames.next()).value as PictureFrame;
  const still = first.duration === null;
  const options = await encoderOptions(canvas, still ? STILL_SECONDS : MENU_LIMITS.seconds, tune);
  const output = new Output({ format: new WebMOutputFormat(), target: new BufferTarget() });
  const source = new CanvasSource(canvas, options);
  output.addVideoTrack(source, { frameRate: still ? 1 : 30 });
  await output.start();
  let time = 0;
  try {
    if (still) {
      paint(ctx, first.image, first.width, first.height, fit, look);
      veil(ctx, look);
      first.close();
      for (let second = 0; second < STILL_SECONDS; second++) {
        if (signal?.aborted) throw new DOMException('Отменено', 'AbortError');
        await source.add(second, 1);
        onProgress(second / STILL_SECONDS);
      }
      time = STILL_SECONDS;
    } else {
      let frame: PictureFrame | undefined = first;
      while (frame) {
        if (signal?.aborted) {
          frame.close();
          throw new DOMException('Отменено', 'AbortError');
        }
        if (time >= MENU_LIMITS.seconds) {
          frame.close();
          break;
        }
        paint(ctx, frame.image, frame.width, frame.height, fit, look);
        veil(ctx, look);
        frame.close();
        const duration = Math.min(frame.duration ?? 0.1, MENU_LIMITS.seconds - time);
        await source.add(time, duration);
        time += duration;
        onProgress(time / MENU_LIMITS.seconds);
        frame = (await frames.next()).value as PictureFrame | undefined;
      }
    }
    await output.finalize();
  } catch (error) {
    await output.cancel().catch(() => undefined);
    throw error;
  } finally {
    await frames.return?.(undefined);
  }
  return { video: new Uint8Array((output.target as BufferTarget).buffer!), seconds: time, codec: options.codec, bitrate: options.bitrate };
}

async function encodeVideo(file: Blob, kind: MediaKind, canvas: OffscreenCanvas, fit: Fit, look: Look, onProgress: Progress, signal: AbortSignal | undefined,
  piece: { start: number; end: number } | null, crossfade: number, tune: Tune): Promise<EncodeResult> {
  const input = new Input({ source: new BlobSource(file), formats: ALL_FORMATS });
  try {
    const track = await input.getPrimaryVideoTrack().catch(() => null);
    if (!track) throw new MenuVideoError(`В файле ${kind.label} нет видео, которое можно прочитать.`);
    if (!(await track.canDecode())) throw new MenuVideoError('Это видео не читается: пересохрани его в MP4 (H.264) или WebM.');
    const first = await track.getFirstTimestamp();
    const length = Math.max(0.1, (await input.computeDuration()) - first);
    const start = Math.max(0, Math.min(piece?.start ?? 0, length - 0.1));
    const end = Math.min(length, piece?.end ?? length, start + MENU_LIMITS.seconds);
    const fade = Math.max(0, Math.min(crossfade, (end - start) / 3));
    const seconds = end - start - fade;
    const count = Math.max(1, Math.round(seconds * FPS));
    const options = await encoderOptions(canvas, seconds, tune);
    const ctx = canvas.getContext('2d')!;
    const output = new Output({ format: new WebMOutputFormat(), target: new BufferTarget() });
    const source = new CanvasSource(canvas, options);
    output.addVideoTrack(source, { frameRate: FPS });
    await output.start();
    // one decoder walks the clip frame by frame; a second one, the piece's start for the loop's blend
    const times = Array.from({ length: count }, (_, k) => start + fade + k / FPS);
    const blendFrom = end - fade;
    const main = new VideoSampleSink(track).samplesAtTimestamps(times.map((t) => first + t));
    const head = fade ? new VideoSampleSink(track).samplesAtTimestamps(times.filter((t) => t >= blendFrom).map((t) => first + t - (end - start - fade))) : null;
    try {
      for (const [k, t] of times.entries()) {
        if (signal?.aborted) throw new DOMException('Отменено', 'AbortError');
        const { value: sample } = await main.next();
        if (sample) {
          paint(ctx, sample.toCanvasImageSource(), sample.displayWidth, sample.displayHeight, fit, look);
          sample.close();
        }
        if (head && t >= blendFrom) {
          const { value: other } = await head.next();
          if (other) {
            ctx.globalAlpha = Math.min(1, (t - blendFrom) / fade);
            paint(ctx, other.toCanvasImageSource(), other.displayWidth, other.displayHeight, fit, look, false);
            ctx.globalAlpha = 1;
            other.close();
          }
        }
        veil(ctx, look);
        await source.add(k / FPS, 1 / FPS);
        onProgress((k + 1) / count);
      }
      await output.finalize();
    } catch (error) {
      await output.cancel().catch(() => undefined);
      throw error;
    } finally {
      await main.return?.(undefined);
      await head?.return?.(undefined);
    }
    return { video: new Uint8Array((output.target as BufferTarget).buffer!), seconds, codec: options.codec, bitrate: options.bitrate };
  } finally {
    input.dispose?.();
  }
}

export interface EncodeOptions {
  size: [number, number];
  fit: Fit;
  effects?: { blur?: number; dim?: number };
  frame?: Partial<Frame> | null;
  piece?: { start: number; end: number } | null;
  crossfade?: number;
  onProgress?: Progress;
  signal?: AbortSignal;
}

export async function encodeMenuVideo(file: Blob, o: EncodeOptions): Promise<EncodeResult & { kind: MediaKind }> {
  if (file.size > MENU_LIMITS.bytes) throw new MenuVideoError(`Файл больше ${MENU_LIMITS.bytes / 1_000_000} МБ.`);
  const kind = mediaKind(new Uint8Array(await file.slice(0, 16).arrayBuffer()));
  if (!kind) throw new MenuVideoError('Нужна картинка (PNG, JPEG, WebP), GIF или видео (MP4, WebM).');
  const [width, height] = o.size;
  const canvas = new OffscreenCanvas(width, height);
  const look: Look = { ...menuLook(o.effects ?? {}, height), frame: o.frame ?? null };
  const onProgress = o.onProgress ?? (() => undefined);
  const encode = (tune: Tune) =>
    kind.type === 'video'
      ? encodeVideo(file, kind, canvas, o.fit, look, onProgress, o.signal, o.piece ?? null, o.crossfade ?? 0, tune)
      : encodePicture(file, kind, canvas, o.fit, look, onProgress, o.signal, tune);
  // noise and grain make the encoder overshoot; over the limit it is encoded again (see GridStudio's notes)
  let result = await encode({});
  for (let attempt = 1; attempt < 3 && result.video.length > MENU_LIMITS.maxVideoBytes; attempt++) {
    result = await encode(
      attempt === 1
        ? { bitrate: Math.max(MIN_BITRATE, Math.floor(result.bitrate * (MENU_LIMITS.videoBytes / result.video.length) ** 3)) }
        : { bitrate: menuBitrate(result.seconds), bitrateMode: 'constant' },
    );
  }
  onProgress(1);
  return { ...result, kind };
}
