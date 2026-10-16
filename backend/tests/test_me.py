import numpy as np
from scipy.special import expit

from drafter.data import me
from drafter.model import explain
from drafter.model.predictor import Term


def _history(A, k, c, heroes=60, games_per_hero=40, seed=0):
    rng = np.random.default_rng(seed)
    ms, t = [], 0
    for h in range(1, heroes + 1):
        for n in range(games_per_hero):
            t += 1
            p = expit(c - A * k / (k + n))
            ms.append({"hero_id": h, "start_time": t, "player_slot": 0, "radiant_win": bool(rng.random() < p)})
    return {"matches": ms}


def test_experience_curve_recovers_penalty():
    exp = me.fit_experience(_history(A=0.6, k=5, c=0.1))
    assert 0.4 < exp["A"] < 0.8


def test_experience_term_is_smooth_and_fades():
    exp = {"A": 0.6, "k": 12, "c": 0.0}
    vals = [me.experience_term(n, exp) for n in (0, 1, 2, 5, 20, 200)]
    assert all(a < b for a, b in zip(vals, vals[1:]))   # strictly less penalty with more games
    assert vals[0] == -0.6 and abs(vals[-1]) < 0.05


def test_hero_pool_edge_sign():
    data = _history(A=0.0, k=5, c=0.0, heroes=2, games_per_hero=50)
    for m in data["matches"]:
        m["radiant_win"] = m["hero_id"] == 1     # always win on hero 1, always lose on hero 2
    pool = me.hero_pool(data)
    assert pool["heroes"][1]["edge"] > 0 > pool["heroes"][2]["edge"]


def test_negative_synergy_wording(monkeypatch):
    monkeypatch.setattr(explain, "name", lambda h: {1: "Slark", 2: "Pudge"}[h])
    assert "плохо сочетается" in explain.term_text(Term("synergy", [1, 2], -0.02))
    assert explain.term_text(Term("synergy", [1, 2], 0.02)).startswith("синергия")
