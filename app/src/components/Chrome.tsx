/** Window chrome: the top bar (logo, tab pill, my position, settings, window buttons) and the
 * wallpaper behind everything (picture, GIF, video, hero art or a built-in one). */
import { isTauri } from '@tauri-apps/api/core';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { ChartColumnIncreasing, Palette, ScrollText, Shield, Swords, Trophy, User, type LucideIcon } from 'lucide-react';
import { motion } from 'motion/react';
import { useEffect, useRef, useState } from 'react';

import { useHealth, useSettings } from '../api/hooks';
import { useLogoUrl } from '../lib/appIcon';
import { blurPicture, loadPicture, setGlassPicture, type Material } from '../lib/glassBackdrop';
import { lightVeilFor, lumaOfBlob, lumaOfUrl, veilFor } from '../lib/wallLuma';
import { useResolvedTheme } from '../lib/theme';
import { useUpdate } from '../lib/updates';
import { refractionSupported } from '../glass/refraction';
import { useDraft } from '../state/draft';
import { loadBackgroundFile } from '../state/bgstore';
import { useUi, type Background, type Page } from '../state/ui';
import { POS_ROLE, RoleIcon } from './DotaIcons';
import { IconClose, IconMax, IconMin, IconSettings, Ti } from './Icons';

/** The tab pill. Builds live under «Герои» (the hero page and its builds share one tab). */
export const NAV: { page: Page; label: string; icon: LucideIcon; also?: Page[] }[] = [
  { page: 'draft', label: 'Драфт', icon: Swords },
  { page: 'meta', label: 'Мета', icon: ChartColumnIncreasing },
  { page: 'hero', label: 'Герои', icon: Shield, also: ['builds'] },
  { page: 'top', label: 'Игры топов', icon: Trophy },
  { page: 'patches', label: 'Патчи', icon: ScrollText },
  { page: 'grids', label: 'Оформление', icon: Palette },
  { page: 'profile', label: 'Профиль', icon: User },
];

