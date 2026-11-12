"""Walk-forward fits of the clock lens (declared.json): training tables by hour band or weekday, the worst / best
cell of a fold, and the multiplier of every signal. Pure functions of the reference chains (no frame needed)."""
import numpy as np
import pandas as pd

import common as C

MIN_SLEEVE = 100
MIN_CELL = 20


def cutoff(year):
    """outcomes known before 1 January of `year` minus 7 days"""
    return pd.Timestamp(f"{year}-01-01", tz="UTC") - C.PURGE


def cells(k, ts, dim):
    """cell of each time for sleeve k: hour band number or server weekday; None if the dimension does not apply"""
    if k in C.NO_WEEKDAY:
        return None
    if dim == "H":
        return C.hour_band(k, ts)
    if dim == "D":
        return C.server_weekday(ts)
    raise ValueError(dim)


def table(train_R, train_cell):
    """{cell: (n, mean)} and the pooled (n, mean)"""
    R = np.asarray(train_R, float)
    c = np.asarray(train_cell)
    out = {}
    for v in np.unique(c):
        if v < 0:
            continue
        m = c == v
        out[int(v)] = (int(m.sum()), float(R[m].mean()))
    return out, (int(len(R)), float(R.mean()) if len(R) else float("nan"))


def fit_fold(chain, k, dim, year, family_chains=None):
    """Training table of sleeve k (or of its family when family_chains is given: list of (key, chain)) for `year`."""
    cut = cutoff(year)
    if family_chains is None:
        tr = chain[chain.exit_time < cut]
        cc = cells(k, tr.entry_time, dim)
        if cc is None:
            return None
        R = tr.R.to_numpy(float)
    else:
        Rs, cs = [], []
        for kk, ch in family_chains:
            tr = ch[ch.exit_time < cut]
            cc_ = cells(kk, tr.entry_time, dim)
            if cc_ is None:
                continue
            Rs.append(tr.R.to_numpy(float))
            cs.append(cc_)
        R = np.concatenate(Rs) if Rs else np.zeros(0)
        cc = np.concatenate(cs) if cs else np.zeros(0, np.int64)
    tab, pooled = table(R, cc)
    elig = {c: v for c, v in tab.items() if v[0] >= MIN_CELL}
    acts = pooled[0] >= MIN_SLEEVE and len(elig) >= 2
    res = {"year": year, "cutoff": str(cut), "n_train": pooled[0], "mean_train": pooled[1], "table": tab,
           "eligible": sorted(elig), "acts": bool(acts), "worst": None, "worst_mean": None, "best": None, "best_mean": None}
    if acts:
        w = min(elig, key=lambda c: (elig[c][1], c))
        b = max(elig, key=lambda c: (elig[c][1], -c))
        res.update(worst=int(w), worst_mean=elig[w][1], best=int(b), best_mean=elig[b][1])
    return res


def decide(fit, rule, T=None, F=None):
    """(cell, multiplier) chosen by a fold's fit for a rule 'worst' or 'best', or (None, 1.0)"""
    if fit is None or not fit["acts"]:
        return None, 1.0
    if rule == "worst":
        return (fit["worst"], None) if fit["worst_mean"] <= T + 1e-12 else (None, 1.0)
    if rule == "best":
        if fit["mean_train"] > 0 and fit["best_mean"] >= F * fit["mean_train"] - 1e-12:
            return fit["best"], 1.5
        return None, 1.0
    raise ValueError(rule)
