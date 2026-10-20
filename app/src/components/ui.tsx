/** Small shared pieces: icons, segmented control, toggle, slider, win bar, sparkline, explanations. */
import { motion, useSpring, useTransform } from 'motion/react';
import { useEffect, useId, type ReactNode } from 'react';

import { asset } from '../api/client';
import { useHeroes } from '../api/hooks';
import type { Term } from '../api/types';

export function HeroIcon({ id, size = 'md', dim, onClick, title }: {
  id: number | null;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  dim?: boolean;
  onClick?: () => void;
  title?: string;
}) {
  const hero = useHeroes().data?.byId.get(id ?? -1);
  return (
    <span
      className={`hero-icon hero-icon--${size} ${dim ? 'is-dim' : ''} ${onClick ? 'is-clickable' : ''}`}
      onClick={onClick}
      title={title ?? hero?.name}
    >
      {hero && <img src={asset(hero.icon)} alt={hero.name} draggable={false} loading="lazy" />}
    </span>
  );
}

export function ItemIcon({ k, title, size = 36 }: { k: string; title?: string; size?: number }) {
  return (
    <img
      className="item-icon"
      src={asset(`/icons/items/${k}.png`)}
      alt={title ?? k}
      title={title}
      style={{ width: size * 1.36, height: size }}
      loading="lazy"
      draggable={false}
    />
  );
}

export function Segmented<T extends string | number | null>({ value, options, onChange, small }: {
  value: T;
  options: { value: T; label: ReactNode; title?: string }[];
  onChange: (v: T) => void;
  small?: boolean;
}) {
  const id = useId(); // the thumb slides between options of this control only
  return (
    <div className={`segmented glass glass--inset ${small ? 'segmented--sm' : ''}`} role="radiogroup">
      {options.map((o) => (
        <button
          key={String(o.value)}
          role="radio"
          aria-checked={o.value === value}
          title={o.title}
          className={`segmented__opt ${o.value === value ? 'is-on' : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.value === value && (
            <motion.span layoutId={id} className="segmented__thumb" transition={{ type: 'spring', stiffness: 340, damping: 32, mass: 0.9 }} />
          )}
          <span className="segmented__label">{o.label}</span>
        </button>
      ))}
    </div>
  );
}

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <label className="toggle">
      <span className="toggle__label">{label}</span>
      <button role="switch" aria-checked={on} className={`toggle__track ${on ? 'is-on' : ''}`} onClick={() => onChange(!on)}>
        <span className="toggle__knob" />
      </button>
    </label>
  );
}

export function Slider({ value, min, max, step, onChange, label, format }: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  label: ReactNode;
  format?: (v: number) => string;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <label className="slider">
      <span className="slider__head">
        <span>{label}</span>
        <span className="slider__value">{format ? format(value) : value}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        style={{ '--pct': `${pct}%` } as React.CSSProperties}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}

/** A percentage that counts smoothly to its new value instead of jumping. */
export function AnimatedPercent({ value, className, digits = 1 }: { value: number; className?: string; digits?: number }) {
  const mv = useSpring(value, { stiffness: 90, damping: 20, mass: 1 });
  const text = useTransform(mv, (v) => `${(v * 100).toFixed(digits)}%`);
  useEffect(() => mv.set(value), [mv, value]);
  return <motion.div className={className}>{text}</motion.div>;
}

export const fmtPct =(x: number | null | undefined, digits = 1) =>
  x === null || x === undefined ? '—' : `${(x * 100).toFixed(digits)}%`;

export const fmtSigned = (x: number, digits = 1) => `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(digits)}`;

export function TermLine({ t, omit }: { t: Term; omit?: number }) {
  const good = t.value >= 0;
  const text = t.text.replace(/\s[+−-]?\d+(\.\d+)?%$/, '');
  return (
    <li className={`term ${good ? 'is-good' : 'is-bad'}`}>
      <span className="term__heroes">
        {t.heroes.filter((h) => h !== omit).slice(0, 3).map((h) => (
          <HeroIcon key={h} id={h} size="sm" />
        ))}
      </span>
      <span className="term__text">{text}</span>
      <span className="term__pct">{fmtSigned(t.pct)}%</span>
    </li>
  );
}

export function Sparkline({ values, width = 84, height = 24 }: { values: (number | null)[]; width?: number; height?: number }) {
  const pts = values.map((v, i) => [i, v] as const).filter((p): p is readonly [number, number] => p[1] !== null);
  if (pts.length < 2) return <svg width={width} height={height} />;
  const ys = pts.map((p) => p[1]);
  const lo = Math.min(...ys, 0.5) - 0.005;
  const hi = Math.max(...ys, 0.5) + 0.005;
  const x = (i: number) => (i / (values.length - 1)) * (width - 4) + 2;
  const y = (v: number) => height - 2 - ((v - lo) / (hi - lo)) * (height - 4);
  const d = pts.map(([i, v], k) => `${k ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const up = ys[ys.length - 1]! >= ys[0]!;
  return (
    <svg className="sparkline" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <line x1="0" x2={width} y1={y(0.5)} y2={y(0.5)} className="sparkline__mid" />
      <path d={d} className={up ? 'sparkline__up' : 'sparkline__down'} />
    </svg>
  );
}

/** Russian noun form for a count: plural(163, 'линия', 'линии', 'линий') -> 'линии'. */
export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

/** A small spinner with a line of text while something loads (instead of an empty area). */
export function Loading({ children = 'Загрузка…', inline }: { children?: ReactNode; inline?: boolean }) {
  return (
    <div className={`loading ${inline ? 'loading--inline' : ''}`} role="status">
      <span className="spinner spinner--sm" aria-hidden />
      <span>{children}</span>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  return <div className="error-box">{error instanceof Error ? error.message : String(error)}</div>;
}
