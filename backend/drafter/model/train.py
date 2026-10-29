"""Train and honestly evaluate the draft win-probability models.

Split by time: train on older days, validate on the next ones, test on the newest.
Hero and pair statistics come from the training part only; for training rows the pair
statistics are out-of-fold so the model never sees a match's own result in its features.

Models compared on the same test set and draft stages:
  baseline  - sum of per-hero winrate log-odds (by rank group), intercept + scale fitted
  lr        - logistic regression: hero strength (global + rank group) + synergy + counters
  lgbm      - gradient boosting on aggregated draft features (strength, synergy, counters,
              position coverage, attack types, rank)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import joblib
import lightgbm as lgb
import numpy as np
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from .. import config
from ..data import constants, matches
from . import draft, positions

ART = config.DATA / "model"
STAGES = [(5, 5), (4, 4), (3, 3), (2, 2), (1, 1)]
K_FOLDS = 5
DAY = 86400


@dataclass
class Split:
    R: np.ndarray
    D: np.ndarray
    y: np.ndarray
    group: np.ndarray
    tier: np.ndarray

    def __len__(self):
        return len(self.y)

    def take(self, idx):
        return Split(self.R[idx], self.D[idx], self.y[idx], self.group[idx], self.tier[idx])


def load_splits(test_days: float = 2, valid_days: float = 2, max_train: int | None = None, log=print):
    df = matches.load()
    t = df["start_time"].to_numpy()
    t_end = t.max()
    span_days = (t_end - t.min()) / DAY
    if span_days < 3 * (test_days + valid_days):  # little data: fall back to fractions
        q_test, q_valid = np.quantile(t, [0.85, 0.70])
    else:
        q_test, q_valid = t_end - test_days * DAY, t_end - (test_days + valid_days) * DAY
    R = df.select([f"r{i}" for i in range(5)]).to_numpy().astype(np.int64)
    D = df.select([f"d{i}" for i in range(5)]).to_numpy().astype(np.int64)
    y = df["radiant_win"].to_numpy().astype(np.float64)
    tier = df["avg_rank_tier"].to_numpy().astype(np.int64)
    full = Split(R, D, y, draft.rank_group(tier), tier)
    tr, va, te = np.nonzero(t < q_valid)[0], np.nonzero((t >= q_valid) & (t < q_test))[0], np.nonzero(t >= q_test)[0]
    if max_train and len(tr) > max_train:
        tr = tr[-max_train:]  # keep the most recent
    fmt = lambda x: time.strftime("%Y-%m-%d %H:%M", time.localtime(x))
    info = {
        "matches": int(len(df)), "train": int(len(tr)), "valid": int(len(va)), "test": int(len(te)),
        "train_period": [fmt(t[tr].min()), fmt(t[tr].max())],
        "valid_period": [fmt(t[va].min()), fmt(t[va].max())],
        "test_period": [fmt(t[te].min()), fmt(t[te].max())],
    }
    log(f"матчей {info['matches']:,}: обучение {info['train']:,}, валидация {info['valid']:,}, тест {info['test']:,}")
    return full.take(tr), full.take(va), full.take(te), info


# ---------- metrics ----------

def ece(y, p, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            tot += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(tot)


def metrics(y, p) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {"logloss": log_loss(y, p), "brier": brier_score_loss(y, p), "auc": roc_auc_score(y, p),
            "acc": float(((p > 0.5) == (y > 0.5)).mean()), "ece": ece(y, p)}


class Platt:
    """Logistic calibration on top of a model's log-odds, fitted on the validation set."""

    def fit(self, z, y):
        self.lr = LogisticRegression(C=1e6).fit(z.reshape(-1, 1), y)
        return self

    def __call__(self, z):
        return self.lr.predict_proba(np.asarray(z).reshape(-1, 1))[:, 1]


# ---------- models ----------

