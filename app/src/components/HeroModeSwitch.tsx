/** «Герои» holds two views: the hero page and its builds. The switch keeps the chosen hero. */
import { Hammer, Shield } from 'lucide-react';

import { useUi } from '../state/ui';
import { Ti } from './Icons';
import { Segmented } from './ui';

export function HeroModeSwitch() {
  const { page, heroPageId, buildHero, set } = useUi();
  return (
    <Segmented
      value={page === 'builds' ? 'builds' : 'hero'}
      onChange={(v) =>
        v === 'builds'
          ? set({ page: 'builds', buildHero: buildHero ?? heroPageId })
          : set({ page: 'hero', heroPageId: heroPageId ?? buildHero })
      }
      options={[
        { value: 'hero', label: <><Ti icon={Shield} />Герой</> },
        { value: 'builds', label: <><Ti icon={Hammer} />Билды</> },
      ]}
    />
  );
}
