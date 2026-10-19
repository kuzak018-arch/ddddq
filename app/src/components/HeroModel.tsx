/**
 * A big hero portrait: the 3D model alone (no scene behind it) over a backing of the same hero's
 * portrait blurred, with a soft glow in the hero's colour and a glass rim. The model may stand a
 * little above the card (iOS style).
 *
 * Where the model comes from (backend drafter/data/renders.py): dota2.com's animated render is a
 * VP9 webm with alpha; the first time a hero is shown its first frame is drawn here (WebView2
 * decodes the alpha) and sent back as a PNG, which the backend keeps when it really is a cut-out.
 * A hero without such a render gets its background removed by the backend once. Every later
 * showing is the cached PNG; `animated` plays the render itself.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type CSSProperties } from 'react';

import { api, apiBytes, asset } from '../api/client';
import { isCutOut, placeStill } from '../lib/heroModel';

interface RenderInfo {
  key: string;
  still: boolean;
  source: 'render' | 'segmented' | null;
  color: string | null;
  size: [number, number] | null;
  crop: [number, number, number, number] | null;
  frame: [number, number] | null;
  video: boolean;
  video_missing: boolean;
}

const preparing = new Map<string, Promise<void>>();

/** The first frame of the render as a PNG with alpha, or null when it is not a cut-out. */
async function firstFrame(blob: Blob): Promise<Blob | null> {
  const url = URL.createObjectURL(blob);
  const v = document.createElement('video');
  v.muted = true;
  v.playsInline = true;
  v.preload = 'auto';
  try {
    await new Promise<void>((ok, fail) => {
      v.onloadeddata = () => ok();
      v.onerror = () => fail(new Error('видео не декодировалось'));
      v.src = url;
    });
    if (v.currentTime !== 0) {
      v.currentTime = 0;
      await new Promise((ok) => (v.onseeked = ok));
    }
    const c = document.createElement('canvas');
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    const g = c.getContext('2d', { willReadFrequently: true });
    if (!g || !c.width) return null;
    g.drawImage(v, 0, 0);
    // the check on a small copy: the same answer, a hundredth of the work
    const s = document.createElement('canvas');
    s.width = 160;
    s.height = Math.max(8, Math.round((160 * c.height) / c.width));
    const sg = s.getContext('2d', { willReadFrequently: true })!;
    sg.drawImage(c, 0, 0, s.width, s.height);
    if (!isCutOut(sg.getImageData(0, 0, s.width, s.height).data, s.width, s.height)) return null;
    return await new Promise((ok) => c.toBlob((b) => ok(b), 'image/png'));
  } finally {
    v.removeAttribute('src');
    URL.revokeObjectURL(url);
  }
}

async function prepare(key: string): Promise<void> {
  try {
    const v = await api<RenderInfo>(`/hero-render/${key}/video`, { method: 'POST' });
    if (v.video) {
      const res = await fetch(asset(`/icons/renders/${key}.webm`));
      if (res.ok) {
        const png = await firstFrame(await res.blob());
        if (png) {
          await apiBytes(`/hero-render/${key}/still`, png);
          return;
        }
      }
    }
  } catch {
    // no render, offline, or not decodable: the background is removed instead
  }
  await api(`/hero-render/${key}/segment`, { method: 'POST' });
}

export function useHeroModel(key: string | null | undefined) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['hero-render', key],
    queryFn: () => api<RenderInfo>(`/hero-render/${key}`),
    enabled: !!key,
    staleTime: Infinity,
    retry: false,
  });
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [key]);
  useEffect(() => {
    if (!key || !q.data || q.data.still) return;
    let job = preparing.get(key);
    if (!job) {
      job = prepare(key);
      preparing.set(key, job);
    }
    let alive = true;
    job.then(
      () => qc.invalidateQueries({ queryKey: ['hero-render', key] }),
      () => {
        preparing.delete(key); // try again next time the hero is opened
        if (alive) setFailed(true);
      },
    );
    return () => {
      alive = false;
    };
  }, [key, q.data, qc]);
  const d = q.data;
  return {
    still: d?.still ? asset(`/icons/renders/${key}.png?s=${d.source}`) : null,
    video: d?.still && d.source === 'render' && d.video ? asset(`/icons/renders/${key}.webm`) : null,
    color: d?.color ?? null,
    crop: d?.crop ?? null,
    frame: d?.frame ?? null,
    loading: !!key && !failed && !d?.still,
    failed,
  };
}

export function HeroModel({ heroKey, heroId, fallback, animated = false, className = '', style }: {
  heroKey: string;
  heroId: number;
  /** a picture of the hero while the model is not ready (the icon) */
  fallback?: string;
  animated?: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  const m = useHeroModel(heroKey);
  const [playing, setPlaying] = useState(false);
  useEffect(() => setPlaying(false), [heroKey]);
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<[number, number] | null>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize([el.clientWidth, el.clientHeight]));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // the video only where its model lands exactly on the still (no jump when it starts)
  const place = size && m.crop && m.frame && size[0] > 0 ? placeStill(size[0], size[1], m.crop, m.frame) : null;
  const backing = `url("/portraits/${heroId}.webp")${fallback ? `, url("${fallback}")` : ''}`;
  return (
    <div
      ref={box}
      className={`hmodel ${m.still ? 'has-model' : ''} ${m.loading ? 'is-loading' : ''} ${className}`}
      style={{ ...style, '--glow': m.color ?? 'var(--accent)' } as CSSProperties}
    >
      <div className="hmodel__card">
        <div className="hmodel__back" style={{ backgroundImage: backing }} />
        <div className="hmodel__glow" />
        <div className="hmodel__rim" />
      </div>
      <div className="hmodel__figs">
        {m.still && <img className={`hmodel__fig ${playing ? 'is-hidden' : ''}`} src={m.still} alt="" draggable={false} />}
        {animated && m.video && place && (
          <video
            className={`hmodel__vid ${playing ? '' : 'is-hidden'}`}
            style={{ left: place.video.left, top: place.video.top, width: place.video.width, height: place.video.height }}
            src={m.video}
            autoPlay
            loop
            muted
            playsInline
            onPlaying={() => setPlaying(true)}
          />
        )}
      </div>
      {!m.still && !m.loading && fallback && <img className="hmodel__flat" src={fallback} alt="" />}
    </div>
  );
}