class AdditiveModel:
    """Hero strength + synergy + counters, all in log-odds. Used for prediction and explanations."""

    def __init__(self, n_ids: int, C_reg: float = 0.05, pair_k: float = 200.0):
        self.n_ids, self.C_reg, self.pair_k = n_ids, C_reg, pair_k

    def _hero_fit(self, s: Split, sample_weight=None):
        X = draft.hero_design(s.R, s.D, s.group, self.n_ids)
        return LogisticRegression(C=self.C_reg, max_iter=300).fit(X, s.y, sample_weight=sample_weight)

    def fit(self, s: Split, rng, log=print):
        n = self.n_ids
        log("  сила героев (только обучение)…")
        hero = self._hero_fit(s)
        p0 = hero.predict_proba(draft.hero_design(s.R, s.D, s.group, n))[:, 1]

        log(f"  пары героев, {K_FOLDS} фолдов out-of-fold…")
        fold = rng.integers(0, K_FOLDS, len(s))
        per_fold = [draft.PairStats(n).add(s.R[fold == f], s.D[fold == f], s.y[fold == f], p0[fold == f])
                    for f in range(K_FOLDS)]
        total = draft.PairStats(n)
        for st in per_fold:
            total = total.plus(st)
        self.pairs = total
        self.S, self.C = total.effects(self.pair_k)

        # training rows: full drafts + one masked copy, pair features out-of-fold
        Rm, Dm = draft.mask_drafts(s.R, s.D, rng)
        R2, D2 = np.vstack([s.R, Rm]), np.vstack([s.D, Dm])
        f2 = np.concatenate([fold, fold])
        pf = np.zeros((len(R2), 3))
        for f in range(K_FOLDS):
            S_f, C_f = total.minus(per_fold[f]).effects(self.pair_k)
            m = f2 == f
            pf[m] = draft.pair_features(R2[m], D2[m], S_f, C_f)
        g2, y2 = np.concatenate([s.group, s.group]), np.concatenate([s.y, s.y])
        X = self._design(R2, D2, g2, pf)
        log("  итоговая логистическая регрессия…")
        self.lr = LogisticRegression(C=self.C_reg, max_iter=500).fit(X, y2)
        return self

    def _design(self, R, D, group, pf):
        import scipy.sparse as sp
        Xh = draft.hero_design(R, D, group, self.n_ids)
        return sp.hstack([Xh, sp.csr_matrix(np.column_stack([pf[:, 0] - pf[:, 1], pf[:, 2]]))]).tocsr()

    def logit(self, R, D, group):
        pf = draft.pair_features(R, D, self.S, self.C)
        return self.lr.decision_function(self._design(R, D, group, pf))

    @property
    def weights(self) -> dict:
        w = self.lr.coef_[0]
        n = self.n_ids
        return {"intercept": float(self.lr.intercept_[0]), "hero": w[:n], "hero_group": w[n:n * (1 + draft.N_GROUPS)].reshape(draft.N_GROUPS, n),
                "syn": float(w[-2]), "cnt": float(w[-1])}


def baseline_fit(s: Split, n_ids: int, prior: float = 50):
    """Per-hero winrate by rank group (shrunk to 50%), summed as log-odds."""
    wins = np.zeros((draft.N_GROUPS, n_ids)) + prior / 2
    games = np.zeros((draft.N_GROUPS, n_ids)) + prior
    for T, won in ((s.R, s.y), (s.D, 1 - s.y)):
        for i in range(5):
            np.add.at(games, (s.group, T[:, i]), 1)
            np.add.at(wins, (s.group, T[:, i]), won)
    lw = logit(wins / games)
    lw[:, 0] = 0
    return lw


def baseline_score(lw, R, D, group):
    return lw[group[:, None], R].sum(1) - lw[group[:, None], D].sum(1)


def team_features(R, D, pos_mat, attack_melee):
    """Position coverage and melee count for each side; index 0 (empty) contributes nothing."""
    out = []
    for T in (R, D):
        cov = pos_mat[T].sum(axis=1)                    # (n, 5) expected heroes per position
        out += [cov, np.maximum(0, 1 - cov).sum(1, keepdims=True), attack_melee[T].sum(1, keepdims=True)]
    return np.hstack(out)


