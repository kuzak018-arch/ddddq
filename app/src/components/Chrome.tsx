/** Window chrome: custom title bar, navigation dock and the wallpaper behind everything. */
import { isTauri } from '@tauri-apps/api/core';
import { getCurrentWindow } from '@tauri-apps/api/window';
import { motion } from 'motion/react';
import { useEffect, useState } from 'react';

import { useHealth } from '../api/hooks';
import { useLogoUrl } from '../lib/appIcon';
import { useUpdates } from '../lib/updates';
import { loadBackgroundFile } from '../state/bgstore';
import { useUi, type Background, type Page } from '../state/ui';
import { Effects } from './Effects';
import { Glass } from './Glass';
import { IconBuild, IconClose, IconDraft, IconHero, IconMax, IconMeta, IconMin, IconProfile, IconSettings } from './Icons';

export function TitleBar() {
  const health = useHealth().data;
  const win = isTauri() ? getCurrentWindow() : null;
  const logo = useLogoUrl();
  const update = useUpdates((s) => (s.status === 'available' ? s.version : null));
  const go = useUi((s) => s.go);
  return (
    <header className="titlebar" data-tauri-drag-region>
      <div className="titlebar__brand" data-tauri-drag-region>
        {logo ? (
          <img className="titlebar__logo titlebar__logo--img" src={logo} alt="" draggable={false} data-tauri-drag-region />
        ) : (
          <span className="titlebar__logo" />
        )}
        Dota Drafter
        {health?.patch && <span className="titlebar__meta">патч {health.patch}</span>}
        {update && (
          <button className="titlebar__update" onClick={() => go('settings')} title="Открыть настройки, чтобы обновиться">
            Обновление {update}
          </button>
        )}
      </div>
      {win && (
        <div className="titlebar__buttons">
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
    </header>
  );
}

const NAV: { page: Page; label: string; Icon: typeof IconDraft }[] = [
  { page: 'draft', label: 'Драфт', Icon: IconDraft },
  { page: 'meta', label: 'Мета', Icon: IconMeta },
  { page: 'hero', label: 'Герой', Icon: IconHero },
  { page: 'builds', label: 'Билды', Icon: IconBuild },
  { page: 'profile', label: 'Профиль', Icon: IconProfile },
  { page: 'settings', label: 'Настройки', Icon: IconSettings },
];

export function Dock() {
  const page = useUi((s) => s.page);
  const go = useUi((s) => s.go);
  return (
    <Glass as="nav" className="dock" refracting>
      {NAV.map(({ page: p, label, Icon }, i) => {
        // the screen-reading wizard is opened from settings: keep settings lit there
        const on = page === p || (p === 'settings' && page === 'vision');
        return (
        <button
          key={p}
          className={`dock__item ${on ? 'is-active' : ''}`}
          onClick={() => go(p)}
          title={`${label} (Ctrl+${i + 1})`}
          aria-current={on ? 'page' : undefined}
        >
          {on && <motion.span layoutId="dock-pill" className="dock__pill" />}
          <Icon />
          <span>{label}</span>
        </button>
        );
      })}
    </Glass>
  );
}

export const PRESETS: { id: string; name: string; css: string }[] = [
  {
    id: 'dire',
    name: 'Dire',
    css: 'radial-gradient(60% 70% at 85% 15%, #8f1d14 0%, transparent 60%), radial-gradient(70% 70% at 10% 90%, #3a0d26 0%, transparent 65%), radial-gradient(50% 50% at 50% 50%, #2a1410 0%, transparent 70%), #0e0a0c',
  },
  {
    id: 'radiant',
    name: 'Radiant',
    css: 'radial-gradient(60% 70% at 15% 15%, #1f7a4d 0%, transparent 60%), radial-gradient(70% 70% at 90% 85%, #0f4a5e 0%, transparent 65%), radial-gradient(40% 40% at 60% 40%, #24533a 0%, transparent 70%), #08110e',
  },
  {
    id: 'night',
    name: 'Ночь',
    css: 'radial-gradient(60% 70% at 20% 20%, #2b2f8f 0%, transparent 60%), radial-gradient(70% 70% at 85% 80%, #5a1f7a 0%, transparent 65%), #0a0b16',
  },
  {
    id: 'aurora',
    name: 'Аврора',
    css: 'radial-gradient(50% 60% at 15% 30%, #0f8b8d 0%, transparent 60%), radial-gradient(60% 60% at 70% 20%, #6a3fd0 0%, transparent 60%), radial-gradient(60% 60% at 70% 90%, #c2367a 0%, transparent 60%), #0b0d18',
  },
  {
    id: 'sunrise',
    name: 'Рассвет',
    css: 'radial-gradient(60% 60% at 20% 20%, #ffb86b 0%, transparent 60%), radial-gradient(60% 60% at 85% 30%, #ff7aa2 0%, transparent 60%), radial-gradient(70% 70% at 50% 100%, #7aa8ff 0%, transparent 65%), #f3eef0',
  },
  {
    id: 'graphite',
    name: 'Графит',
    css: 'radial-gradient(70% 70% at 30% 20%, #3a3d46 0%, transparent 60%), radial-gradient(60% 60% at 80% 90%, #22252c 0%, transparent 70%), #121316',
  },
];

export const heroArt = (key: string) =>
  `https://cdn.cloudflare.steamstatic.com/apps/dota2/videos/dota_react/heroes/renders/${key}.png`;

function useBackgroundCss(bg: Background): string {
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  useEffect(() => {
    if (bg.kind !== 'file') return;
    let url: string | null = null;
    loadBackgroundFile().then((blob) => {
      if (blob) setFileUrl((url = URL.createObjectURL(blob)));
    });
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [bg]);
  const fallback = PRESETS[0]!.css;
  if (bg.kind === 'preset') return PRESETS.find((p) => p.id === bg.id)?.css ?? fallback;
  if (bg.kind === 'hero') return `url("${heroArt(bg.key)}") center 20% / cover no-repeat, ${PRESETS[5]!.css}`;
  return fileUrl ? `url("${fileUrl}") center / cover no-repeat, #111` : fallback;
}

export function Wallpaper() {
  const { background, bgBlur, bgDim, performance } = useUi();
  const css = useBackgroundCss(background);
  const blur = performance ? 0 : bgBlur;
  return (
    <div className="wallpaper" aria-hidden>
      <div
        className="wallpaper__image"
        style={{ background: css, filter: blur ? `blur(${blur}px)` : undefined, transform: blur ? 'scale(1.06)' : undefined }}
      />
      <div className="wallpaper__dim" style={{ background: `rgba(0,0,0,${bgDim})` }} />
      <Effects />
    </div>
  );
}
