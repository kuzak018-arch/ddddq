/** A link to a site the app shows data from: opened in the default browser by the backend (the
 * app window has no browser of its own, so target="_blank" opens nothing there). */
import type { ReactNode } from 'react';

import { api } from '../api/client';

export function ExternalLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  return (
    <a
      className={className}
      href={href}
      rel="noreferrer"
      onClick={(e) => {
        e.preventDefault();
        void api('/open-url', { body: { url: href } }).catch(() => window.open(href, '_blank'));
      }}
    >
      {children}
    </a>
  );
}
