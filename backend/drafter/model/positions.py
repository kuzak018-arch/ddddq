"""P(position | hero) without per-player data, estimated by EM over team compositions.

Generative model: each team has exactly one hero per position 1..5, and position p draws
its hero from phi[p, :]. For a team of 5 heroes the latent variable is which of the 120
permutations maps heroes to positions. E-step: posterior over permutations; M-step:
phi = expected counts + Dirichlet prior built from OpenDota hero roles. The prior both
regularises rare heroes and anchors the cluster labels to real positions (otherwise the
5 clusters are exchangeable). Stratz, when available, is the reference to validate against.
"""

from __future__ import annotations

import itertools
import json

import numpy as np

from .. import config
from ..data import constants

OUT = config.DATA / "model" / "positions_em.json"
PERMS = np.array(list(itertools.permutations(range(5))), dtype=np.int64)  # (120, 5): hero slot -> position
ONEHOT = np.eye(5)[PERMS]  # (120, slot, position)

# How strongly each OpenDota role points to positions 1..5.
ROLE_AFFINITY = {
    "Carry":     [3.0, 1.5, 1.0, 0.1, 0.0],
    "Support":   [0.0, 0.1, 0.3, 2.0, 3.0],
    "Nuker":     [0.3, 1.2, 0.4, 0.8, 0.5],
    "Initiator": [0.1, 0.5, 1.5, 1.0, 0.4],
    "Durable":   [0.6, 0.4, 1.5, 0.1, 0.0],
    "Disabler":  [0.2, 0.4, 0.8, 0.9, 0.8],
    "Escape":    [0.9, 0.9, 0.3, 0.5, 0.1],
    "Pusher":    [0.6, 0.5, 0.5, 0.2, 0.1],
}


def role_prior(n_heroes: int) -> np.ndarray:
    """(5, n_heroes+1) pseudo-affinity of each hero id to each position."""
    prior = np.full((5, n_heroes + 1), 0.05)
    for h in constants.hero_index():
        for role in h["roles"]:
            prior[:, h["id"]] += ROLE_AFFINITY.get(role, [0] * 5)
    prior[:, 0] = 0
    return prior


def fit(teams: np.ndarray, iters: int = 40, prior_strength: float = 2000.0, chunk: int = 20_000,
        tol: float = 1e-4, log=print) -> np.ndarray:
    """teams: (N, 5) hero ids. Returns phi (5, max_id+1), rows sum to 1."""
    n_ids = int(teams.max()) + 1
    prior = role_prior(n_ids - 1)
    prior_counts = prior / prior.sum(axis=1, keepdims=True) * prior_strength
    phi = prior / prior.sum(axis=1, keepdims=True)
    prev = -np.inf
    for it in range(iters):
        counts = prior_counts.copy()
        ll = 0.0
        logphi = np.log(phi + 1e-12)
        for s in range(0, len(teams), chunk):
            t = teams[s:s + chunk]                              # (n, 5)
            # score[n, k] = sum_i logphi[PERMS[k, i], t[n, i]]
            score = logphi[PERMS[None, :, :], t[:, None, :]].sum(axis=2)   # (n, 120)
            m = score.max(axis=1, keepdims=True)
            w = np.exp(score - m)
            z = w.sum(axis=1, keepdims=True)
            ll += float((np.log(z) + m).sum())
            w /= z
            for i in range(5):
                pos_w = w @ ONEHOT[:, i, :]   # (n, 5): P(hero in slot i plays position p)
                for p in range(5):
                    counts[p] += np.bincount(t[:, i], weights=pos_w[:, p], minlength=n_ids)
        phi = counts / counts.sum(axis=1, keepdims=True)
        ll /= len(teams)
        log(f"  EM {it + 1:>2}: log-likelihood на команду {ll:.4f}")
        if ll - prev < tol:
            break
        prev = ll
    return phi


def pos_given_hero(phi: np.ndarray) -> dict[int, list[float]]:
    out = {}
    for h in constants.hero_index():
        col = phi[:, h["id"]] if h["id"] < phi.shape[1] else np.zeros(5)
        s = col.sum()
        out[h["id"]] = (col / s).round(4).tolist() if s > 0 else [0.2] * 5
    return out


def run(sample_teams: int = 400_000, seed: int = 0, log=print) -> dict[int, list[float]]:
    from ..data import matches
    df = matches.load()
    rad = df.select([f"r{i}" for i in range(5)]).to_numpy()
    dire = df.select([f"d{i}" for i in range(5)]).to_numpy()
    teams = np.vstack([rad, dire]).astype(np.int64)
    rng = np.random.default_rng(seed)
    if len(teams) > sample_teams:
        teams = teams[rng.choice(len(teams), sample_teams, replace=False)]
    log(f"EM позиций на {len(teams):,} командах")
    res = pos_given_hero(fit(teams, log=log))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res))
    return res


def load() -> dict[int, list[float]]:
    return {int(k): v for k, v in json.loads(OUT.read_text()).items()}
