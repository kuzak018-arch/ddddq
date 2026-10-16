"""Russian explanations for evaluation/suggestion terms."""

from __future__ import annotations

from scipy.special import expit

from ..data import constants


def name(h: int) -> str:
    return constants.hero_by_id()[h]["name"]


def pct(v: float) -> str:
    """Log-odds contribution near 50% -> percentage points (d p / d z = 0.25 at p = 0.5)."""
    return f"{(expit(v) - 0.5) * 100:+.1f}%"


def term_text(t, me: int | None = None) -> str:
    if t.kind == "hero":
        return f"сила {name(t.heroes[0])} в мете {pct(t.value)}"
    if t.kind == "synergy":
        a, b = t.heroes
        if t.value >= 0:
            return f"синергия {name(a)} + {name(b)} {pct(t.value)}"
        return f"{name(a)} плохо сочетается с {name(b)} {pct(t.value)}"
    if t.kind == "counter":
        a, b = t.heroes
        if t.value >= 0:
            return f"{name(a)} хорош против {name(b)} {pct(t.value)}"
        return f"{name(b)} контрит {name(a)} {pct(t.value)}"
    if t.kind == "comfort":
        return f"твой опыт на герое ({t.note}) {pct(t.value)}"
    if t.kind == "risk":
        who = ", ".join(name(h) for h in t.heroes)
        return f"риск контрпика{' (' + who + ')' if who else ''} {pct(t.value)}"
    return f"{t.kind} {pct(t.value)}"
