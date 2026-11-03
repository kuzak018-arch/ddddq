/**
 * Dota's own icons (public/dota-icons, see its README): attributes, rank medals and Dota Plus.
 * Positions are not pictograms: a number with the role's name («1 Керри», PosTag).
 */
import { medalFor, rankName } from '../lib/ranks';

export const POS_ROLE = ['', 'Керри', 'Мид', 'Хард', 'Роумер', 'Саппорт'];

/** A position: its number and, unless `bare`, the role's name — «1 Керри». */
export function PosTag({ pos, bare, className = '' }: { pos: number; bare?: boolean; className?: string }) {
  return (
    <span className={`pos-tag ${className}`} title={bare ? `Позиция ${pos} · ${POS_ROLE[pos] ?? ''}` : undefined}>
      <b>{pos}</b>
      {!bare && POS_ROLE[pos] && <span>{POS_ROLE[pos]}</span>}
    </span>
  );
}

const ATTR: Record<string, string> = { str: 'Сила', agi: 'Ловкость', int: 'Интеллект', all: 'Универсальный' };

export function AttrIcon({ attr, size = 16, className = '' }: { attr: string; size?: number; className?: string }) {
  if (!ATTR[attr]) return null;
  return (
    <img
      className={`attr-ico ${className}`}
      src={`/dota-icons/attr/${attr}.png`}
      width={size}
      height={size}
      alt={ATTR[attr]}
      title={ATTR[attr]}
      draggable={false}
    />
  );
}

/** A rank medal as in the client: the medal, its stars, and the leaderboard place for Immortals. */
export function RankMedal({ tier, leaderboard, size = 56, className = '' }: {
  tier: number | null | undefined;
  leaderboard?: number | null;
  size?: number;
  className?: string;
}) {
  const { medal, stars } = medalFor(tier, leaderboard);
  const name = `${rankName(tier)}${leaderboard ? ` · #${leaderboard} в таблице лидеров` : ''}`;
  return (
    <span className={`rank-medal ${className}`} style={{ width: size, height: size }} title={name} role="img" aria-label={name}>
      <img src={`/dota-icons/ranks/medal_${medal}.webp`} alt="" draggable={false} />
      {stars > 0 && <img src={`/dota-icons/ranks/stars_${stars}.webp`} alt="" draggable={false} />}
      {!!leaderboard && medal.startsWith('8') && <b className="rank-medal__place" style={{ fontSize: Math.max(9, Math.round(size * 0.19)) }}>{leaderboard}</b>}
    </span>
  );
}

export function PlusBadge({ size = 22 }: { size?: number }) {
  return <img className="plus-badge" src="/dota-icons/plus.webp" height={size} alt="Dota Plus" title="Dota Plus" draggable={false} />;
}
