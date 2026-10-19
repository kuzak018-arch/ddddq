/**
 * «Фон меню»: a picture, GIF or video becomes Dota's main-menu background (and, if wanted, the
 * background behind the hero and under the hero grid). The preview is the game's screen at the
 * chosen shape with the same framing, blur and dim the video gets (lib/mods/frame.ts), so what is
 * seen is what is built. The video is made here (lib/mods/video.ts), the pack and the install are
 * the backend's (drafter/game_mods).
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { create } from 'zustand';

import { apiUpload } from '../../api/client';
import { DEFAULT_FRAME, framePlacement, mediaKind, MENU_LIMITS, MENU_SIZES, menuLook, screenAspect, fitPiece, type Aspect, type Fit, type Frame, type MediaKind } from '../../lib/mods/frame';
import { encodeMenuVideo, MenuVideoError } from '../../lib/mods/video';
import { activeGrid, useGrids } from '../../state/grids';
import { useUi } from '../../state/ui';
import { ErrorBox, Segmented, Slider, Toggle } from '../ui';
import { GridScreen, HeroScreen, MenuScreen } from './DotaScreens';
import { blocker, useModsStatus } from './ModsGate';

const HERO_OPACITY = 0.6; // drafter/game_mods/menu.py
const GRID_DIM_MAX = 0.9;

interface Source {
  file: File;
  url: string;
  kind: MediaKind;
  width: number;
  height: number;
  duration: number | null;
  fit: Fit;
  blur: number;
  dim: number;
  frame: Frame;
  piece: { start: number; end: number } | null;
  crossfade: number;
}

type Screen = 'menu' | 'hero' | 'grid';

interface BgState {
  aspect: Aspect;
  screen: Screen;
  menu: Source | null;
  hero: 'off' | 'menu' | 'own';
  heroSource: Source | null;
  grid: 'menu' | 'dim' | 'own';
  gridDim: number;
  gridSource: Source | null;
  news: boolean;
}

/** Kept for the session (files cannot go to localStorage), so switching tabs loses nothing. */
const useBg = create<BgState>(() => ({
  aspect: typeof window !== 'undefined' ? screenAspect(window.screen.width, window.screen.height) : '16:9',
  screen: 'menu',
  menu: null,
  hero: 'off',
  heroSource: null,
  grid: 'menu',
  gridDim: 0.55,
  gridSource: null,
  news: true,
}));

async function loadSource(file: File): Promise<Source> {
  if (file.size > MENU_LIMITS.bytes) throw new MenuVideoError(`Файл больше ${MENU_LIMITS.bytes / 1_000_000} МБ — возьми поменьше.`);
  const kind = mediaKind(new Uint8Array(await file.slice(0, 16).arrayBuffer()));
  if (!kind) throw new MenuVideoError('Нужна картинка (PNG, JPEG, WebP), GIF или видео (MP4, WebM).');
  const url = URL.createObjectURL(file);
  const base = { file, url, kind, fit: 'cover' as Fit, blur: 0, dim: 0.15, frame: { ...DEFAULT_FRAME }, crossfade: 0 };
  if (kind.type === 'video') {
    const v = document.createElement('video');
    v.muted = true;
    v.preload = 'metadata';
    v.src = url;
    await new Promise<void>((ok, fail) => {
      v.onloadedmetadata = () => ok();
      v.onerror = () => fail(new MenuVideoError('Видео не читается: пересохрани его в MP4 (H.264) или WebM.'));
    });
    const duration = Number.isFinite(v.duration) ? v.duration : MENU_LIMITS.seconds;
    return { ...base, width: v.videoWidth, height: v.videoHeight, duration, piece: fitPiece({ start: 0, end: duration }, duration, 'end') };
  }
  const bmp = await createImageBitmap(file).catch(() => {
    throw new MenuVideoError(`Не получилось открыть ${kind.label}.`);
  });
  const out = { ...base, width: bmp.width, height: bmp.height, duration: null, piece: null };
  bmp.close();
  return out;
}

