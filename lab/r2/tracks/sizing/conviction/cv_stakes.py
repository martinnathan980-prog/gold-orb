"""Stake multipliers of the families (i), (i-pool) and (ii) of declared.json, fitted walk-forward.

Every function takes the signal tables and baseline chains of ONE cost mode and returns, per sleeve, one stake per
signal (aligned with the signal table, oid = row number) plus the fitted quantities of every fold, so that the
truncation test can recompute any decision. A training set for fold year Y only holds baseline chain trades whose
exit_time <= 1 January Y - 7 days (V.train_cut_ns)."""
import numpy as np
import pandas as pd

import cv_common as V

MIN_TRAIN = 60
MIN_GROUP = 10
ZERO_BAR = 0.02


# ------------------------------------------------------------------------------------------- tables
def tables(mode):
    """{k: (signals, training table)}; the training table = baseline chain trades with their descriptors"""
    out = {}
    for k in V.KEYS:
        s = V.load_signals(k, mode)
        assert (s.oid.to_numpy() == np.arange(len(s))).all()
        ch = V.load_chain(k, mode)
        tr = s.set_index("oid").loc[ch.oid.to_numpy()].reset_index()
        tr["exit_ns"] = V.ns(ch.exit_time)
        tr["entry_ns"] = V.ns(ch.entry_time)
        tr["R"] = ch.R.to_numpy()
        assert np.allclose(tr.R.to_numpy(), tr.chain_R.to_numpy(), rtol=0, atol=1e-12)
        out[k] = (s, tr)
    return out


def train_rows(tr, y):
    return tr[tr.exit_ns.to_numpy() <= V.train_cut_ns(y)]


# ------------------------------------------------------------------------------------------- one descriptor
def split(x, q):
    x = x[np.isfinite(x)]
    if len(x) < MIN_TRAIN:
        return None
    b_lo, b_hi = np.quantile(x, [q, 1 - q])
    if not b_lo < b_hi:
        return None
    return float(b_lo), float(b_hi)


def welch(y_hi, y_lo):
    se = np.sqrt(y_hi.var(ddof=1) / len(y_hi) + y_lo.var(ddof=1) / len(y_lo))
    return float((y_hi.mean() - y_lo.mean()) / se) if se > 0 else 0.0


def separation(x, y, q):
    """fit of one descriptor on training values: boundaries, group means, Welch t (hi - lo); None if not eligible"""
    sp = split(x, q)
    if sp is None:
        return None
    b_lo, b_hi = sp
    with np.errstate(invalid="ignore"):
        lo = np.isfinite(x) & (x <= b_lo)
        hi = np.isfinite(x) & (x >= b_hi)
    if lo.sum() < MIN_GROUP or hi.sum() < MIN_GROUP:
        return None
    return {"b_lo": b_lo, "b_hi": b_hi, "n_lo": int(lo.sum()), "n_hi": int(hi.sum()),
            "m_lo": float(y[lo].mean()), "m_hi": float(y[hi].mean()),
            "m_mid": float(y[np.isfinite(x) & ~lo & ~hi].mean()) if (np.isfinite(x) & ~lo & ~hi).any() else None,
            "t": welch(y[hi], y[lo]), "n": int(np.isfinite(x).sum())}


def apply_groups(x, b_lo, b_hi):
    """0 = lo, 1 = mid, 2 = hi, -1 = NaN"""
    x = np.asarray(x, float)
    g = np.full(len(x), -1, np.int64)
    f = np.isfinite(x)
    g[f] = 1
    g[f & (x <= b_lo)] = 0
    g[f & (x >= b_hi)] = 2
    return g


def stakes_from_groups(g, worst, stake_worst):
    """worst = 'lo' or 'hi'"""
    st = np.ones(len(g))
    w, b = (0, 2) if worst == "lo" else (2, 0)
    st[g == w] = stake_worst
    st[g == b] = 1.5
    return st


def worst_stake(m_worst, nozero):
    return 0.5 if (nozero or m_worst > ZERO_BAR) else 0.0


# ------------------------------------------------------------------------------------------- family (i)
def fit_i(tr, y, q, descriptors=None):
    """all eligible descriptors' fits for fold year y on the sleeve's training rows"""
    t = train_rows(tr, y)
    R = t.R.to_numpy(float)
    fits = {}
    for d in (descriptors or V.ELIGIBLE):
        f = separation(t[d].to_numpy(float), R, q)
        if f is not None:
            fits[d] = f
    return fits, int(len(t))


def decide_i(fits, nozero, t_min=None):
    """choice of family (i) for one sleeve-year: descriptor, direction, boundaries, worst stake (or None = stake 1)"""
    if not fits:
        return None
    d = max(fits, key=lambda q: (abs(fits[q]["t"]), q))
    f = fits[d]
    if t_min is not None and abs(f["t"]) < t_min:
        return None
    worst = "lo" if f["t"] > 0 else "hi"
    m_w = f["m_lo"] if worst == "lo" else f["m_hi"]
    return {"descriptor": d, "worst": worst, "b_lo": f["b_lo"], "b_hi": f["b_hi"], "t": f["t"],
            "m_worst": m_w, "m_best": f["m_hi"] if worst == "lo" else f["m_lo"], "stake_worst": worst_stake(m_w, nozero)}


