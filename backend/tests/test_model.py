import numpy as np
import pytest

from drafter.model import draft
from drafter.model.train import ece

N = 12


def _random_drafts(rng, n):
    heroes = np.array([rng.permutation(np.arange(1, N))[:10] for _ in range(n)])
    return heroes[:, :5], heroes[:, 5:]


def test_mask_keeps_requested_counts():
    rng = np.random.default_rng(0)
    R, D = _random_drafts(rng, 200)
    Rm, Dm = draft.mask_drafts(R, D, rng, (3, 2))
    assert ((Rm > 0).sum(1) == 3).all() and ((Dm > 0).sum(1) == 2).all()
    # visible heroes are the original ones in the same slots
    assert ((Rm == R) | (Rm == 0)).all()


def test_counter_is_antisymmetric_and_recovers_signal():
    rng = np.random.default_rng(1)
    R, D = _random_drafts(rng, 20000)
    # hero 1 beats hero 2: when they face each other, hero 1's side wins 75%
    r1, d2 = (R == 1).any(1), (D == 2).any(1)
    d1, r2 = (D == 1).any(1), (R == 2).any(1)
    p = np.full(len(R), 0.5)
    p[r1 & d2] = 0.75
    p[d1 & r2] = 0.25
    y = (rng.random(len(R)) < p).astype(float)
    st = draft.PairStats(N).add(R, D, y, np.full(len(R), 0.5))
    S, C = st.effects(k=10)
    assert np.allclose(C, -C.T)
    assert np.allclose(S, S.T)
    assert C[1, 2] > 0.3 and abs(C[3, 4]) < 0.15


def test_pair_features_ignore_empty_slots():
    S = np.ones((N, N))
    S[0, :] = S[:, 0] = 0
    C = np.zeros((N, N))
    R = np.array([[1, 2, 0, 0, 0]])
    D = np.array([[0, 0, 0, 0, 0]])
    assert draft.pair_features(R, D, S, C)[0].tolist() == [1.0, 0.0, 0.0]


def test_ece_perfect_calibration_is_zero():
    y = np.array([0, 1] * 500, dtype=float)
    assert ece(y, np.full(len(y), 0.5)) == pytest.approx(0.0)