/** A file from outside the builder (GridStudio's workshop) as the menu background. */
export async function takeBackgroundFile(file: File): Promise<void> {
  const src = await loadSource(file);
  const old = useBg.getState().menu;
  if (old) URL.revokeObjectURL(old.url);
  useBg.setState({ menu: src, screen: 'menu' });
}

/** The picture on the stage, placed as in the video; dragging moves the frame. */
function Media({ src, aspect, opacity = 1, onFrame }: { src: Source; aspect: Aspect; opacity?: number; onFrame?: (f: Frame) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [h, setH] = useState(400);
  const [W, H] = MENU_SIZES[aspect];
  const look = menuLook(src, H);
  const at = framePlacement(W / H, src.width / src.height, src.fit, look.zoom, src.frame);
  useEffect(() => {
    const ro = new ResizeObserver(() => setH(box.current?.clientHeight ?? 400));
    if (box.current) ro.observe(box.current);
    return () => ro.disconnect();
  }, []);
  // a video loops over its piece
  useEffect(() => {
    const v = video.current;
    if (!v || !src.piece) return;
    const p = src.piece;
    if (v.currentTime < p.start || v.currentTime > p.end) v.currentTime = p.start;
    const tick = () => {
      if (v.currentTime >= p.end - 0.05 || v.currentTime < p.start) v.currentTime = p.start;
    };
    v.addEventListener('timeupdate', tick);
    return () => v.removeEventListener('timeupdate', tick);
  }, [src.piece?.start, src.piece?.end]); // eslint-disable-line react-hooks/exhaustive-deps
  const drag = useRef<{ x: number; y: number; frame: Frame } | null>(null);
  const style: React.CSSProperties = {
    left: `${at.x * 100}%`,
    top: `${at.y * 100}%`,
    width: `${at.w * 100}%`,
    height: `${at.h * 100}%`,
    transform: `rotate(${at.rotate}deg) scale(${at.flipX ? -1 : 1}, ${at.flipY ? -1 : 1})`,
    filter: look.sigma ? `blur(${(look.sigma * h) / H}px)` : undefined,
  };
  return (
    <div
      ref={box}
      className={`bgb-media ${onFrame ? 'can-frame' : ''}`}
      style={{ opacity }}
      onPointerDown={(e) => {
        if (!onFrame) return;
        drag.current = { x: e.clientX, y: e.clientY, frame: src.frame };
        (e.target as Element).setPointerCapture?.(e.pointerId);
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d || !onFrame || !box.current) return;
        const r = box.current.getBoundingClientRect();
        const dx = (e.clientX - d.x) / r.width;
        const dy = (e.clientY - d.y) / r.height;
        // cx = (1 - bw)·x + bw/2: a picture moved by dx needs x + dx/(1 - bw)
        const nx = Math.abs(1 - at.bw) > 1e-6 ? d.frame.x + dx / (1 - at.bw) : d.frame.x;
        const ny = Math.abs(1 - at.bh) > 1e-6 ? d.frame.y + dy / (1 - at.bh) : d.frame.y;
        onFrame({ ...d.frame, x: Math.min(1, Math.max(0, nx)), y: Math.min(1, Math.max(0, ny)) });
      }}
      onPointerUp={() => (drag.current = null)}
    >
      {src.kind.type === 'video' ? (
        <video ref={video} src={src.url} style={style} muted loop autoPlay playsInline />
      ) : (
        <img src={src.url} style={style} alt="" draggable={false} />
      )}
      {!!look.veil && <div className="bgb-veil" style={{ opacity: look.veil }} />}
    </div>
  );
}

