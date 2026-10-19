const RANKS = ['', 'Herald', 'Guardian', 'Crusader', 'Archon', 'Legend', 'Ancient', 'Divine', 'Immortal'];

/** «Legend 4» from a rank tier (54), «нет ранга» without one. */
export const rankName = (t: number | null | undefined) => (t ? `${RANKS[Math.floor(t / 10)] ?? '?'}${t % 10 ? ` ${t % 10}` : ''}` : 'нет ранга');
