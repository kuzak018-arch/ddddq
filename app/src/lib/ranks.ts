const RANKS = ['', 'Herald', 'Guardian', 'Crusader', 'Archon', 'Legend', 'Ancient', 'Divine', 'Immortal'];

/** «Legend 4» from a rank tier (54), «нет ранга» without one. */
export const rankName = (t: number | null | undefined) => (t ? `${RANKS[Math.floor(t / 10)] ?? '?'}${t % 10 ? ` ${t % 10}` : ''}` : 'нет ранга');

/** Which medal and stars (public/dota-icons/ranks) a rank tier (54 = Legend 4) shows; Immortals in
 * the leaderboard's top 100 and top 10 have their own medals. */
export function medalFor(tier: number | null | undefined, leaderboard?: number | null): { medal: string; stars: number } {
  const major = tier ? Math.min(8, Math.floor(tier / 10)) : 0;
  if (major === 8) return { medal: leaderboard && leaderboard <= 10 ? '8c' : leaderboard && leaderboard <= 100 ? '8b' : '8', stars: 0 };
  return { medal: String(major), stars: major ? Math.min(7, tier! % 10) : 0 };
}
