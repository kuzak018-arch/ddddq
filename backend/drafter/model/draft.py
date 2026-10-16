"""Draft representation and the additive win model's building blocks.

A draft is two (n, 5) int arrays of hero ids (Radiant, Dire); 0 means "not picked yet".
The model is linear in log-odds, so every prediction decomposes exactly into
per-hero strength, ally-pair synergy and cross-team counter terms, which is what the
explanations in the UI show.
"""

from __future__ import annotations

import itertools

import numpy as np
import scipy.sparse as sp

N_GROUPS = 3  # rank groups for hero strength: Herald-Crusader, Archon-Legend, Ancient-Divine(+)
ALLY_PAIRS = list(itertools.combinations(range(5), 2))
CROSS_PAIRS = list(itertools.product(range(5), range(5)))


def rank_group(avg_rank_tier: np.ndarray | int) -> np.ndarray:
    tier = np.asarray(avg_rank_tier) // 10
    return np.clip(np.where(tier <= 3, 0, np.where(tier <= 5, 1, 2)), 0, N_GROUPS - 1)


def mask_drafts(R: np.ndarray, D: np.ndarray, rng: np.random.Generator,
                stage: tuple[int, int] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Hide heroes to emulate an unfinished draft. stage=(k_r, k_d) or random per row."""
    n = len(R)
    if stage is None:
        k = rng.integers(1, 6, size=n)
        kr = k
        kd = np.clip(k + rng.integers(-1, 2, size=n), 0, 5)
        swap = rng.random(n) < 0.5
        kr, kd = np.where(swap, kd, kr), np.where(swap, kr, kd)
    else:
        kr, kd = np.full(n, stage[0]), np.full(n, stage[1])
    out = []
    for T, k in ((R, kr), (D, kd)):
        order = rng.random(T.shape).argsort(axis=1)        # random visible subset
        keep = order < k[:, None]
        out.append(np.where(keep, T, 0))
    return out[0], out[1]


def hero_design(R: np.ndarray, D: np.ndarray, group: np.ndarray, n_ids: int) -> sp.csr_matrix:
    """Columns: global hero strength (n_ids) + per rank-group hero strength (N_GROUPS * n_ids).
    +1 for a Radiant hero, -1 for a Dire hero, nothing for empty slots."""
    n = len(R)
    rows, cols, vals = [], [], []
    for T, sign in ((R, 1.0), (D, -1.0)):
        for i in range(5):
            h = T[:, i]
            ok = h > 0
            idx = np.nonzero(ok)[0]
            rows += [idx, idx]
            cols += [h[ok], n_ids * (1 + group[ok]) + h[ok]]
            vals += [np.full(len(idx), sign)] * 2
    return sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                         shape=(n, n_ids * (1 + N_GROUPS)))


class PairStats:
    """Synergy S[a, b] (symmetric) and counter C[a, b] (antisymmetric, a's team vs b's team)
    as one ridge-Newton step on top of a hero-only model: effect = sum(residual) / (sum(var) + k)."""

    def __init__(self, n_ids: int):
        self.n = n_ids
        nn = n_ids * n_ids
        self.syn_num, self.syn_den = np.zeros(nn), np.zeros(nn)
        self.cnt_num, self.cnt_den = np.zeros(nn), np.zeros(nn)

    def add(self, R, D, y, p) -> "PairStats":
        n = self.n
        resid, var = y - p, p * (1 - p)
        for T, sign in ((R, 1.0), (D, -1.0)):
            for i, j in ALLY_PAIRS:
                a, b = T[:, i], T[:, j]
                ok = (a > 0) & (b > 0)
                key = np.minimum(a, b)[ok] * n + np.maximum(a, b)[ok]
                self.syn_num += np.bincount(key, sign * resid[ok], n * n)
                self.syn_den += np.bincount(key, var[ok], n * n)
        for i, j in CROSS_PAIRS:
            a, b = R[:, i], D[:, j]
            ok = (a > 0) & (b > 0)
            k1, k2 = a[ok] * n + b[ok], b[ok] * n + a[ok]
            self.cnt_num += np.bincount(k1, resid[ok], n * n) - np.bincount(k2, resid[ok], n * n)
            v = np.bincount(k1, var[ok], n * n) + np.bincount(k2, var[ok], n * n)
            self.cnt_den += v
        return self

    def _combine(self, other: "PairStats", sign: float) -> "PairStats":
        out = PairStats(self.n)
        for f in ("syn_num", "syn_den", "cnt_num", "cnt_den"):
            setattr(out, f, getattr(self, f) + sign * getattr(other, f))
        return out

    def plus(self, other: "PairStats") -> "PairStats":
        return self._combine(other, 1.0)

    def minus(self, other: "PairStats") -> "PairStats":
        return self._combine(other, -1.0)

    def effects(self, k: float) -> tuple[np.ndarray, np.ndarray]:
        S = (self.syn_num / (self.syn_den + k)).reshape(self.n, self.n)
        S = np.triu(S, 1)
        S = S + S.T
        C = (self.cnt_num / (self.cnt_den + k)).reshape(self.n, self.n)
        return S, C

    def games(self) -> tuple[np.ndarray, np.ndarray]:
        """Approximate games per pair (variance sum / 0.25), for 'how sure are we' in the UI."""
        g_s = (self.syn_den / 0.25).reshape(self.n, self.n)
        g_s = np.triu(g_s, 1)
        return g_s + g_s.T, (self.cnt_den / 0.5).reshape(self.n, self.n)


def pair_features(R, D, S, C) -> np.ndarray:
    """(n, 3): synergy of Radiant, synergy of Dire, counter advantage of Radiant over Dire."""
    out = np.zeros((len(R), 3))
    for col, T in ((0, R), (1, D)):
        for i, j in ALLY_PAIRS:
            out[:, col] += S[T[:, i], T[:, j]]
    for i, j in CROSS_PAIRS:
        out[:, 2] += C[R[:, i], D[:, j]]
    return out  # index 0 is the empty slot: S[0, :] = C[0, :] = 0
