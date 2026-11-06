/**
 * My position, one for the whole app: the round buttons in the top bar, the draft's suggestions,
 * the builds and the hero page all read and change this one (the draft board's position, else
 * the one in the settings).
 */
import { useSettings } from '../api/hooks';
import { useDraft } from './draft';

export function useMyPos(): [number, (p: number) => void] {
  const settings = useSettings().data;
  const pos = useDraft((s) => s.pos);
  const setPos = useDraft((s) => s.setPos);
  return [pos ?? settings?.pos ?? 1, setPos];
}
