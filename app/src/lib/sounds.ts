/**
 * Interface sounds, synthesised with Web Audio (no sound files): a hero placed, a ban, a hero
 * removed, hero selection starting, and (if wanted) a soft tick when the tab changes. Played by the
 * main window only (the overlay would double them). Настройки → Оформление → «Звуки».
 */

export type SoundName = 'pick' | 'ban' | 'remove' | 'start' | 'tab' | 'done';

interface Note {
  /** start, s */
  at: number;
  freq: number;
  dur: number;
  type?: OscillatorType;
  gain?: number;
  /** pitch glides to this by the end */
  to?: number;
}

/** What each sound is made of (exported for the tests: every sound is short and not too loud). */
export const SOUNDS: Record<SoundName, Note[]> = {
  pick: [
    { at: 0, freq: 660, dur: 0.12, gain: 0.5 },
    { at: 0.06, freq: 990, dur: 0.18, gain: 0.45 },
  ],
  ban: [
    { at: 0, freq: 220, to: 150, dur: 0.22, type: 'triangle', gain: 0.6 },
    { at: 0, freq: 440, to: 300, dur: 0.12, gain: 0.2 },
  ],
  remove: [{ at: 0, freq: 520, to: 360, dur: 0.14, type: 'triangle', gain: 0.35 }],
  start: [
    { at: 0, freq: 523.25, dur: 0.22, gain: 0.4 },
    { at: 0.11, freq: 659.25, dur: 0.22, gain: 0.4 },
    { at: 0.22, freq: 783.99, dur: 0.26, gain: 0.4 },
    { at: 0.34, freq: 1046.5, dur: 0.42, gain: 0.35 },
  ],
  tab: [{ at: 0, freq: 1800, dur: 0.035, type: 'triangle', gain: 0.12 }],
  done: [
    { at: 0, freq: 784, dur: 0.16, gain: 0.4 },
    { at: 0.09, freq: 1175, dur: 0.3, gain: 0.35 },
  ],
};

export const soundLength = (name: SoundName) => Math.max(...SOUNDS[name].map((n) => n.at + n.dur));

let ctx: AudioContext | null = null;

/** Plays a sound at volume 0..1. Silent when the browser has no audio or refuses to start it. */
export function play(name: SoundName, volume: number): void {
  if (volume <= 0 || typeof AudioContext === 'undefined') return;
  try {
    ctx ??= new AudioContext();
    if (ctx.state === 'suspended') void ctx.resume();
    const t0 = ctx.currentTime + 0.01;
    const master = ctx.createGain();
    master.gain.value = Math.min(1, volume) * 0.35;
    master.connect(ctx.destination);
    for (const n of SOUNDS[name]) {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = n.type ?? 'sine';
      osc.frequency.setValueAtTime(n.freq, t0 + n.at);
      if (n.to) osc.frequency.exponentialRampToValueAtTime(n.to, t0 + n.at + n.dur);
      // a soft attack and an exponential fade: no clicks
      g.gain.setValueAtTime(0.0001, t0 + n.at);
      g.gain.exponentialRampToValueAtTime(n.gain ?? 0.3, t0 + n.at + 0.008);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + n.at + n.dur);
      osc.connect(g).connect(master);
      osc.start(t0 + n.at);
      osc.stop(t0 + n.at + n.dur + 0.02);
    }
    setTimeout(() => master.disconnect(), (soundLength(name) + 0.2) * 1000);
  } catch {
    // no audio device or the context was refused: the app just stays quiet
  }
}

type Board = { allies: (number | null)[]; enemies: (number | null)[]; bans: number[] };

/** Which sound a change of the draft board deserves: a ban first, then a pick, then a removal. */
export function boardSound(prev: Board, next: Board): SoundName | null {
  const count = (b: Board) => ({
    picks: b.allies.filter(Boolean).length + b.enemies.filter(Boolean).length,
    bans: b.bans.length,
  });
  const a = count(prev);
  const b = count(next);
  if (b.bans > a.bans) return 'ban';
  if (b.picks > a.picks) return 'pick';
  if (b.picks < a.picks || b.bans < a.bans) {
    // a new match clears the board at once: that is not «a hero removed»
    return b.picks === 0 && b.bans === 0 && a.picks + a.bans > 1 ? null : 'remove';
  }
  return null;
}
