"""Lens `weights`: the stake rules of declared.json, as pure functions of a BOOK. IN SAMPLE ONLY.

A book is a DataFrame of trades of the sleeves of one universe, sorted by entry time then sleeve order, with columns
    k       sleeve key ("<name>__<sym>")
    t_in    entry time, int64 ns UTC
    t_out   exit time, int64 ns UTC; UNKNOWN = INT_MAX (a trade still open at the time the book is cut)
    R       result in R; NaN when unknown
    wk_out  FP server week of the exit (common.week_id); UNKNOWN_WEEK when unknown
    year_in UTC year of the entry
Every rule returns one stake per row computed ONLY from rows whose exit is strictly before the row's own entry
(trailing rules) or before the cutoff of the row's fold year (yearly fits); the truncation tests check it by
cutting the book.
"""
import numpy as np
import pandas as pd

import common as C

INT_MAX = np.iinfo(np.int64).max
UNKNOWN_WEEK = 10 ** 9
NS_DAY = 86_400_000_000_000
MIN_WEEKS = 26
CAP_LO, CAP_HI = 0.25, 2.0


def book_frame(b):
    """common.load_book output -> the int64 / float book used here"""
    out = pd.DataFrame({"k": b.k.to_numpy(), "t_in": pd.DatetimeIndex(b.t_in).as_unit("ns").asi8,
                        "t_out": pd.DatetimeIndex(b.t_out).as_unit("ns").asi8, "R": b.R.to_numpy(float),
                        "side": b.side.to_numpy(np.int64), "wk_out": b.wk_out.to_numpy(np.int64),
                        "year_in": b.year_in.to_numpy(np.int64)})
    return out


def cut_book(b, T_ns):
    """What is known at decision time T: trades entered after T removed; trades not closed strictly before T keep
    their entry but lose their exit time, week and result."""
    c = b[b.t_in.to_numpy() <= T_ns].copy()
    unk = c.t_out.to_numpy() >= T_ns
    c.loc[unk, "t_out"] = INT_MAX
    c.loc[unk, "wk_out"] = UNKNOWN_WEEK
    c.loc[unk, "R"] = np.nan
    return c


def week_of_ns(t_ns):
    return C.week_id(pd.to_datetime(np.asarray(t_ns, np.int64), utc=True))


# ============================================================================================ yearly fits (MV, IV)
def fold_last_week(Y):
    """last server week that ends (next Monday 00:00 server) at or before the cutoff Y-01-01 UTC - 7 days"""
    cut = pd.Timestamp(f"{Y}-01-01", tz="UTC") - C.PURGE
    cut_srv = C.server_naive(pd.DatetimeIndex([cut]))[0]
    d = int(np.floor((cut_srv - pd.Timestamp("1970-01-01")) / pd.Timedelta(days=1)))
    return (d + 3) // 7 - 1


def fold_estimates(b, keys, Y):
    """{k: (mu, sd, n_weeks, n_trades)} of each sleeve's weekly training series for fold Y (enough history only)"""
    last = fold_last_week(Y)
    est = {}
    kk = b.k.to_numpy()
    for k in keys:
        sel = kk == k
        if not sel.any():
            continue
        w0 = int(week_of_ns([b.t_in.to_numpy()[sel].min()])[0])
        nw = last - w0 + 1
        if nw < MIN_WEEKS:
            continue
        wk = b.wk_out.to_numpy()[sel]
        R = b.R.to_numpy()[sel]
        known = wk <= last
        ws = np.zeros(nw)
        np.add.at(ws, wk[known] - w0, R[known])
        sd = float(ws.std(ddof=1))
        if not sd > 0:
            continue
        est[k] = (float(ws.mean()), sd, int(nw), int(known.sum()))
    return est


def fold_weights(est, keys, family, lam):
    w = {k: 1.0 for k in keys}
    if est:
        r = {k: (mu / sd ** 2 if family == "MV" else 1.0 / sd) for k, (mu, sd, _, _) in est.items()}
        m = float(np.mean(list(r.values())))
        q = {k: (r[k] / m if m > 0 else 1.0) for k in r}
        for k in r:
            w[k] = float(np.clip(lam + (1.0 - lam) * q[k], CAP_LO, CAP_HI))
    for k in keys:
        if k in C.F1_KEYS:
            w[k] = min(w[k], 1.0)
    return w