function SourceFields({ src, onChange, onPick, label }: { src: Source | null; onChange: (s: Source) => void; onPick: (f: File) => void; label: string }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="bgb-fields">
      <div className="row">
        <button className="btn btn--sm" onClick={() => input.current?.click()}>
          {src ? 'Другой файл…' : `${label}…`}
        </button>
        {src && (
          <span className="muted small">
            {src.kind.label}, {src.width}×{src.height}
            {src.duration ? `, ${src.duration.toFixed(1)} с` : ''}
          </span>
        )}
        <input
          ref={input}
          type="file"
          accept="image/*,video/mp4,video/webm"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = '';
            if (f) onPick(f);
          }}
        />
      </div>
      {src && (
        <>
          <Segmented
            small
            value={src.fit}
            onChange={(fit) => onChange({ ...src, fit })}
            options={[
              { value: 'cover', label: 'Заполнить экран' },
              { value: 'contain', label: 'Целиком' },
            ]}
          />
          <Slider label="Масштаб" value={src.frame.zoom} min={1} max={3} step={0.01} onChange={(zoom) => onChange({ ...src, frame: { ...src.frame, zoom } })} format={(v) => `${Math.round(v * 100)}%`} />
          <Slider label="Размытие" value={src.blur} min={0} max={1} step={0.01} onChange={(blur) => onChange({ ...src, blur })} format={(v) => `${Math.round(v * 100)}%`} />
          <Slider label="Затемнение" value={src.dim} min={0} max={1} step={0.01} onChange={(dim) => onChange({ ...src, dim })} format={(v) => `${Math.round(v * 100)}%`} />
          {src.duration && src.piece && (
            <>
              <Slider
                label="Начало отрезка"
                value={src.piece.start}
                min={0}
                max={Math.max(0, src.duration - 1)}
                step={0.1}
                onChange={(start) => onChange({ ...src, piece: fitPiece({ ...src.piece!, start }, src.duration!, 'start') })}
                format={(v) => `${v.toFixed(1)} с`}
              />
              <Slider
                label="Конец отрезка (до 30 с)"
                value={src.piece.end}
                min={1}
                max={src.duration}
                step={0.1}
                onChange={(end) => onChange({ ...src, piece: fitPiece({ ...src.piece!, end }, src.duration!, 'end') })}
                format={(v) => `${v.toFixed(1)} с`}
              />
              <Segmented
                small
                value={src.crossfade}
                onChange={(crossfade) => onChange({ ...src, crossfade })}
                options={[
                  { value: 0, label: 'Без склейки' },
                  { value: 0.5, label: '0,5 с' },
                  { value: 1, label: '1 с' },
                  { value: 2, label: '2 с' },
                ]}
              />
              <p className="hint">Видео — отрезок до 30 секунд, без звука. Склейка плавно переводит конец отрезка в его начало, чтобы шва не было видно.</p>
            </>
          )}
          <div className="row">
            <button className="btn btn--sm btn--ghost" onClick={() => onChange({ ...src, frame: { ...DEFAULT_FRAME } })}>
              Сбросить кадр
            </button>
            <span className="hint">Тяни картинку в превью, чтобы выбрать кадр.</span>
          </div>
        </>
      )}
    </div>
  );
}

