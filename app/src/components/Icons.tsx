import { RotateCw, Search, Settings, type LucideIcon } from './glyphs';
import type { SVGProps } from 'react';

const base = (p: SVGProps<SVGSVGElement>) => ({
  width: 22,
  height: 22,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  ...p,
});

export const IconSettings = (p: { width?: number }) => <Settings size={p.width ?? 20} />;
/** Telegram's paper plane, as a line icon like the others. */
export const IconTelegram = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base(p)}>
    <path d="M21.2 4.1 2.9 11.2c-.8.3-.8 1.4 0 1.7l4.5 1.5 1.7 5.3c.2.7 1.1.9 1.6.4l2.6-2.4 4.6 3.4c.6.5 1.5.1 1.7-.6L22.5 5.3c.2-.8-.6-1.5-1.3-1.2Z" />
    <path d="m7.4 14.4 10-6.6-7.3 7.6" />
  </svg>
);

export const IconSearch = (p: { width?: number }) => <Search size={p.width ?? 18} />;
export const IconClose = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base({ width: 14, height: 14, strokeWidth: 2, ...p })}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);
export const IconMin = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base({ width: 14, height: 14, strokeWidth: 2, ...p })}>
    <path d="M5 12h14" />
  </svg>
);
export const IconMax = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base({ width: 13, height: 13, strokeWidth: 2, ...p })}>
    <rect x="4" y="4" width="16" height="16" rx="3" />
  </svg>
);
export const IconReset = (p: { width?: number }) => <RotateCw size={p.width ?? 16} />;

/** An icon in front of a label (a Dota glyph, components/glyphs.tsx), sized to the text (CSS .ti). */
export function Ti({ icon: I, className = '' }: { icon: LucideIcon; className?: string }) {
  return <I className={`ti ${className}`} aria-hidden strokeWidth={1.9} />;
}