def family_i(T, q, nozero=False, t_min=None, years=V.OOF_YEARS):
    out, info = {}, {}
    for k, (s, tr) in T.items():
        st = np.ones(len(s))
        info[k] = {}
        for y in years:
            fits, n_tr = fit_i(tr, y, q)
            dec = decide_i(fits, nozero, t_min)
            info[k][y] = {"n_train": n_tr, "decision": dec,
                          "best_t_by_descriptor": {d: round(f["t"], 3) for d, f in fits.items()}}
            if dec is None:
                continue
            m = s.year.to_numpy() == y
            g = apply_groups(s.loc[m, dec["descriptor"]].to_numpy(float), dec["b_lo"], dec["b_hi"])
            st[m] = stakes_from_groups(g, dec["worst"], dec["stake_worst"])
        out[k] = st
    return out, info


def family_i_pool(T, q, years=V.OOF_YEARS):
    """V23-V25: the crypto breakouts share one descriptor choice; the other sleeves as family_i (same q)"""
    out, info = family_i({k: v for k, v in T.items() if k not in V.CRYPTO_BRK}, q)
    for k in V.CRYPTO_BRK:
        out[k] = np.ones(len(T[k][0]))
        info[k] = {}
    for y in years:
        per = {k: fit_i(T[k][1], y, q) for k in V.CRYPTO_BRK}
        common_d = [d for d in V.ELIGIBLE if all(d in per[k][0] for k in V.CRYPTO_BRK)]
        if not common_d:
            for k in V.CRYPTO_BRK:
                info[k][y] = {"n_train": per[k][1], "decision": None}
            continue
        tsum = {d: sum(per[k][0][d]["t"] for k in V.CRYPTO_BRK) for d in common_d}
        d = max(tsum, key=lambda q_: (abs(tsum[q_]), q_))
        worst = "lo" if tsum[d] > 0 else "hi"
        for k in V.CRYPTO_BRK:
            s = T[k][0]
            f = per[k][0][d]
            m_w = f["m_lo"] if worst == "lo" else f["m_hi"]
            dec = {"descriptor": d, "worst": worst, "b_lo": f["b_lo"], "b_hi": f["b_hi"], "t": f["t"],
                   "t_sum": tsum[d], "m_worst": m_w, "stake_worst": worst_stake(m_w, False)}
            info[k][y] = {"n_train": per[k][1], "decision": dec,
                          "t_sum_by_descriptor": {q_: round(v, 3) for q_, v in tsum.items()}}
            m = s.year.to_numpy() == y
            g = apply_groups(s.loc[m, d].to_numpy(float), f["b_lo"], f["b_hi"])
            out[k][m] = stakes_from_groups(g, worst, dec["stake_worst"])
    return out, info


# ------------------------------------------------------------------------------------------- family (ii)
def zscore_fit(X):
    mu = np.nanmean(X, axis=0)
    sd = np.nanstd(X, axis=0)
    ok = np.isfinite(mu) & np.isfinite(sd) & (sd > 0)
    return np.where(ok, mu, 0.0), np.where(ok, sd, 1.0), ok


def zscore(X, mu, sd, ok):
    Z = np.clip((X - mu) / sd, -4, 4)
    Z = np.where(np.isfinite(Z), Z, 0.0)
    Z[:, ~ok] = 0.0
    return Z


def ridge_fit(Zc, yc, alpha):
    p = Zc.shape[1]
    return np.linalg.solve(Zc.T @ Zc + alpha * np.eye(p), Zc.T @ yc)


