"""How many rating points (ПТС, MMR) are left to the next star and the next medal.

Valve hides the exact rating, the profile only shows the rank tier (54 = Legend 4: medal 5, star 4).
What is known about the scale (community tables, stable for years): medals start at 0, 770, 1540,
2310, 3080, 3850, 4620 (Herald … Divine) and Immortal at 5420; a star is a fifth of a medal
(154 points; Divine's are 160). So a tier tells the window the rating is in; inside it the rating is
either OpenDota's estimate (when that falls into the window, otherwise it is unrelated to the current
rank) or the middle of the window. A ranked win or loss is worth about 25 points.
"""

from __future__ import annotations

import math

MEDALS = ["", "Herald", "Guardian", "Crusader", "Archon", "Legend", "Ancient", "Divine", "Immortal"]
BASE = [0, 0, 770, 1540, 2310, 3080, 3850, 4620, 5420]   # index = medal 1..8
POINTS_PER_GAME = 25


def _star_width(medal: int) -> float:
    return (BASE[medal + 1] - BASE[medal]) / 5


def _name(medal: int, star: int) -> str:
    return MEDALS[medal] if medal >= 8 else f"{MEDALS[medal]} {star}"


def progress(rank_tier: int | None, estimate: float | None = None) -> dict | None:
    """The window of the rating, the best guess inside it and what is left to the next star / medal;
    None without a rank, for Immortals (their rank is a leaderboard place) and for tiers we don't know."""
    if not rank_tier:
        return None
    medal, star = divmod(int(rank_tier), 10)
    if not 1 <= medal <= 7 or not 1 <= star <= 5:
        return None
    width = _star_width(medal)
    low = BASE[medal] + (star - 1) * width
    high = low + width
    use_estimate = estimate is not None and low <= estimate < high
    mmr = float(estimate) if use_estimate else (low + high) / 2

    def step(name: str, at: float) -> dict:
        points = max(1, round(at - mmr))
        return {"name": name, "points": points, "games": math.ceil(points / POINTS_PER_GAME)}

    next_medal = _name(medal + 1, 1)
    return {
        "tier": int(rank_tier), "name": _name(medal, star), "mmr": round(mmr), "from_estimate": bool(use_estimate),
        "low": round(low), "high": round(high) - 1,
        "next_star": step(_name(medal, star + 1), high) if star < 5 else None,
        "next_rank": step(next_medal, BASE[medal + 1]),
        "per_game": POINTS_PER_GAME,
    }
