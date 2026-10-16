"""Hero lookup by English/Russian names and slang, with keyboard-layout auto-fix
(`згвпу` -> pudge). Port of the dota2-tierlist search, plus ranking: exact > prefix > substring."""

from __future__ import annotations

import re
from functools import cache

from .data import constants

_EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
_RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
_SWAP = {**dict(zip(_EN, _RU)), **dict(zip(_RU, _EN))}


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9а-я]+", "", s.lower().replace("ё", "е"))


def _switch_layout(s: str) -> str:
    return "".join(_SWAP.get(c, c) for c in s.lower())


@cache
def _haystacks() -> list[tuple[int, list[str]]]:
    out = []
    for h in constants.hero_index():
        parts = [h["name"], h["key"].replace("_", " "), *h["ru"], *h["alias"]]
        out.append((h["id"], sorted({normalize(p) for p in parts if normalize(p)})))
    return out


def _rank(term: str) -> list[tuple[int, int]]:
    scored = []
    for hid, hay in _haystacks():
        best = min((0 if x == term else 1 if x.startswith(term) else 2 if term in x else 9) for x in hay)
        if best < 9:
            scored.append((best, hid))
    return sorted(scored)


def find(query: str, limit: int = 8) -> list[int]:
    typed, switched = normalize(query), normalize(_switch_layout(query))
    if not typed and not switched:
        return []
    # `,r,` loses its commas when normalized: the other layout is what was meant
    terms = [switched] if len(switched) > len(typed) else [typed, switched]
    for term in terms:
        if term and (res := _rank(term)):
            return [hid for _, hid in res[:limit]]
    return []


def resolve(query: str) -> int:
    """Single hero for a query, or ValueError with the candidates."""
    res = find(query)
    if not res:
        raise ValueError(f"не нашёл героя «{query}»")
    return res[0]