def stakes_yearly(b, keys, family, lam, return_folds=False):
    out = np.ones(len(b))
    yrs = b.year_in.to_numpy()
    kk = b.k.to_numpy()
    folds = {}
    if len(b):
        for Y in range(int(yrs.min()) + 1, 2022):
            sel = yrs == Y
            if not sel.any():
                continue
            est = fold_estimates(b, keys, Y)
            w = fold_weights(est, keys, family, lam)
            folds[Y] = {"weights": w, "estimates": est}
            out[sel] = np.array([w[k] for k in kk[sel]])
    return (out, folds) if return_folds else out


# ============================================================================================ trailing rules (Z, D)
def _trailing(b, u, t_dec, window_days):
    """(sum, count) of sleeve u's paper results with exit time in [t - window, t) for each decision time t
    (window None = every exit before t)"""
    sel = b.k.to_numpy() == u
    to = b.t_out.to_numpy()[sel]
    R = b.R.to_numpy()[sel]
    order = np.argsort(to, kind="stable")
    tos, Rs = to[order], R[order]
    cs = np.r_[0.0, np.cumsum(np.where(tos < INT_MAX, Rs, 0.0))]
    hi = np.searchsorted(tos, t_dec, "left")
    lo = np.zeros(len(t_dec), np.int64) if window_days is None else np.searchsorted(tos, t_dec - np.int64(window_days) * NS_DAY, "left")
    return cs[hi] - cs[lo], hi - lo


def stakes_Z(b, keys, window_days, min_n=20):
    out = np.ones(len(b))
    kk = b.k.to_numpy()
    ti = b.t_in.to_numpy()
    for k in keys:
        idx = np.nonzero(kk == k)[0]
        if not len(idx):
            continue
        s, n = _trailing(b, k, ti[idx], window_days)
        off = (n >= min_n) & (s <= 0.0)
        out[idx[off]] = 0.0
    return out


def stakes_D(b, keys, window_days, min_n=5):
    n = len(b)
    K = len(keys)
    kk = b.k.to_numpy()
    ti = b.t_in.to_numpy()
    S = np.zeros((n, K))
    N = np.zeros((n, K), np.int64)
    for j, u in enumerate(keys):
        S[:, j], N[:, j] = _trailing(b, u, ti, window_days)
    ranked = N >= min_n
    with np.errstate(invalid="ignore", divide="ignore"):
        M = np.where(ranked, S / np.maximum(N, 1), np.nan)
    pos = {k: i for i, k in enumerate(keys)}
    own = np.array([pos[x] for x in kk], np.int64)
    rows = np.arange(n)
    mine = M[rows, own]
    nr = ranked.sum(1)
    with np.errstate(invalid="ignore"):
        below = (ranked & (M < mine[:, None])).sum(1)
        ties = (ranked & (M == mine[:, None])).sum(1) - 1
    g = np.ones(n)
    ok = ranked[rows, own] & (nr >= 2)
    g[ok] = 0.5 + (below[ok] + 0.5 * ties[ok]) / (nr[ok] - 1)
    f1 = np.isin(kk, C.F1_KEYS)
    g[f1] = np.minimum(g[f1], 1.0)
    return g


# ============================================================================================ dispatch
def stakes(b, keys, v, return_folds=False):
    fam = v["family"]
    if fam in ("MV", "IV"):
        return stakes_yearly(b, keys, fam, float(v["lambda"]), return_folds)
    if fam == "Z":
        s = stakes_Z(b, keys, int(v["window_days"]))
    elif fam == "D":
        s = stakes_D(b, keys, None if v["window_days"] is None else int(v["window_days"]))
    elif fam == "REF":
        s = np.ones(len(b))
    else:
        raise ValueError(fam)
    return (s, None) if return_folds else s
