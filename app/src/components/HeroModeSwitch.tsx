/** «Герои» holds three views of one hero: the overview, its build and top players' games. The
 * hero is picked once (ui.heroPageId) and stays when the view changes. */
import { ChartColumnIncreasing, Hammer, ScrollText, Shield, Trophy } from './glyphs';

import { DEMO } from '../demo/api';
import { useUi } from '../state/ui';
import { Ti } from './Icons';
import { Segmented } from './ui';

type View = 'hero' | 'builds' | 'top';

export function HeroModeSwitch() {
  const page = useUi((s) => s.page);
  const go = useUi((s) => s.go);
  const value: View = page === 'builds' || page === 'top' ? page : 'hero';
  return (
    <Segmented
      value={value}
      onChange={(v: View) => go(v)}
      options={[
        { value: 'hero' as View, label: <><Ti icon={Shield} />Обзор</> },
        { value: 'builds' as View, label: <><Ti icon={Hammer} />Билд</> },
        ...(DEMO ? [] : [{ value: 'top' as View, label: <><Ti icon={Trophy} />Игры топов</> }]),
      ]}
    />
  );
}

/** «Мета» holds the tier list and the patch notes. */
export function MetaModeSwitch() {
  const page = useUi((s) => s.page);
  const go = useUi((s) => s.go);
  if (DEMO) return null;
  return (
    <Segmented
      value={page === 'patches' ? 'patches' : 'meta'}
      onChange={(v: 'meta' | 'patches') => go(v)}
      options={[
        { value: 'meta' as const, label: <><Ti icon={ChartColumnIncreasing} />Тир-лист</> },
        { value: 'patches' as const, label: <><Ti icon={ScrollText} />Патчи</> },
      ]}
    />
  );
}