def fit_ii(T, keys, y, alpha_factor, q, n_keep=6, descriptors=None):
    """pooled (or single-sleeve) ridge for fold year y: per-sleeve standardisation, within-sleeve demeaning,
    screening of n_keep descriptors by |corr|, ridge, pooled split of the score"""
    desc = list(descriptors)
    Zs, ys, ids, stand = [], [], [], {}
    for k in keys:
        t = train_rows(T[k][1], y)
        X = t[desc].to_numpy(float)
        mu, sd, ok = zscore_fit(X)
        stand[k] = (mu, sd, ok)
        Z = zscore(X, mu, sd, ok)
        yy = np.clip(t.R.to_numpy(float), -2, 4)
        Zs.append(Z - Z.mean(axis=0))
        ys.append(yy - yy.mean())
        ids.append(np.full(len(t), keys.index(k)))
    Zc = np.vstack(Zs)
    yc = np.concatenate(ys)
    ids = np.concatenate(ids)
    n = len(yc)
    if n < MIN_TRAIN:
        return None
    sz = Zc.std(axis=0)
    corr = np.where(sz > 0, (Zc * yc[:, None]).mean(axis=0) / np.where(sz > 0, sz, 1) / yc.std(), 0.0)
    order = sorted(range(len(desc)), key=lambda j: (-abs(corr[j]), desc[j]))
    keep = [j for j in order if sz[j] > 0][:n_keep]
    beta = ridge_fit(Zc[:, keep], yc, alpha_factor * n)
    # training scores (raw z, not demeaned: the score of a trade is beta . z with its sleeve's standardisation)
    sc_tr, R_tr = [], []
    for k in keys:
        t = train_rows(T[k][1], y)
        mu, sd, ok = stand[k]
        Z = zscore(t[desc].to_numpy(float), mu, sd, ok)
        sc_tr.append(Z[:, keep] @ beta)
        R_tr.append(t.R.to_numpy(float))
    sc_all = np.concatenate(sc_tr)
    b_lo, b_hi = np.quantile(sc_all, [q, 1 - q])
    m_lo = {}
    for k, sc, R in zip(keys, sc_tr, R_tr):
        lo = sc <= b_lo
        m_lo[k] = float(R[lo].mean()) if lo.any() else float("nan")
    return {"descriptors": [desc[j] for j in keep], "keep_idx": keep, "beta": beta.tolist(),
            "corr": {desc[j]: round(float(corr[j]), 4) for j in range(len(desc))}, "alpha": alpha_factor * n,
            "n_train": int(n), "b_lo": float(b_lo), "b_hi": float(b_hi), "m_lo": m_lo,
            "stand": {k: (stand[k][0].tolist(), stand[k][1].tolist(), stand[k][2].tolist()) for k in keys},
            "desc_all": desc}


def score_ii(fit, k, X):
    mu, sd, ok = (np.asarray(v) for v in fit["stand"][k])
    Z = zscore(X, mu, sd, ok.astype(bool))
    return Z[:, fit["keep_idx"]] @ np.asarray(fit["beta"])


def stake_ii(fit, k, X, nozero=False):
    sc = score_ii(fit, k, X)
    st = np.ones(len(sc))
    lo = sc <= fit["b_lo"]
    hi = sc >= fit["b_hi"]
    if fit["b_lo"] < fit["b_hi"]:
        st[lo] = worst_stake(fit["m_lo"][k], nozero)
        st[hi] = 1.5
    return st


def family_ii_pool(T, alpha_factor, q, years=V.OOF_YEARS, nozero=False):
    desc = [d for d in V.ELIGIBLE if d != "rel2"]
    out = {k: np.ones(len(T[k][0])) for k in T}
    info = {k: {} for k in V.CRYPTO_BRK}
    for y in years:
        fit = fit_ii(T, list(V.CRYPTO_BRK), y, alpha_factor, q, 6, desc)
        for k in V.CRYPTO_BRK:
            info[k][y] = fit
            if fit is None:
                continue
            s = T[k][0]
            m = s.year.to_numpy() == y
            out[k][m] = stake_ii(fit, k, s.loc[m, desc].to_numpy(float), nozero)
    return out, info


def family_ii_each(T, alpha_factor=1.0, q=1 / 3, years=V.OOF_YEARS):
    out, info = {}, {}
    for k, (s, tr) in T.items():
        out[k] = np.ones(len(s))
        info[k] = {}
        desc = [d for d in V.ELIGIBLE if np.isfinite(tr[d].to_numpy(float)).any()]
        for y in years:
            fit = fit_ii(T, [k], y, alpha_factor, q, 6, desc)
            info[k][y] = fit
            if fit is None:
                continue
            m = s.year.to_numpy() == y
            out[k][m] = stake_ii(fit, k, s.loc[m, desc].to_numpy(float))
    return out, info


# ------------------------------------------------------------------------------------------- registry
EARLY = {
    "V01": lambda T: family_i(T, 1 / 3),
    "V02": lambda T: family_i(T, 0.25),
    "V03": lambda T: family_i(T, 0.40),
    "V04": lambda T: family_i(T, 1 / 3, nozero=True),
    "V05": lambda T: family_ii_pool(T, 1.0, 1 / 3),
    "V06": lambda T: family_ii_pool(T, 0.5, 1 / 3),
    "V07": lambda T: family_ii_pool(T, 2.0, 1 / 3),
    "V08": lambda T: family_ii_pool(T, 1.0, 0.25),
    "V09": lambda T: family_ii_pool(T, 1.0, 0.40),
    "V10": lambda T: family_ii_each(T, 1.0, 1 / 3),
    "V23": lambda T: family_i_pool(T, 1 / 3),
    "V24": lambda T: family_i_pool(T, 0.25),
    "V25": lambda T: family_i_pool(T, 0.40),
    "V26": lambda T: family_i(T, 1 / 3, t_min=2.0),
    "V27": lambda T: family_i(T, 1 / 3, t_min=1.5),
    "V28": lambda T: family_i(T, 1 / 3, t_min=2.5),
}