export function TitleBar() {
  const health = useHealth().data;
  const win = isTauri() ? getCurrentWindow() : null;
  const logo = useLogoUrl();
  const page = useUi((s) => s.page);
  const go = useUi((s) => s.go);
  const update = useUpdate((s) => (s.check?.newer ? s.check.latest : null));
  return (
    <header className="topbar" data-tauri-drag-region>
      <div className="topbar__brand" data-tauri-drag-region>
        {logo ? (
          <img className="brand-logo brand-logo--img" src={logo} alt="" draggable={false} data-tauri-drag-region />
        ) : (
          <span className="brand-logo" data-tauri-drag-region>
            <BrandMark />
          </span>
        )}
        <span className="topbar__title" data-tauri-drag-region>
          Dota Drafter
          {health?.patch && <small data-tauri-drag-region>патч {health.patch}</small>}
        </span>
      </div>

      <nav className="tabs glass" aria-label="Разделы">
        {NAV.map(({ page: p, label, icon, also }, i) => {
          const on = page === p || !!also?.includes(page);
          return (
            <button
              key={p}
              className={`tabs__item ${on ? 'is-active' : ''}`}
              onClick={() => go(p)}
              title={`${label} (Ctrl+${i + 1})`}
              aria-current={on ? 'page' : undefined}
            >
              {on && <motion.span layoutId="tab-pill" className="tabs__pill" transition={{ type: 'spring', stiffness: 380, damping: 34 }} />}
              <span className="tabs__label">
                <Ti icon={icon} />
                {label}
              </span>
            </button>
          );
        })}
      </nav>

      <div className="topbar__right" data-tauri-drag-region>
        <PositionPicker />
        <button
          className={`round-btn glass ${page === 'settings' || page === 'vision' ? 'is-active' : ''}`}
          onClick={() => go('settings')}
          title={update ? `Настройки (Ctrl+8) · доступна версия ${update}` : 'Настройки (Ctrl+8)'}
          aria-label="Настройки"
        >
          <IconSettings />
          {update && <span className="round-btn__dot" />}
        </button>
        {win && (
          <div className="winbtns">
            <button className="winbtn" aria-label="Свернуть" onClick={() => win.minimize()}>
              <IconMin />
            </button>
            <button className="winbtn" aria-label="Развернуть" onClick={() => win.toggleMaximize()}>
              <IconMax />
            </button>
            <button className="winbtn winbtn--close" aria-label="Закрыть" onClick={() => win.close()}>
              <IconClose />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

/** My position for the draft and its suggestions: round buttons with Dota's position icons. */
function PositionPicker() {
  const settings = useSettings().data;
  const d = useDraft();
  const pos = d.pos ?? settings?.pos ?? 1;
  return (
    <div className="posnav glass" role="radiogroup" aria-label="Моя позиция">
      {[1, 2, 3, 4, 5].map((p) => (
        <button
          key={p}
          role="radio"
          aria-checked={p === pos}
          className={`posnav__btn ${p === pos ? 'is-on' : ''}`}
          onClick={() => d.setPos(p)}
          title={`Моя позиция: ${p} · ${POS_ROLE[p]}`}
          aria-label={`Позиция ${p} · ${POS_ROLE[p]}`}
        >
          {p === pos && <motion.span layoutId="pos-pill" className="posnav__pill" transition={{ type: 'spring', stiffness: 380, damping: 34 }} />}
          <span>
            <RoleIcon pos={p} size={20} />
          </span>
        </button>
      ))}
    </div>
  );
}

/** The built-in logo: crossed blades on a glass lens over a Radiant-to-Dire glow (the app icon,
 * app/design/app-icon.svg; public/brand.svg is the same file). */
export function BrandMark() {
  return <img className="brand-mark" src="/brand.svg" alt="" draggable={false} data-tauri-drag-region />;
}

/** Built-in wallpapers (graphite, light, dark, night); `luma` is how bright each one is (for the glass veil). */
export const PRESETS: { id: string; name: string; css: string; luma: number }[] = [
  {
    id: 'graphite',
    name: 'Графит',
    css: 'radial-gradient(70% 70% at 30% 20%, #3a3d46 0%, transparent 60%), radial-gradient(60% 60% at 80% 90%, #22252c 0%, transparent 70%), #121316',
    luma: 0.04,
  },
  {
    id: 'light',
    name: 'Светлый',
    css: 'radial-gradient(60% 55% at 15% 10%, rgba(255, 255, 255, 0.95) 0%, transparent 70%), radial-gradient(55% 60% at 90% 95%, rgba(196, 204, 222, 0.7) 0%, transparent 70%), linear-gradient(160deg, #f4f5f8 0%, #e3e6ed 100%)',
    luma: 0.9,
  },
  {
    id: 'dark',
    name: 'Тёмный',
    css: 'radial-gradient(60% 55% at 15% 10%, rgba(255, 255, 255, 0.05) 0%, transparent 70%), radial-gradient(55% 60% at 90% 95%, rgba(80, 90, 120, 0.12) 0%, transparent 70%), linear-gradient(160deg, #111216 0%, #08090b 100%)',
    luma: 0.03,
  },
  {
    id: 'night',
    name: 'Ночь',
    css: 'radial-gradient(60% 70% at 20% 20%, #2b2f8f 0%, transparent 60%), radial-gradient(70% 70% at 85% 80%, #5a1f7a 0%, transparent 65%), #0a0b16',
    luma: 0.05,
  },
];
/** What a fresh install (and a wallpaper that is no longer offered) shows. */
export const DEFAULT_PRESET = 'night';
const GRAPHITE = PRESETS.find((p) => p.id === 'graphite')!.css;

export const heroArt = (key: string) =>
  `https://cdn.cloudflare.steamstatic.com/apps/dota2/videos/dota_react/heroes/renders/${key}.png`;

/** The user's own wallpaper file: object URL, whether it is a video, and its brightness. */
function useWallFile(bg: Background) {
  const [file, setFile] = useState<{ url: string; video: boolean; luma: number | null } | null>(null);
  useEffect(() => {
    if (bg.kind !== 'file') {
      setFile(null);
      return;
    }
    let url: string | null = null;
    let alive = true;
    loadBackgroundFile().then(async (blob) => {
      if (!blob || !alive) return;
      url = URL.createObjectURL(blob);
      const video = blob.type.startsWith('video/');
      setFile({ url, video, luma: null });
      const luma = await lumaOfBlob(blob);
      if (alive) setFile({ url, video, luma });
    });
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [bg]);
  return file;
}

/** Brightness of a hero render (null while unknown or when the CDN refuses to be read). */
function useHeroLuma(bg: Background): number | null {
  const [luma, setLuma] = useState<number | null>(null);
  useEffect(() => {
    setLuma(null);
    if (bg.kind !== 'hero') return;
    let alive = true;
    lumaOfUrl(heroArt(bg.key)).then((l) => alive && setLuma(l));
    return () => {
      alive = false;
    };
  }, [bg]);
  return luma;
}

/** Heavy background work stops: performance mode, a running match, or the window is hidden. */
export function useCalmBackground(): boolean {
  const perf = useUi((s) => s.performance);
  const phase = useDraft((s) => s.phase);
  const [hidden, setHidden] = useState(() => document.hidden);
  useEffect(() => {
    const on = () => setHidden(document.hidden);
    document.addEventListener('visibilitychange', on);
    return () => document.removeEventListener('visibilitychange', on);
  }, []);
  return perf || phase === 'game' || hidden;
}

/**
 * The blurred wallpaper under the glass panels, made once (lib/glassBackdrop.ts): a gradient as it
 * is, a picture blurred on a small canvas, a video re-blurred twice a second (paused while calm).
 * Live refraction needs the live blur, and «Как в Доте» shows no wallpaper: both clear it.
 */
function useGlassPicture(bg: Background, presetCss: string | null, file: { url: string; video: boolean } | null, video: React.RefObject<HTMLVideoElement | null>, calm: boolean) {
  const { bgPos, material, refraction } = useUi();
  const [view, setView] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    let t: ReturnType<typeof setTimeout>;
    const on = () => {
      clearTimeout(t);
      t = setTimeout(() => setView({ w: window.innerWidth, h: window.innerHeight }), 300);
    };
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, []);
  const liveBlur = refraction && refractionSupported;
  useEffect(() => {
    if (liveBlur || material === 'dota') return setGlassPicture(null);
    if (presetCss) return setGlassPicture(presetCss);
    const url = bg.kind === 'hero' ? heroArt(bg.key) : file?.url;
    if (!url) return setGlassPicture(null);
    let alive = true;
    const m = material as Material;
    if (file?.video) {
      const tick = () => {
        const v = video.current;
        if (!alive || !v || !v.videoWidth) return;
        const d = blurPicture(v, v.videoWidth, v.videoHeight, view, bgPos, m);
        setGlassPicture(d ? `url("${d}")` : null, true);
      };
      const v = video.current;
      v?.addEventListener('loadeddata', tick);
      tick();
      const timer = calm ? undefined : setInterval(tick, 500);
      return () => {
        alive = false;
        v?.removeEventListener('loadeddata', tick);
        clearInterval(timer);
      };
    }
    void loadPicture(url).then((img) => {
      if (!alive) return;
      const d = img ? blurPicture(img, img.naturalWidth, img.naturalHeight, view, bgPos, m) : null;
      setGlassPicture(d ? `url("${d}")` : null, true); // null: the live blur stays (the picture can't be read)
    });
    return () => {
      alive = false;
    };
  }, [liveBlur, material, presetCss, bg, file?.url, file?.video, video, view, bgPos, calm]);
}

export function Wallpaper() {
  const { background: bg, bgBlur, bgDim, bgPos, theme } = useUi();
  const dark = useResolvedTheme(theme) === 'dark';
  const calm = useCalmBackground();
  const file = useWallFile(bg);
  const heroLuma = useHeroLuma(bg);
  const video = useRef<HTMLVideoElement>(null);
  const pos = `${bgPos.x}% ${bgPos.y}%`;
  const blur = calm ? 0 : bgBlur;

  const fallback = PRESETS.find((x) => x.id === DEFAULT_PRESET) ?? PRESETS[0]!;
  let css = fallback.css;
  let luma: number | null = fallback.luma;
  if (bg.kind === 'preset') {
    const p = PRESETS.find((x) => x.id === bg.id) ?? PRESETS.find((x) => x.id === DEFAULT_PRESET) ?? PRESETS[0]!;
    css = p.css;
    luma = p.luma;
  } else if (bg.kind === 'hero') {
    css = `url("${heroArt(bg.key)}") ${pos} / cover no-repeat, ${GRAPHITE}`;
    luma = heroLuma ?? 0.2; // renders are mostly dark; until measured, a careful guess
  } else if (file && !file.video) {
    css = `url("${file.url}") ${pos} / cover no-repeat, #111`;
    luma = file.luma ?? 0.3;
  } else if (file?.video) {
    css = '#0b0b10';
    luma = file.luma ?? 0.3;
  }

  useGlassPicture(bg, bg.kind === 'preset' ? css : null, file, video, calm);
  useEffect(() => {
    document.documentElement.style.setProperty('--wall-dim', String(bgDim));
  }, [bgDim]);

  // glass veil from the wallpaper's brightness: only the dark theme has white text on the glass
  useEffect(() => {
    // dark theme: black under white text on bright pictures; light theme: white under dark text on dark ones
    document.documentElement.style.setProperty('--veil', (dark ? veilFor(luma ?? 0.3, bgDim) : lightVeilFor(luma ?? 0.3, bgDim)).toFixed(3));
  }, [luma, bgDim, dark]);

  // a video background stops in performance mode and during a match (first frame stays)
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    if (calm) v.pause();
    else void v.play().catch(() => undefined);
  }, [calm, file?.url]);

  const style = { filter: blur ? `blur(${blur}px)` : undefined, transform: blur ? 'scale(1.06)' : undefined };
  return (
    <div className="wallpaper" aria-hidden>
      {file?.video ? (
        <video
          ref={video}
          className="wallpaper__image wallpaper__video"
          src={file.url}
          style={{ ...style, objectPosition: pos }}
          autoPlay={!calm}
          loop
          muted
          playsInline
        />
      ) : (
        <div className="wallpaper__image" style={{ ...style, background: css }} />
      )}
      <div className="wallpaper__dim" style={{ background: `rgba(0,0,0,${bgDim})` }} />
    </div>
  );
}
