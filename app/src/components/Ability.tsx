/** Ability and talent icons for builds: the game's icon from the local cache, or a drawn badge. */
import { useState } from 'react';

import { asset } from '../api/client';
import type { AbilityInfo } from '../api/types';

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
  // innate abilities have no icon on Valve's CDN: a hexagon badge like the game's own
  return (
    <span className={`ability-icon ability-icon--badge ${info?.innate ? 'is-innate' : ''}`} style={{ width: size, height: size }} aria-label={label}>
      {abbr(label)}
    </span>
  );
}

/** The talent tree glyph (a level where a talent is taken, or a talent with no ability of its own). */
export function TalentIcon({ size = 32 }: { size?: number }) {
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