export function BackgroundBuilder() {
  const st = useBg();
  const set = useBg.setState;
  const enabled = useUi((s) => s.gameMods);
  const status = useModsStatus().data;
  const grid = useGrids(activeGrid);
  const qc = useQueryClient();
  const [err, setErr] = useState<unknown>(null);
  const [progress, setProgress] = useState<{ what: string; share: number } | null>(null);
  const abort = useRef<AbortController | null>(null);
  const [W, H] = MENU_SIZES[st.aspect];

  const pick = (key: 'menu' | 'heroSource' | 'gridSource') => async (f: File) => {
    setErr(null);
    try {
      const src = await loadSource(f);
      const old = useBg.getState()[key];
      if (old) URL.revokeObjectURL(old.url);
      set({ [key]: src } as Partial<BgState>);
    } catch (e) {
      setErr(e);
    }
  };

  const install = useMutation({
    mutationFn: async () => {
      const s = useBg.getState();
      const ctl = new AbortController();
      abort.current = ctl;
      const size = MENU_SIZES[s.aspect];
      const files: Uint8Array[] = [];
      const encode = async (src: Source, what: string) => {
        const res = await encodeMenuVideo(src.file, {
          size,
          fit: src.fit,
          effects: { blur: src.blur, dim: src.dim },
          frame: src.frame,
          piece: src.piece,
          crossfade: src.crossfade,
          signal: ctl.signal,
          onProgress: (share) => setProgress({ what, share }),
        });
        files.push(res.video);
      };
      if (s.menu) await encode(s.menu, 'фон меню');
      if (s.hero === 'own' && s.heroSource) await encode(s.heroSource, 'фон за героем');
      if (s.grid === 'own' && s.gridSource) await encode(s.gridSource, 'фон под сеткой');
      setProgress({ what: 'установка', share: 1 });
      return apiUpload<{ path: string; language: string; bytes: number }>('/game-mods/background', {
        accept: true,
        has_menu: !!s.menu,
        clean: !s.news,
        hero: s.hero === 'menu' && !s.menu ? 'off' : s.hero,
        grid: s.grid === 'own' && !s.gridSource ? 'menu' : s.grid,
        grid_dim: s.gridDim * GRID_DIM_MAX,
        label: s.menu?.file.name ?? '',
      }, files);
    },
    onSettled: () => {
      setProgress(null);
      abort.current = null;
      void qc.invalidateQueries({ queryKey: ['game-mods'] });
    },
  });

  const block = blocker(status, enabled) ?? (status && !status.usable ? 'Нужна неанглийская озвучка Доты — см. выше.' : null);
  const nothing = !st.menu && st.hero !== 'own' && st.grid === 'menu' && st.news;
  const missing = (st.hero === 'own' && !st.heroSource) || (st.grid === 'own' && !st.gridSource);

  const stage = useMemo(() => {
    const menuMedia = st.menu ? <Media src={st.menu} aspect={st.aspect} onFrame={(frame) => set({ menu: { ...st.menu!, frame } })} /> : <div className="bgb-valve">Фон Доты (не меняется)</div>;
    if (st.screen === 'menu') return (<>{menuMedia}<MenuScreen news={st.news} /></>);
    if (st.screen === 'hero') {
      const src = st.hero === 'own' ? st.heroSource : st.hero === 'menu' ? st.menu : null;
      return (
        <>
          <div className="bgb-black" />
          {src ? (
            <Media src={src} aspect={st.aspect} opacity={HERO_OPACITY} onFrame={st.hero === 'own' ? (frame) => set({ heroSource: { ...st.heroSource!, frame } }) : undefined} />
          ) : (
            <div className="bgb-valve">Картинка Доты за героем</div>
          )}
          <div className="bgb-edges" />
          <HeroScreen aspect={st.aspect} />
        </>
      );
    }
    const own = st.grid === 'own' && st.gridSource;
    return (
      <>
        {own ? <Media src={st.gridSource!} aspect={st.aspect} onFrame={(frame) => set({ gridSource: { ...st.gridSource!, frame } })} /> : menuMedia}
        {st.grid === 'dim' && <div className="bgb-veil" style={{ opacity: st.gridDim * GRID_DIM_MAX }} />}
        <GridScreen grid={grid} />
      </>
    );
  }, [st, grid]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="bgb">
      <div className="bgb-stage-wrap">
        <div className="row">
          <Segmented
            value={st.screen}
            onChange={(screen) => set({ screen })}
            options={[
              { value: 'menu', label: 'Главное меню' },
              { value: 'hero', label: 'За героем' },
              { value: 'grid', label: 'Сетка героев' },
            ]}
          />
          <Segmented
            small
            value={st.aspect}
            onChange={(aspect) => set({ aspect })}
            options={(Object.keys(MENU_SIZES) as Aspect[]).map((a) => ({ value: a, label: a }))}
          />
        </div>
        <div className="bgb-stage" style={{ aspectRatio: `${W} / ${H}` }}>
          {stage}
        </div>
        <p className="hint">
          Экран {W}×{H} — видео собирается ровно таким: превью и игра совпадают. На мониторах 1440p и 4K Дота растянет его сама.
        </p>
      </div>
      <div className="bgb-side">
        {st.screen === 'menu' && (
          <>
            <h3>Главное меню</h3>
            <SourceFields src={st.menu} label="Картинка, GIF или видео" onPick={pick('menu')} onChange={(menu) => set({ menu })} />
            {st.menu && (
              <button className="btn btn--sm btn--ghost" onClick={() => set({ menu: null })}>
                Оставить фон Доты
              </button>
            )}
            <Toggle on={st.news} onChange={(news) => set({ news })} label="Колонка новостей на главной" />
          </>
        )}
        {st.screen === 'hero' && (
          <>
            <h3>За героем</h3>
            <p className="hint">Страница героя («Герои» → герой): Дота рисует модель героя поверх этой картинки.</p>
            <Segmented
              small
              value={st.hero}
              onChange={(hero) => set({ hero })}
              options={[
                { value: 'off', label: 'Как в Доте' },
                { value: 'menu', label: 'Как в меню' },
                { value: 'own', label: 'Свой фон' },
              ]}
            />
            {st.hero === 'menu' && !st.menu && <p className="warn small">Сначала выбери фон главного меню.</p>}
            {st.hero === 'own' && <SourceFields src={st.heroSource} label="Файл за героем" onPick={pick('heroSource')} onChange={(heroSource) => set({ heroSource })} />}
          </>
        )}
        {st.screen === 'grid' && (
          <>
            <h3>Под сеткой героев</h3>
            <p className="hint">Страница «Герои» с сеткой. В превью — сетка, открытая в редакторе: «{grid.name}».</p>
            <Segmented
              small
              value={st.grid}
              onChange={(g) => set({ grid: g })}
              options={[
                { value: 'menu', label: 'Как в меню' },
                { value: 'dim', label: 'Темнее' },
                { value: 'own', label: 'Свой фон' },
              ]}
            />
            {st.grid === 'dim' && <Slider label="Затемнение под сеткой" value={st.gridDim} min={0} max={1} step={0.01} onChange={(gridDim) => set({ gridDim })} format={(v) => `${Math.round(v * 100)}%`} />}
            {st.grid === 'own' && <SourceFields src={st.gridSource} label="Файл под сетку" onPick={pick('gridSource')} onChange={(gridSource) => set({ gridSource })} />}
          </>
        )}
        {!!err && <ErrorBox error={err} />}
        {install.error && !(install.error instanceof DOMException) && <ErrorBox error={install.error} />}
        {install.data && <p className="small c-good">Готово: фон стоит в {install.data.path}. Запускай Доту.</p>}
        {progress ? (
          <div className="bgb-progress">
            <div className="lane__progress">
              <i style={{ width: `${Math.round(progress.share * 100)}%` }} />
            </div>
            <p className="small">
              {progress.what === 'установка' ? 'Ставлю в Доту…' : `Собираю ${progress.what}: ${Math.round(progress.share * 100)}%`}
            </p>
            <button className="btn btn--sm btn--ghost" onClick={() => abort.current?.abort()}>
              Отменить
            </button>
          </div>
        ) : (
          <>
            <button className="btn btn--accent" disabled={!!block || nothing || missing || install.isPending} onClick={() => install.mutate()} title={block ?? undefined}>
              Собрать и поставить в Доту
            </button>
            {block && <p className="hint">{block}</p>}
            {!block && nothing && <p className="hint">Выбери фон меню или фон одной из страниц.</p>}
          </>
        )}
      </div>
    </div>
  );
}
