/** «Герои» holds two views: the hero page and its builds. The switch keeps the chosen hero. */
import { useUi } from '../state/ui';
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
        { value: 'hero', label: 'Герой' },
        { value: 'builds', label: 'Билды' },
      ]}
    />
  );
}
