import type { ReactNode } from 'react';

/**
 * A flat block of the settings' right column: no glass, no backdrop-filter, no animation, no
 * scrolling of its own (see SettingsPage for why the column is kept this plain).
 */
export function Section({ children }: { children: ReactNode }) {
  return <section className="settings-section">{children}</section>;
}
