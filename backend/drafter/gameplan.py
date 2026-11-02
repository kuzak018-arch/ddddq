"""The overlay's game plan: when each team is strongest, how to play this draft, how to finish the
game, and which enemy heroes my hero can kill.

Timing: every hero's win rate by game length (model/timing.py) against the average of that length;
a team's curve is the sum over its heroes, ours minus theirs gives the window (where we are
stronger) and the moment it turns. Style: the heroes' roles (OpenDota: Initiator, Disabler,
Pusher, Escape, Durable, Carry...). Without the match base there is no timing, the rest still works.

Who to kill: for my hero against each enemy, the pair's counter term of the draft model (how much
my hero wins against that one, log-odds), how fragile the enemy is (health and armor at the level
of this minute against the median hero), whether it escapes or is tanky, and whether this part of
the game is the enemy's strong one. It says whom to look for and whom to leave alone; it knows
nothing about items and levels in the actual game.
"""

from __future__ import annotations

import statistics

from .data import constants
from .model import timing

WINDOW = 0.015          # a team curve difference above this is a window
KILL, AVOID = 0.12, -0.12


def _name(h: int) -> str:
    return (constants.hero_by_id().get(h) or {}).get("name") or str(h)


def _names(hs: list[int], n: int = 3) -> str:
    return ", ".join(_name(h) for h in hs[:n])


def _roles(h: int) -> set[str]:
    return set((constants.hero_by_id().get(h) or {}).get("roles") or [])


def curve(team: list[int], t: dict) -> list[float]:
    base = t["base"]
    out = [0.0] * len(base)
    for h in team:
        wr = (t["heroes"].get(str(h)) or {}).get("wr")
        if wr:
            for b, (w, avg) in enumerate(zip(wr, base)):
                out[b] += w - avg
    return out


def _late_heroes(team: list[int], t: dict) -> list[int]:
    """Heroes of the team that gain the most from a long game."""
    def gain(h):
        wr = (t["heroes"].get(str(h)) or {}).get("wr")
        return (wr[-1] - t["base"][-1]) - (wr[0] - t["base"][0]) if wr else 0
    return [h for h in sorted(team, key=gain, reverse=True) if gain(h) > 0.02]


def _early_heroes(team: list[int], t: dict) -> list[int]:
    def gain(h):
        wr = (t["heroes"].get(str(h)) or {}).get("wr")
        return (wr[0] - t["base"][0]) - (wr[-1] - t["base"][-1]) if wr else 0
    return [h for h in sorted(team, key=gain, reverse=True) if gain(h) > 0.02]


def plan(allies: list[int], enemies: list[int], minute: float | None = None, t: dict | None = None) -> dict:
    t = t if t is not None else timing.load()
    tips: list[dict] = []
    out: dict = {"timing": None, "tips": tips}
    shape = "even"
    if t and t.get("heroes") and allies and enemies:
        ours, theirs = curve(allies, t), curve(enemies, t)
        diff = [round(a - b, 4) for a, b in zip(ours, theirs)]
        out["timing"] = {"buckets": t["buckets"], "diff": diff,
                         "now": timing.bucket_of(minute) if minute is not None else None}
        signs = [1 if d > WINDOW else -1 if d < -WINDOW else 0 for d in diff]
        cross = next((timing.EDGES[i] for i in range(len(diff) - 1) if (diff[i] > 0) != (diff[i + 1] > 0)), None)
        if diff[0] > 0 and diff[-1] < 0:
            shape = "early"
            late = _late_heroes(enemies, t)
            tips.append({"kind": "timing", "text": f"Ваше окно — до ~{cross or 35} мин: давите сейчас, затягивать нельзя"
                         + (f" — дальше сильнее враги ({_names(late)})." if late else ".")})
        elif diff[0] < 0 and diff[-1] > 0:
            shape = "late"
            late = _late_heroes(allies, t)
            tips.append({"kind": "timing", "text": f"До ~{cross or 35} мин сильнее враги: играйте от защиты и фарма, не отдавайте смерти."
                         + (f" Потом сильнее вы ({_names(late)})." if late else " Потом сильнее вы.")})
        elif all(s >= 0 for s in signs) and any(s > 0 for s in signs):
            shape = "ahead"
            tips.append({"kind": "timing", "text": "Состав сильнее во всех фазах игры: играйте уверенно и не дарите смерти — время на вашей стороне."})
        elif all(s <= 0 for s in signs) and any(s < 0 for s in signs):
            shape = "behind"
            tips.append({"kind": "timing", "text": "По составу враги сильнее: ищите их ошибки, ловите из тумана, не идите в равные драки 5 на 5."})
        else:
            tips.append({"kind": "timing", "text": "Составы ровные по времени: игру решат линии и первый Рошан."})
        if minute is not None:
            d = diff[timing.bucket_of(minute)]
            if d > WINDOW:
                tips.append({"kind": "now", "text": f"Сейчас ({int(minute)} мин) ваше время: собирайтесь и навязывайте драки."})
            elif d < -WINDOW:
                tips.append({"kind": "now", "text": f"Сейчас ({int(minute)} мин) время врагов: не драться без преимущества, фармить безопасно."})
    out["shape"] = shape

    def has(team, role):
        return [h for h in team if role in _roles(h)]
    control = has(allies, "Initiator") + [h for h in has(allies, "Disabler") if h not in has(allies, "Initiator")]
    if len(set(control)) >= 4:
        tips.append({"kind": "style", "text": f"Много контроля и инициации ({_names(sorted(set(control)), 4)}): сила в драках 5 на 5 — ищите их у Рошана и вышек."})
    if len(pushers := has(allies, "Pusher")) >= 2:
        tips.append({"kind": "style", "text": f"У вас пушеры ({_names(pushers)}): после каждой выигранной драки — сразу на строения."})
    if len(esc := has(enemies, "Escape")) >= 2:
        tips.append({"kind": "style", "text": f"У врагов побег ({_names(esc)}): ловите только с контролем из тумана, далеко не гонитесь."})
    if len(tanks := has(enemies, "Durable")) >= 2:
        tips.append({"kind": "style", "text": f"У врагов толстые герои ({_names(tanks)}): долгие драки им выгодны — бейте быстро и по самым хрупким."})
    if len(their_push := has(enemies, "Pusher")) >= 2:
        tips.append({"kind": "style", "text": f"Враги быстро ломают вышки ({_names(their_push)}): защищайте линии вовремя, не уходите всей командой в лес."})
    if len(carries := has(allies, "Carry")) >= 3:
        tips.append({"kind": "style", "text": f"Много героев на фарм ({_names(carries)}): делите карту, кто-то должен отдать фарм."})

    finish = {
        "early": "Как закончить: к ~20–25 мин собирайтесь впятером, ломайте вышки одной линии за раз, после Рошана — сразу высокие вышки. Не уходите фармить лес, пока есть перевес.",
        "late": "Как закончить: без Аегиса и выкупов врагов на высокие вышки не лезьте. Дождитесь слотов, выиграйте драку у Рошана и только тогда идите на базу.",
        "ahead": "Как закончить: держите темп — Рошан, затем строения. Каждый раз, когда враги без выкупа, идите на базу.",
        "behind": "Как закончить: держите базу, ловите одиночек и забирайте Рошана из тумана; одна выигранная драка у высоких вышек разворачивает игру.",
        "even": "Как закончить: решает первый Рошан — к 18–20 мин поставьте вижн у логова и деритесь там, после Аегиса давите строения.",
    }[shape]
    tips.append({"kind": "finish", "text": finish})
    return out