def run(max_train: int | None = 4_000_000, seed: int = 0, log=print) -> dict:
    t0 = time.monotonic()
    rng = np.random.default_rng(seed)
    n_ids = max(h["id"] for h in constants.hero_index()) + 1
    tr, va, te, info = load_splits(max_train=max_train, log=log)

    # --- baseline
    log("бейзлайн…")
    lw = baseline_fit(tr, n_ids)
    base_cal = LogisticRegression(C=1e6).fit(baseline_score(lw, tr.R, tr.D, tr.group).reshape(-1, 1), tr.y)

    # --- additive LR; pick pair shrinkage k on validation
    best = None
    for k in (200.0, 800.0, 3200.0):
        log(f"аддитивная модель, сглаживание пар k={k:g}")
        m = AdditiveModel(n_ids, pair_k=k).fit(tr, np.random.default_rng(seed), log=log)
        ll = log_loss(va.y, expit(m.logit(va.R, va.D, va.group)))
        log(f"  валидация logloss {ll:.5f}")
        if best is None or ll < best[0]:
            best = (ll, m)
    add = best[1]
    log(f"выбрано k={add.pair_k:g}")

    # --- LightGBM on aggregated features
    log("бустинг…")
    try:
        pos = positions.load()
    except FileNotFoundError:
        pos = positions.run(log=log)
    pos_mat = np.zeros((n_ids, 5))
    for h, v in pos.items():
        pos_mat[h] = v
    melee = np.zeros(n_ids)
    for h in constants.hero_index():
        melee[h["id"]] = h["attack"] == "Melee"
    w = add.weights

    def gbm_X(R, D, group, tier):
        hero_part = (w["hero"][R].sum(1) - w["hero"][D].sum(1)
                     + w["hero_group"][group[:, None], R].sum(1) - w["hero_group"][group[:, None], D].sum(1))
        pf = draft.pair_features(R, D, add.S, add.C)
        nvis = np.column_stack([(R > 0).sum(1), (D > 0).sum(1)])
        return np.column_stack([hero_part, pf, tier // 10, nvis, team_features(R, D, pos_mat, melee)])

    Rm, Dm = draft.mask_drafts(tr.R, tr.D, rng)
    Xtr = gbm_X(np.vstack([tr.R, Rm]), np.vstack([tr.D, Dm]), np.concatenate([tr.group] * 2), np.concatenate([tr.tier] * 2))
    ytr = np.concatenate([tr.y, tr.y])
    Rv, Dv = draft.mask_drafts(va.R, va.D, rng)
    Xva = gbm_X(np.vstack([va.R, Rv]), np.vstack([va.D, Dv]), np.concatenate([va.group] * 2), np.concatenate([va.tier] * 2))
    yva = np.concatenate([va.y, va.y])
    gbm = lgb.LGBMClassifier(n_estimators=2000, learning_rate=0.03, num_leaves=31, min_child_samples=500,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
    gbm.fit(Xtr, ytr, eval_X=(Xva,), eval_y=(yva,), callbacks=[lgb.early_stopping(100, verbose=False)])
    log(f"  деревьев: {gbm.best_iteration_}")

    # --- calibration on validation (full + masked drafts)
    Rvv, Dvv, gvv, tvv = np.vstack([va.R, Rv]), np.vstack([va.D, Dv]), np.concatenate([va.group] * 2), np.concatenate([va.tier] * 2)
    z = {
        "baseline": base_cal.decision_function(baseline_score(lw, Rvv, Dvv, gvv).reshape(-1, 1)),
        "lr": add.logit(Rvv, Dvv, gvv),
        "lgbm": logit(np.clip(gbm.predict_proba(Xva)[:, 1], 1e-6, 1 - 1e-6)),
    }
    cal = {name: Platt().fit(zz, yva) for name, zz in z.items()}

    def predict(name, R, D, group, tier):
        if name == "baseline":
            zz = base_cal.decision_function(baseline_score(lw, R, D, group).reshape(-1, 1))
        elif name == "lr":
            zz = add.logit(R, D, group)
        else:
            zz = logit(np.clip(gbm.predict_proba(gbm_X(R, D, group, tier))[:, 1], 1e-6, 1 - 1e-6))
        return cal[name](zz)

    # --- test: by draft stage, and by rank for full drafts
    log("тест…")
    results = {"stages": {}, "ranks": {}}
    trng = np.random.default_rng(seed + 1)
    for st in STAGES:
        R, D = (te.R, te.D) if st == (5, 5) else draft.mask_drafts(te.R, te.D, trng, st)
        results["stages"][f"{st[0]}v{st[1]}"] = {name: metrics(te.y, predict(name, R, D, te.group, te.tier))
                                               for name in ("baseline", "lr", "lgbm")}
    for g in range(1, 8):
        m = te.tier // 10 == g
        if m.sum() < 2000:
            continue
        sub = te.take(np.nonzero(m)[0])
        results["ranks"][constants_rank(g)] = {"n": int(m.sum()), **{
            name: metrics(sub.y, predict(name, sub.R, sub.D, sub.group, sub.tier)) for name in ("baseline", "lr", "lgbm")}}
    p_lr = predict("lr", te.R, te.D, te.group, te.tier)
    results["calibration_lr"] = calibration_curve(te.y, p_lr)
    results["radiant_wr_test"] = float(te.y.mean())

    # pick probability per match by rank group, for counter-pick risk and ban suggestions
    picks = np.zeros((draft.N_GROUPS, n_ids))
    for T in (tr.R, tr.D):
        for i in range(5):
            np.add.at(picks, (tr.group, T[:, i]), 1)
    pick_rate = picks / np.maximum(np.bincount(tr.group, minlength=draft.N_GROUPS), 1)[:, None]

    ART.mkdir(parents=True, exist_ok=True)
    joblib.dump({"additive": add, "lw": lw, "base_cal": base_cal, "gbm": gbm, "cal": cal,
                 "pos_mat": pos_mat, "melee": melee, "n_ids": n_ids, "pick_rate": pick_rate},
                ART / "models.joblib", compress=3)
    meta = {"trained": time.strftime("%Y-%m-%d %H:%M"), "patch": constants.current_patch()["name"],
            "data": info, "pair_k": add.pair_k, "lr_weights": {"syn": w["syn"], "cnt": w["cnt"]},
            "gbm_trees": int(gbm.best_iteration_), "results": results, "seconds": round(time.monotonic() - t0)}
    tmp = ART / "meta.json.tmp"
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ART / "meta.json")
    log(f"готово за {meta['seconds']} с")
    return meta


def calibration_curve(y, p, bins: int = 10):
    edges = np.linspace(0.3, 0.7, bins + 1)
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (p >= a) & (p < b)
        if m.sum() >= 200:
            out.append({"pred": float(p[m].mean()), "real": float(y[m].mean()), "n": int(m.sum())})
    return out


def constants_rank(g: int) -> str:
    return ["", "Herald", "Guardian", "Crusader", "Archon", "Legend", "Ancient", "Divine", "Immortal"][g]
