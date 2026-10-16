/**
 * Keeps the draft identical in every window (main, overlay) through the backend's /session:
 * local edits are PUT (debounced), changes from other windows / GSI arrive as "session" events.
 */
import { api, subscribe } from '../api/client';
import { useDraft } from './draft';

interface SessionDto {
  allies: (number | null)[];
  enemies: (number | null)[];
  bans: number[];
  side: 'radiant' | 'dire' | null;
  pos: number | null;
  comfort: boolean | null;
  my_hero: number | null;
  phase: 'idle' | 'draft' | 'game';
  rev: number;
  source: string;
}

const CLIENT = `${location.hash.includes('overlay') ? 'overlay' : 'main'}-${Math.random().toString(36).slice(2, 8)}`;
let applying = false;
let last: SessionDto | null = null;

function apply(s: SessionDto) {
  last = s;
  applying = true;
  useDraft.setState({
    allies: s.allies,
    enemies: s.enemies,
    bans: s.bans,
    side: s.side,
    pos: s.pos,
    comfort: s.comfort,
    phase: s.phase,
    myHero: s.my_hero,
  });
  applying = false;
}

let timer: ReturnType<typeof setTimeout> | null = null;
function push() {
  if (timer) clearTimeout(timer);
  timer = setTimeout(async () => {
    const d = useDraft.getState();
    const body = {
      allies: d.allies,
      enemies: d.enemies,
      bans: d.bans,
      side: d.side,
      pos: d.pos,
      comfort: d.comfort,
      my_hero: last?.my_hero ?? null,
      phase: last?.phase ?? 'idle',
      source: CLIENT,
    };
    try {
      last = await api<SessionDto>('/session', { method: 'PUT', body });
    } catch (e) {
      console.warn('session sync failed', e);
    }
  }, 80);
}

export async function startSync(): Promise<() => void> {
  apply(await api<SessionDto>('/session'));
  const unsubStore = useDraft.subscribe((s, prev) => {
    if (applying) return;
    const shared = ['allies', 'enemies', 'bans', 'side', 'pos', 'comfort'] as const;
    if (shared.some((k) => s[k] !== prev[k])) push();
  });
  const unsubWs = subscribe((e) => {
    if (e.type !== 'session') return;
    const s = e.state as SessionDto;
    if (s.source !== CLIENT && (!last || s.rev >= last.rev)) apply(s);
    else last = s;
  });
  return () => {
    unsubStore();
    unsubWs();
  };
}
