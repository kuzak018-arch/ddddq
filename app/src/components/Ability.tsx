/** Ability and talent icons for builds: the game's icon from the local cache, or a drawn badge. */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api, asset, subscribe } from '../api/client';
import type { AbilityInfo } from '../api/types';

/** Dota's own talent and innate glyphs (backend ui_icons.py), when downloaded; else null. */
export function useUiIcons() {
  const qc = useQueryClient();
  useEffect(() => subscribe((e) => e.type === 'ui-icons' && void qc.invalidateQueries({ queryKey: ['ui-icons'] })), [qc]);
  return useQuery({
    queryKey: ['ui-icons'],
    staleTime: Infinity,
    retry: false,
    queryFn: () => api<{ talent: string | null; innate: string | null }>('/ui-icons'),
  }).data;
}

/** Initials for an ability without an icon ("Mana Break" -> "MB", "Blink" -> "Bl"). */
export const abbr = (name: string) => {
  const w = name.split(/[\s-]+/).filter((x) => /^\p{L}/u.test(x));
  return w.length >= 2 ? (w[0]![0]! + w[1]![0]!).toUpperCase() : name.slice(0, 2);
};

export function AbilityIcon({ info, name, size = 32 }: { info?: AbilityInfo | null; name?: string; size?: number }) {
  const [broken, setBroken] = useState(false);
  const label = info?.name ?? name ?? '';
  if (info?.icon && !broken)
    return (
      <img
        className="ability-icon"
        src={asset(info.icon)}
        alt={label}
        width={size}
        height={size}
        draggable={false}
        onError={() => setBroken(true)}
      />
    );
  // innate abilities have no icon of their own on Valve's CDN: the game's innate mark, or a drawn badge
  if (info?.innate) return <InnateIcon size={size} label={label} />;
  return (
    <span className={`ability-icon ability-icon--badge ${info?.innate ? 'is-innate' : ''}`} style={{ width: size, height: size }} aria-label={label}>
      {abbr(label)}
    </span>
  );
}

/** The talent tree glyph (a level where a talent is taken, or a talent with no ability of its own). */
/** Dota's innate-ability mark (the same for every hero), else a hexagon badge with the initials. */
export function InnateIcon({ size = 32, label = 'Врождённая' }: { size?: number; label?: string }) {
  const icons = useUiIcons();
  const [broken, setBroken] = useState(false);
  if (icons?.innate && !broken)
    return (
      <span className="ability-icon ability-icon--glyph is-innate" style={{ width: size, height: size }} title={label}>
        <img src={asset(icons.innate)} alt={label} width={size * 0.78} height={size * 0.78} draggable={false} onError={() => setBroken(true)} />
      </span>
    );
  return (
    <span className="ability-icon ability-icon--badge is-innate" style={{ width: size, height: size }} aria-label={label}>
      {abbr(label)}
    </span>
  );
}

export function TalentIcon({ size = 32 }: { size?: number }) {
  const icons = useUiIcons();
  const [broken, setBroken] = useState(false);
  if (icons?.talent && !broken)
    return (
      <span className="ability-icon ability-icon--glyph ability-icon--talent" style={{ width: size, height: size }} aria-label="Талант">
        <img src={asset(icons.talent)} alt="Талант" width={size * 0.8} height={size * 0.8} draggable={false} onError={() => setBroken(true)} />
      </span>
    );
  return (
    <span className="ability-icon ability-icon--talent" style={{ width: size, height: size }} aria-label="Талант">
      <svg viewBox="0 0 24 24" width={size * 0.62} height={size * 0.62} aria-hidden>
        <path
          d="M12 21V11m0 0L7 6m5 5 5-5M7 6V3m0 3H4m13 0V3m0 3h3M12 11V7"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}
