"""How a lane of hero A against hero B goes, minute by minute, from real matches of that pair.

- Curves: A minus B in networth and in experience at each minute 0..MINUTES (median and the
  middle half of matches), and how often A is ahead.
- Pressure windows: stretches where the gap keeps growing towards one hero (networth and
  experience separately). For every 2-minute step, the change of the gap in each match; a step
  counts if the mean is at least PRESS_MIN a minute and stands out of the noise (PRESS_Z standard
  errors). Fixed minutes, not purchase moments: items are bought right after fast farming, so
  measuring around purchases would be biased.
- Spikes: when each hero reaches levels 2, 3 and 6 and buys its usual lane items (median times).
  A spike is called an overspike only when a pressure window of that hero starts right at it.
- Phases: stretches of minutes where one hero is clearly ahead, for the plain-text summary.
"""

from __future__ import annotations

import statistics

from ..builds import sequences
from . import pairs

MINUTES = 15
LEVELS = (2, 3, 6)
ITEM_WINDOW_S = MINUTES * 60
ITEM_MIN_SHARE = 0.35
PRESS_MIN = 30           # gold (or experience) per minute
PRESS_Z = 1.5
PRESS_SURE_Z = 2.5       # above this the window is "sure", below it "noticeable"
SPIKE_BEFORE = 1.0       # an overspike: the window starts at most this many minutes before it ...
SPIKE_AFTER = 1.5        # ... or this many after it
CHEAP = 1000             # items below this cost explain a window only if nothing else does
LEAD_BASE = 150          # a lead counts from this much networth ...
LEAD_SHARE = 0.05        # ... plus this share of the heroes' average networth at that minute
MIN_GAMES = 20
RELIABLE_GAMES = 80


