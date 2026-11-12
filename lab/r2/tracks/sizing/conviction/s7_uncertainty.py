"""Uncertainty of the measured Sharpe ratios (diagnostic on the variants already simulated; no new variant):
- the same books measured on 2019-2020 only (104 weeks) and on 2021 alone, FP;
- a paired circular block bootstrap of the 157 out-of-fold weeks (blocks of 4 weeks, 5,000 draws, seed 157): the
  variant's and the reference's weekly sums are resampled together, the ratio of their weekly Sharpe recomputed.
Writes uncertainty.json."""
import os

import numpy as np
import pandas as pd

import cv_common as V
import cv_engine as E
import cv_stakes as S
from s2_run import stakes_on_chains

VARS = {"V05": ("ii", lambda T: S.family_ii_pool(T, 1.0, 1 / 3)), "V09": ("ii", lambda T: S.family_ii_pool(T, 1.0, 0.40)),
        "V30": ("ii", lambda T: S.family_ii_pool(T, 1.0, 1 / 3, nozero=True)), "V01": ("i", lambda T: S.family_i(T, 1 / 3)),
        "V26": ("i", lambda T: S.family_i(T, 1 / 3, t_min=2.0))}


def boot(wr, wv, n=5000, block=4, seed=157):
    rng = np.random.default_rng(seed)
    N = len(wr)
    nb = int(np.ceil(N / block))
    out = np.empty(n)
    for i in range(n):
        st = rng.integers(0, N, nb)
        idx = (st[:, None] + np.arange(block)[None, :]).ravel()[:N] % N
        out[i] = V.sharpe(wv[idx]) / V.sharpe(wr[idx])
    return out


def main():
    mode = "fp"
    T = S.tables(mode)
    tdec = {k: T[k][0].t_dec.to_numpy(np.int64) for k in V.KEYS}
    base = {k: E.baseline(k, mode) for k in V.KEYS}
    bref = E.book(base, {k: np.ones(len(base[k])) for k in V.KEYS}, tdec)
    W = E.OOF_W
    W1920 = W[np.isin(V.week_thursday_year(W), (2019, 2020))]
    W21 = W[V.week_thursday_year(W) == 2021]
    res = {}
    books = {}
    for vid, (fam, fn) in VARS.items():
        st, _ = fn(T)
        if vid == "V30":
            chains = base
        else:
            df = pd.read_parquet(os.path.join(V.OUT, "chains", f"{vid}__{mode}.parquet"))
            chains = {k: df[df.sleeve == k][E.CHAIN_COLS].reset_index(drop=True) for k in V.KEYS}
        stc = stakes_on_chains(chains, [st], None, mode, tdec)
        books[vid] = E.book(chains, stc, tdec)
    # agreement V11 on the baseline chains
    stc = stakes_on_chains(base, [], (1.5, 0.5, False), mode, tdec)
    books["V11"] = E.book(base, stc, tdec)
    for vid, bk in books.items():
        wr, wv = V.weekly(bref, W), V.weekly(bk, W)
        b = boot(wr, wv)
        r1920 = V.sharpe(V.weekly(bk, W1920)) / V.sharpe(V.weekly(bref, W1920))
        r21 = V.sharpe(V.weekly(bk, W21)) / V.sharpe(V.weekly(bref, W21))
        res[vid] = {"ratio_157_weeks": round(V.sharpe(wv) / V.sharpe(wr), 4),
                    "ratio_2019_2020_104_weeks": round(r1920, 4), "ratio_2021_52_weeks": round(r21, 4),
                    "bootstrap_ratio_p05": round(float(np.percentile(b, 5)), 4),
                    "bootstrap_ratio_p50": round(float(np.percentile(b, 50)), 4),
                    "bootstrap_ratio_p95": round(float(np.percentile(b, 95)), 4),
                    "bootstrap_share_ratio_le_1": round(float((b <= 1).mean()), 4),
                    "bootstrap_share_ratio_ge_1.10": round(float((b >= 1.10).mean()), 4)}
        print(vid, res[vid], flush=True)
    V.dump({"what": "uncertainty of the pooled 2019-2021 FP weekly Sharpe ratio (paired circular block bootstrap of "
                    "weeks, blocks of 4, 5,000 draws, seed 157) and sub-windows; diagnostic on variants already simulated",
            "results": res}, os.path.join(V.OUT, "uncertainty.json"))


if __name__ == "__main__":
    main()
