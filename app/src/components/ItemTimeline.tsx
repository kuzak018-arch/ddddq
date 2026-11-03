/** A build as a timeline: the items in the order they are bought, each with its minute under it,
 * joined by arrows — «Battle Fury 12:24 → Manta Style 18:42 → Butterfly 24:54». Used by the builds
 * (BuildView) and the overlay's «Билд». */
import { fmtPct, ItemIcon } from './ui';

export interface TimelineStep {
  key: string;
  name: string;
  minute: number | null;
  /** what the minute is: «у топов» or the bracket's median (the tooltip) */
  title?: string;
  share?: number;
  alternatives?: { key: string; name: string; share: number }[];
}

export const clock = (m: number) => {
  const s = Math.round(m * 60);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

/** Items without a minute keep their place after the timed ones. */
export const byMinute = <T extends { minute: number | null }>(xs: T[]) =>
  xs.map((x, i) => ({ x, i })).sort((a, b) => (a.x.minute ?? Infinity) - (b.x.minute ?? Infinity) || a.i - b.i).map((v) => v.x);

export function ItemTimeline({ steps, size = 36, compact }: { steps: TimelineStep[]; size?: number; compact?: boolean }) {
  return (
    <ol className={`tl ${compact ? 'tl--compact' : ''}`}>
      {steps.map((s, i) => (
        <li key={`${s.key}${i}`} className="tl__step" title={[s.name, s.title, s.share != null ? `${fmtPct(s.share, 0)} игр` : ''].filter(Boolean).join(' · ')}>
          <ItemIcon k={s.key} title={s.name} size={size} />
          <b className="tl__time">{s.minute != null ? clock(s.minute) : '—'}</b>
          {!compact && <span className="tl__name">{s.name}</span>}
          {!compact && s.share != null && <small className="tl__share">{fmtPct(s.share, 0)} игр</small>}
          {!compact && s.alternatives && s.alternatives.length > 0 && (
            <span className="tl__alts">
              или
              {s.alternatives.map((a) => (
                <span key={a.key} title={`${a.name}: ${fmtPct(a.share, 0)} игр`}>
                  <ItemIcon k={a.key} title={a.name} size={18} />
                </span>
              ))}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}