def _q(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    i = (len(xs) - 1) * q
    lo = int(i)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def _moments(p: dict) -> dict[str, int]:
    """Second of each lane-phase moment of one player in one match: levels and first purchases
    of finished items (no consumables or components, see sequences.parse)."""
    out = {f"level{lv}": p["lvl"][lv - 1] for lv in LEVELS if len(p["lvl"]) >= lv}
    g = sequences.parse({"items": p["items"], "w": p["w"]})
    if g:
        seen: dict[str, int] = dict(g.early)
        for x in (g.boots, g.upgrade, *g.core):
            if x:
                seen.setdefault(x[0], x[1])
        out.update({k: t for k, t in seen.items() if t <= ITEM_WINDOW_S})
    return out


def _slope(gaps: list[list[int]], t0: int, t1: int) -> tuple[float, float, int] | None:
    """Mean per-minute change of the gap from minute t0 to t1 over the matches, its z score, n."""
    xs = [(g[t1] - g[t0]) / (t1 - t0) for g in gaps if len(g) > t1]
    if len(xs) < MIN_GAMES:
        return None
    mean = statistics.fmean(xs)
    se = statistics.stdev(xs) / len(xs) ** 0.5
    return mean, (mean / se if se else (float("inf") if mean else 0.0)), len(xs)


def _windows(gaps: list[list[int]], metric: str, horizon: int) -> list[dict]:
    flags = []
    for t in range(horizon - 1):
        r = _slope(gaps, t, t + 2)
        f = 0
        if r and abs(r[0]) >= PRESS_MIN and abs(r[1]) >= PRESS_Z:
            f = 1 if r[0] > 0 else -1
        flags.append(f)
    # runs of steps in the same direction; runs that touch (a step's end is the next one's start) merge
    spans: list[list[int]] = []
    for t, f in enumerate(flags):
        if not f:
            continue
        if spans and spans[-1][2] == f and t <= spans[-1][1]:
            spans[-1][1] = t + 2
        else:
            spans.append([t, t + 2, f])
    out = []
    for frm, to, f in spans:
        mean, z, n = _slope(gaps, frm, to)
        out.append({"metric": metric, "from": frm, "to": to, "leader": "hero" if f > 0 else "enemy",
                    "per_min": round(abs(mean)), "z": round(abs(z), 1), "sure": abs(z) >= PRESS_SURE_Z, "n": n})
    return out


def analyze(recs: list[dict], a: int, pa: int, b: int, pb: int) -> dict:
    games = [r for r in recs if pairs.usable(r, a, pa, b, pb)]
    A = [r["p"][str(a)] for r in games]
    B = [r["p"][str(b)] for r in games]
    n = len(games)
    out: dict = {"games": n, "reliable": n >= RELIABLE_GAMES, "min_games": MIN_GAMES,
                 "wins": sum(x["w"] for x in A)}
    if n < MIN_GAMES:
        return out

    curves = []
    for t in range(MINUTES + 1):
        both = [(x, y) for x, y in zip(A, B) if len(x["nw"]) > t and len(y["nw"]) > t
                and len(x["xp"]) > t and len(y["xp"]) > t]
        if len(both) < max(MIN_GAMES, n / 2):
            break
        nw = [x["nw"][t] - y["nw"][t] for x, y in both]
        xp = [x["xp"][t] - y["xp"][t] for x, y in both]
        avg = statistics.fmean((x["nw"][t] + y["nw"][t]) / 2 for x, y in both)
        curves.append({"minute": t, "n": len(both),
                       "nw": round(statistics.median(nw)), "nw_lo": round(_q(nw, 0.25)), "nw_hi": round(_q(nw, 0.75)),
                       "xp": round(statistics.median(xp)), "xp_lo": round(_q(xp, 0.25)), "xp_hi": round(_q(xp, 0.75)),
                       "ahead": round(sum(d > 0 for d in nw) / len(nw), 3), "avg_nw": round(avg)})
    out["curves"] = curves

    horizon = curves[-1]["minute"] if curves else 0
    windows = []
    for metric in ("nw", "xp"):
        gaps = [[u - v for u, v in zip(x[metric], y[metric])][:horizon + 1] for x, y in zip(A, B)]
        windows += _windows(gaps, metric, horizon)
    out["windows"] = sorted(windows, key=lambda w: (w["from"], w["metric"]))

    # spikes of both heroes: their usual levels and items; an overspike starts a pressure window
    events = []
    for side, hero, players in (("hero", a, A), ("enemy", b, B)):
        moments = [_moments(p) for p in players]
        for key in {k for m in moments for k in m}:
            times = [m[key] for m in moments if key in m]
            if len(times) / n < (0.5 if key.startswith("level") else ITEM_MIN_SHARE):
                continue
            e = {"side": side, "hero": hero, "key": key,
                 "minute": round(statistics.median(times) / 60, 1), "share": round(len(times) / n, 3)}
            if key.startswith("level"):
                e.update(kind="level", name=f"{key[5:]} уровень")
            else:
                e.update(kind="item", name=sequences._name(key), cost=sequences._cost(key))
            e["spike"], e["window"] = False, None
            events.append(e)
    # each window is put down to at most one spike: the owner's moment nearest to its start, levels and
    # real items first (a Magic Wand bought at the start of a window is a coincidence, not its cause)
    for w in windows:
        near = [e for e in events if e["side"] == w["leader"]
                and e["minute"] - SPIKE_BEFORE <= w["from"] <= e["minute"] + SPIKE_AFTER]
        if near:
            e = min(near, key=lambda e: (e.get("cost", CHEAP) < CHEAP, abs(e["minute"] - w["from"])))
            w["spike"] = e["name"]
            if not e["spike"]:
                e["spike"], e["window"] = True, {k: v for k, v in w.items() if k != "spike"}
    out["events"] = sorted(events, key=lambda e: e["minute"])

    # phases: who is clearly ahead, minute by minute, merged into stretches
    phases: list[dict] = []
    for c in curves:
        lead = LEAD_BASE + LEAD_SHARE * c["avg_nw"]
        who = "hero" if c["nw"] >= lead else "enemy" if c["nw"] <= -lead else None
        if phases and phases[-1]["leader"] == who:
            ph = phases[-1]
            ph["to"] = c["minute"]
            if abs(c["nw"]) > abs(ph["peak"]):
                ph["peak"] = c["nw"]
        else:
            phases.append({"from": c["minute"], "to": c["minute"], "leader": who, "peak": c["nw"]})
    out["phases"] = phases

    at = next((c for c in curves if c["minute"] == 10), curves[-1] if curves else None)
    out["at"] = at and {"minute": at["minute"], "nw": at["nw"], "xp": at["xp"], "ahead": at["ahead"]}
    return out
