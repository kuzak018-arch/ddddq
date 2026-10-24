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
// a local edit waiting to be sent or on its way: changes from elsewhere wait until the backend has
// merged it (it sends the rev it was based on, so the backend keeps both sides' changes)
let timer: ReturnType<typeof setTimeout> | null = null;
let inFlight = false;
let deferred: SessionDto | null = null;

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

/** A state from the backend: applied unless older than what this window shows. */
function offer(s: SessionDto) {
  if (timer || inFlight) {
    if (!deferred || s.rev > deferred.rev) deferred = s;
    return;
  }
  if (!last || s.rev > last.rev) apply(s);
}

function push() {
  if (timer) clearTimeout(timer);
  timer = setTimeout(send, 80);
}

async function send() {
  timer = null;
  inFlight = true;
  const d = useDraft.getState();
  const body = {
    allies: d.allies,
    enemies: d.enemies,
    bans: d.bans,
    side: d.side,
    pos: d.pos,
    comfort: d.comfort,
    base_rev: last?.rev ?? null,
    source: CLIENT,
  };
  try {
    const merged = await api<SessionDto>('/session', { method: 'PUT', body });
    if (!deferred || merged.rev >= deferred.rev) deferred = merged;
  } catch (e) {
    console.warn('session sync failed', e);
  } finally {
    inFlight = false;
  }
  if (timer) return; // edited again meanwhile: that send brings the newest state back
  const next = deferred;
  deferred = null;
  if (next && (!last || next.rev > last.rev)) apply(next);
}

async function refetch() {
  try {
    offer(await api<SessionDto>('/session'));
  } catch {
    /* the next event brings it */
  }
}

export async function startSync(): Promise<() => void> {
  apply(await api<SessionDto>('/session'));
  const unsubStore = useDraft.subscribe((s, prev) => {
    if (applying) return;
    const shared = ['allies', 'enemies', 'bans', 'side', 'pos', 'comfort'] as const;
    if (shared.some((k) => s[k] !== prev[k])) push();
  });
  const unsubWs = subscribe((e) => {
    // (re)connected: anything changed while the socket was down or not yet open
    if (e.type === 'hello') return void refetch();
    if (e.type !== 'session') return;
    const s = e.state as SessionDto;
    if (s.source !== CLIENT) offer(s);   // our own echo: the PUT's answer brings that state
  });
  return () => {
    unsubStore();
    unsubWs();
  };
}
