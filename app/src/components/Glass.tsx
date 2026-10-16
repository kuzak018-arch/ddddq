import { useEffect, useRef, type CSSProperties, type ElementType, type ReactNode } from 'react';

import { refract } from '../glass/refraction';
import { useUi } from '../state/ui';

interface Props {
  as?: ElementType;
  className?: string;
  style?: CSSProperties;
  /** Edge refraction for top-level panels (nested glass would only refract its parent). */
  refracting?: boolean;
  strong?: boolean;
  inset?: boolean;
  children?: ReactNode;
  [k: string]: unknown;
}

export function Glass({ as: Tag = 'div', className = '', refracting, strong, inset, children, ...rest }: Props) {
  const ref = useRef<HTMLElement>(null);
  const on = useUi((s) => s.refraction && !s.performance);
  useEffect(() => {
    if (!refracting || !on || !ref.current) return;
    return refract(ref.current, { bezel: 20, scale: 30 });
  }, [refracting, on]);
  const cls = ['glass', strong && 'glass--strong', inset && 'glass--inset', className].filter(Boolean).join(' ');
  return (
    <Tag ref={ref} className={cls} {...rest}>
      {children}
    </Tag>
  );
}

/** Pointer-following highlight for .btn elements (one listener for the whole app). */
export function installButtonSheen(): void {
  document.addEventListener('pointermove', (e) => {
    const el = (e.target as HTMLElement | null)?.closest?.('.btn') as HTMLElement | null;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty('--mx', `${e.clientX - r.left}px`);
    el.style.setProperty('--my', `${e.clientY - r.top}px`);
  });
}