# ---------- who to kill ---------------------------------------------------------------------------

def _level(minute: float) -> float:
    """A typical hero's level at this minute (about 10 at 10 minutes, 18 at 25, 25 at 40)."""
    return max(1.0, min(30.0, 1 + minute * 0.95 if minute < 10 else 10 + (minute - 10) * 0.55))


def _ehp(h: dict, level: float) -> float:
    strength = (h.get("base_str") or 0) + (h.get("str_gain") or 0) * (level - 1)
    agility = (h.get("base_agi") or 0) + (h.get("agi_gain") or 0) * (level - 1)
    hp = (h.get("base_health") or 120) + 22 * strength
    armor = (h.get("base_armor") or 0) + agility / 6
    return hp * (1 + 0.06 * armor) if armor >= 0 else hp / (1 + 0.06 * -armor)


def killable(me: int, enemies: list[int], counter, minute: float = 10.0, t: dict | None = None) -> list[dict]:
    """Each enemy: `kill` (go for it), `team` (only with the team) or `avoid` (not alone), with reasons.
    `counter(a, b)`: the draft model's log-odds advantage of hero a against hero b."""
    heroes = constants.hero_by_id()
    stats = {int(k): v for k, v in constants._load("heroes").items() if str(k).isdigit()}   # base health, armor, gains
    t = t if t is not None else timing.load(start=False)
    level = _level(minute)
    median = statistics.median(_ehp(h, level) for h in stats.values()) or 1
    b = timing.bucket_of(minute)
    out = []
    for e in enemies:
        h = heroes.get(e)
        if not h:
            continue
        reasons = []
        c = float(counter(me, e))
        frail = median / max(_ehp(stats.get(e) or {}, level), 1) - 1     # > 0: less health and armor than the median hero
        roles = set(h.get("roles") or [])
        score = 2.0 * c + 0.6 * frail
        if c > 0.04:
            reasons.append(f"ты его контришь (+{c / 4 * 100:.1f}% к победе)")
        elif c < -0.04:
            reasons.append(f"он контрит тебя ({c / 4 * 100:.1f}%)")
        if frail > 0.12:
            reasons.append("хрупкий")
        elif frail < -0.15:
            reasons.append("толстый")
        if "Escape" in roles:
            score -= 0.12
            reasons.append("есть побег")
        if "Durable" in roles and frail >= -0.15:
            score -= 0.08
            reasons.append("живучий")
        if t and t.get("heroes") and (wr := (t["heroes"].get(str(e)) or {}).get("wr")):
            strong = wr[b] - t["base"][b]
            score -= 3 * strong
            if strong > 0.025:
                reasons.append("сейчас его время")
            elif strong < -0.025:
                reasons.append("сейчас слабеет")
        verdict = "kill" if score >= KILL else "avoid" if score <= AVOID else "team"
        out.append({"hero": e, "verdict": verdict, "score": round(score, 3), "reasons": reasons[:3]})
    out.sort(key=lambda x: -x["score"])
    return out
