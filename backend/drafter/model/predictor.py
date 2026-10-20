"""Win probability, hero suggestions and ban suggestions with explanations.

Served model: the additive logistic regression (best on the time-split test, see
reports/model.md). It is linear in log-odds, so each prediction splits exactly into
hero strength, synergy pairs and counter pairs; Platt calibration (p = sigmoid(a*z + b))
maps log-odds to probability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

import joblib
import numpy as np
from scipy.special import expit

from ..data import constants, me
from . import draft, train

MAIN_POS_SHARE = 0.40  # main list: heroes played on this position in >= 40% of their games
MIN_POS_SHARE = 0.10   # 'off-role' block: 10-40%; below 10% a hero is not suggested at all
# The personal experience curve (me.fit_experience) is fitted on the user's games, but part of it
# is selection (new heroes get tried in odd drafts), so only this share goes into the score.
COMFORT_WEIGHT = 0.5
COMFORT_MIN_GAMES = 3  # below this a hero counts as unfamiliar for the specialist rule and ban pool
# Rarely picked heroes with high winrate are mostly played by specialists (Meepo, ...).
SPECIALIST_PICK_RATE = 0.03


@dataclass
class Term:
    kind: str           # hero | synergy | counter | comfort | risk
    heroes: list[int]
    value: float        # log-odds contribution (already scaled by calibration slope)
    note: str = ""


@dataclass
class Evaluation:
    p_win: float
    terms: list[Term] = field(default_factory=list)


class Predictor:
    def __init__(self, path=train.ART / "models.joblib"):
        a = joblib.load(path)
        self.n_ids: int = a["n_ids"]
        add = a["additive"]
        w = add.weights
        self.S, self.C = add.S * w["syn"], add.C * w["cnt"]       # already in log-odds
        self.pair_games = add.pairs.games()                       # (synergy, counter) games per pair
        self.hero_w, self.hero_group_w = w["hero"], w["hero_group"]
        self.intercept = w["intercept"]                            # Radiant advantage
        cal = a["cal"]["lr"].lr
        self.cal_a, self.cal_b = float(cal.coef_[0][0]), float(cal.intercept_[0])
        self.pick_rate = a["pick_rate"]
        self.lw = a["lw"]
        self.pos_mat = a["pos_mat"].copy()        # EM estimate from team compositions
        self.positions_source = "EM по составам команд"
        from ..data import stratz
        bracket = stratz.bracket_for(me.rank_tier())
        sp = stratz.positions(bracket)
        if sp:                                     # Stratz knows real positions: prefer it
            for h, v in sp.items():
                if h < len(self.pos_mat):
                    self.pos_mat[h] = v
            self.positions_source = f"Stratz, {bracket}"
        self.heroes = constants.hero_by_id()
        self._grow_to(max(self.heroes, default=0) + 1)

    def _grow_to(self, n: int) -> None:
        """A patch brings a hero the model was trained without (constants are refreshed at once, the
        model only after enough games): every per-hero array grows with zeros, so the new hero is
        «no data» (neutral) instead of an IndexError in the hero list and the draft."""
        old = self.n_ids
        if n <= old:
            return

        def grow(a: np.ndarray) -> np.ndarray:
            pad = [(0, n - old) if dim == old else (0, 0) for dim in a.shape]
            return np.pad(a, pad) if any(p[1] for p in pad) else a

        self.S, self.C = grow(self.S), grow(self.C)
        self.pair_games = tuple(grow(g) for g in self.pair_games)
        self.hero_w, self.hero_group_w = grow(self.hero_w), grow(self.hero_group_w)
        self.pick_rate, self.lw, self.pos_mat = grow(self.pick_rate), grow(self.lw), grow(self.pos_mat)
        self.n_ids = n

    # ---- basics -------------------------------------------------------------------------

    def strength(self, h: int, group: int) -> float:
        return float(self.hero_w[h] + self.hero_group_w[group, h])

    def side_term(self, side: str | None) -> float:
        """Calibrated log-odds of playing Radiant (+) or Dire (-); unknown side -> neutral.
        Radiant: sigmoid(a*(z + c) + b); Dire, seen from our side: sigmoid(a*z - a*c - b)."""
        s = self.cal_a * self.intercept + self.cal_b
        return {"radiant": s, "dire": -s}.get(side, 0.0)

    def evaluate(self, allies: list[int], enemies: list[int], group: int, side: str | None = None) -> Evaluation:
        terms: list[Term] = []
        for h in allies:
            terms.append(Term("hero", [h], self.cal_a * self.strength(h, group)))
        for h in enemies:
            terms.append(Term("hero", [h], -self.cal_a * self.strength(h, group)))
        for i, a in enumerate(allies):
            for b in allies[i + 1:]:
                terms.append(Term("synergy", [a, b], self.cal_a * self.S[a, b]))
        for i, a in enumerate(enemies):
            for b in enemies[i + 1:]:
                terms.append(Term("synergy", [a, b], -self.cal_a * self.S[a, b]))
        for a in allies:
            for b in enemies:
                terms.append(Term("counter", [a, b], self.cal_a * self.C[a, b]))
        z = sum(t.value for t in terms) + self.side_term(side)
        return Evaluation(float(expit(z)), sorted(terms, key=lambda t: -abs(t.value)))

    # ---- positions -------------------------------------------------------------------------

    def playable(self, pos: int) -> np.ndarray:
        """Boolean mask of hero ids playable on position 1..5."""
        share = self.pos_mat[:, pos - 1]
        return share >= MIN_POS_SHARE

    # ---- suggestions -------------------------------------------------------------------------

    def suggest(self, allies: list[int], enemies: list[int], bans: list[int], pos: int, group: int,
                side: str | None = None, pool: dict | None = None, top: int = 10,
                comfort_weight: float = COMFORT_WEIGHT, offrole_top: int = 3) -> dict[str, list[dict]]:
        """{'main': top heroes that usually play this position, 'offrole': best of the rest (10-40%)}.
        pool=None switches personal comfort off completely."""
        taken = set(allies) | set(enemies) | set(bans)
        base = self.evaluate(allies, enemies, group, side)
        z_now = float(np.log(base.p_win / (1 - base.p_win)))
        available = np.array([h in self.heroes and h not in taken for h in range(self.n_ids)])
        cand = np.nonzero(available & self.playable(pos))[0]
        enemy_left = max(0, 5 - len(enemies))
        # pick probability of each still-available hero for the enemy's next picks
        q = self.pick_rate[group] * available
        q = q / q.sum() if q.sum() > 0 else q
        out = []
        for h in cand:
            ph = (pool or {}).get("heroes", {}).get(h)
            familiar = bool(ph and ph["games"] >= COMFORT_MIN_GAMES)
            strength = self.cal_a * self.strength(h, group)
            specialist = bool(self.pick_rate[group, h] < SPECIALIST_PICK_RATE and self.lw[group, h] > 0.06)
            if specialist and not familiar and strength > 0:
                # the high winrate belongs to the few who main this hero; don't promise it to others
                strength = 0.0
            terms = [Term("hero", [h], strength)]
            terms += [Term("synergy", [h, a], self.cal_a * self.S[h, a]) for a in allies]
            terms += [Term("counter", [h, e], self.cal_a * self.C[h, e]) for e in enemies]
            # expected counter from enemy picks still to come (excluding h itself)
            qh = q.copy()
            qh[h] = 0
            qh = qh / qh.sum() if qh.sum() > 0 else qh
            threat = qh * self.C[:, h]                                     # C[e, h] > 0: e beats h
            risk = -self.cal_a * enemy_left * float(threat.sum())
            if enemy_left:
                by = [int(e) for e in np.argsort(-threat)[:3] if threat[e] > 0]
                terms.append(Term("risk", by, risk))
            if pool and pool.get("experience") and comfort_weight > 0:
                games = ph["games"] if ph else 0
                exp = me.experience_term(games, pool["experience"])
                edge = ph["edge"] if ph else 0.0
                note = f"{games} игр" + (f", {ph['wins'] / games * 100:.0f}% побед" if games else "")
                terms.append(Term("comfort", [h], comfort_weight * (exp + edge), note))
            dz = sum(t.value for t in terms)
            p_after = float(expit(z_now + dz))
            out.append({
                "hero": int(h), "score": dz, "p_win": p_after, "delta": p_after - base.p_win,
                "pos_share": float(self.pos_mat[h, pos - 1]),
                "meta_wr": float(expit(self.lw[group, h])),
                "pick_rate": float(self.pick_rate[group, h]),
                "specialist": specialist and not familiar,
                "terms": sorted(terms, key=lambda t: -abs(t.value)),
            })
        out.sort(key=lambda r: -r["score"])
        main = [r for r in out if r["pos_share"] >= MAIN_POS_SHARE][:top]
        offrole = [r for r in out if r["pos_share"] < MAIN_POS_SHARE][:offrole_top]
        return {"main": main, "offrole": offrole}

    def bans(self, allies: list[int], enemies: list[int], bans: list[int], pos: int, group: int,
             pool: dict | None = None, top: int = 5) -> list[dict]:
        """Threat of each hero = P(enemy picks it) * how much it would lower our win chance.
        Before picks, 'our heroes' are the user's comfort heroes for the chosen position."""
        taken = set(allies) | set(enemies) | set(bans)
        ours = list(allies)
        if not ours and pool and pool.get("heroes"):
            playable = self.playable(pos)
            ours = [h for h, v in sorted(pool["heroes"].items(), key=lambda kv: -kv[1]["games"])
                    if playable[h] and v["games"] >= COMFORT_MIN_GAMES][:3]
        q = self.pick_rate[group].copy()
        out = []
        for e in self.heroes:
            if e in taken:
                continue
            terms = [Term("hero", [e], self.cal_a * self.strength(e, group))]
            terms += [Term("counter", [e, a], self.cal_a * self.C[e, a]) for a in ours]
            harm = sum(t.value for t in terms)                    # enemy's gain in log-odds
            out.append({"hero": e, "threat": float(q[e] * harm), "harm": harm, "pick_rate": float(q[e]),
                        "against": ours, "terms": sorted(terms, key=lambda t: -abs(t.value))})
        out.sort(key=lambda r: -r["threat"])
        return out[:top]


@cache
def get() -> Predictor:
    return Predictor()
