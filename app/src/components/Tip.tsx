/**
 * Hover tooltip rendered into <body>: panels clip their content (overflow hidden for the glass),
 * so a tooltip inside them would be cut. Shows on pointer hover and on keyboard focus.
 */
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export function Tip({ content, children, className = '' }: { content: ReactNode; children: ReactNode; className?: string }) {
  const anchor = useRef<HTMLSpanElement>(null);
  const tip = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number; below: boolean } | null>(null);

  useLayoutEffect(() => {
    if (!open || !anchor.current || !tip.current) return;
    const a = anchor.current.getBoundingClientRect();
    const t = tip.current.getBoundingClientRect();
    const gap = 8;
    // above the anchor when it fits, otherwise below; kept inside the window horizontally
    const below = a.top - t.height - gap < 4;
    const top = below ? a.bottom + gap : a.top - t.height - gap;
    const left = Math.min(window.innerWidth - t.width - 6, Math.max(6, a.left + a.width / 2 - t.width / 2));
    setPos({ left, top, below });
  }, [open]);

  return (
    <span
      ref={anchor}
      className={`tip-anchor ${className}`}
      onPointerEnter={() => setOpen(true)}
      onPointerLeave={() => {
        setOpen(false);
        setPos(null);
      }}
      onFocus={() => setOpen(true)}
      onBlur={() => {
        setOpen(false);
        setPos(null);
      }}
    >
      {children}
      {open &&
        createPortal(
          <div
            ref={tip}
            role="tooltip"
            className={`tip ${pos ? 'is-shown' : ''} ${pos?.below ? 'is-below' : ''}`}
            style={pos ? { left: pos.left, top: pos.top } : { left: -9999, top: -9999 }}
          >
            {content}
          </div>,
          document.body,
        )}
    </span>
  );
}
