"""A hero newer than the trained model: per-hero arrays grow, the new hero is neutral."""

import numpy as np

from drafter.model.predictor import Predictor


def test_new_hero_grows_every_per_hero_array():
    p = Predictor.__new__(Predictor)
    n, g = 4, 3
    p.n_ids = n
    p.S, p.C = np.ones((n, n)), np.ones((n, n))
    p.pair_games = (np.ones((n, n)), np.ones((n, n)))
    p.hero_w, p.hero_group_w = np.ones(n), np.ones((g, n))
    p.pick_rate, p.lw, p.pos_mat = np.ones((g, n)), np.ones((g, n)), np.ones((n, 5))
    p._grow_to(6)
    assert p.n_ids == 6
    assert p.S.shape == (6, 6) and p.pair_games[1].shape == (6, 6) and p.hero_group_w.shape == (g, 6)
    assert p.pos_mat.shape == (6, 5) and p.pick_rate.shape == (g, 6)
    assert p.hero_w[5] == 0 and p.S[5].sum() == 0 and p.pos_mat[5].sum() == 0 and p.hero_w[3] == 1
    p._grow_to(5)  # never shrinks
    assert p.n_ids == 6
