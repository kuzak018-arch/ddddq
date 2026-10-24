"""Three-way merge of the shared draft: a window sends its whole board, edited from the state it
last saw (`base`); meanwhile GSI or screen reading may have changed the board (`theirs`). Every
slot / field the window changed takes the window's value, every other one keeps the newer state's,
so neither side's change is lost. A hero that ends up twice stays where the window put it."""

from __future__ import annotations


def _field(base, mine, theirs):
    return theirs if mine == base else mine


def merge(base: dict, mine: dict, theirs: dict) -> dict:
    out = dict(theirs)
    mine_slots: set[tuple[str, int]] = set()
    for team in ("allies", "enemies"):
        slots = []
        for i, (b, m, t) in enumerate(zip(base[team], mine[team], theirs[team])):
            if m != b:
                mine_slots.add((team, i))
            slots.append(_field(b, m, t))
        out[team] = slots
    added = [h for h in mine["bans"] if h not in base["bans"]]
    removed = {h for h in base["bans"] if h not in mine["bans"]}
    bans = [h for h in theirs["bans"] if h not in removed]
    out["bans"] = bans + [h for h in added if h not in bans]
    for k in ("side", "pos", "comfort"):
        out[k] = _field(base.get(k), mine.get(k), theirs.get(k))
    # one hero, one place: the window's own placement wins over the other side's
    mine_heroes = {mine[t][i] for t, i in mine_slots if mine[t][i]} | set(added)
    for team in ("allies", "enemies"):
        out[team] = [None if h in mine_heroes and (team, i) not in mine_slots else h for i, h in enumerate(out[team])]
    out["bans"] = [h for h in out["bans"] if h not in mine_heroes or h in added]
    seen: set[int] = set()
    for team in ("allies", "enemies"):
        for i, h in enumerate(out[team]):
            if h is not None and h in seen:
                out[team][i] = None
            elif h is not None:
                seen.add(h)
    out["bans"] = [h for h in dict.fromkeys(out["bans"]) if h not in seen]
    return out
