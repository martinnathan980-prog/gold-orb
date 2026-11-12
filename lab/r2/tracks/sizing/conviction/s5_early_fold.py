"""Earlier out-of-fold year, REPORTED APART AND JUDGING NOTHING (Addendum I): the 2018 fold where the frames allow.

The same declared rules, fitted on the training set of 2018 (baseline chain trades with exit_time <= 2017-12-25) and
applied to the signals decided in 2018; every other signal at stake 1; measured on the 52 server weeks whose Thursday
falls in 2018. Training exists for the us100 and gold sleeves (from 2014 / 2013) and for the three btcusd sleeves
(from 2017-05: brk72 84 trades, F1 73, nq 95); the ethusd sleeves start in 2018 and keep stake 1.
- V01 (family i): every sleeve with >= 60 training trades.
- V05 / V30 (pooled crypto ridge): pooled over the two btcusd breakouts only (the ethusd ones have no training rows),
  a deviation forced by the data, said so.
- V11 (agreement): no fit.
Writes early_fold_2018.json."""
import os

import numpy as np

import cv_common as V
import cv_engine as E
import cv_stakes as S

Y = 2018
W = V.oof_weeks((Y,))
BTC_BRK = ["brk72_24h_wd__btcusd", "F1_brk_ridge_filter__btcusd"]


def ii_btc(T, nozero):
    desc = [d for d in V.ELIGIBLE if d != "rel2"]
    out = {k: np.ones(len(T[k][0])) for k in T}
    fit = S.fit_ii(T, BTC_BRK, Y, 1.0, 1 / 3, 6, desc)
    for k in BTC_BRK:
        s = T[k][0]
        m = s.year.to_numpy() == Y
        out[k][m] = S.stake_ii(fit, k, s.loc[m, desc].to_numpy(float), nozero)
    return out, {"descriptors": fit["descriptors"], "beta": fit["beta"], "n_train": fit["n_train"],
                 "m_lo": fit["m_lo"], "b_lo": fit["b_lo"], "b_hi": fit["b_hi"]}


def measure(bk, bref):
    wr, wv = V.weekly(bref, W), V.weekly(bk, W)
    k = np.std(wr, ddof=1) / np.std(wv, ddof=1)
    return {"weeks": int(len(W)), "sharpe_ref": round(V.sharpe(wr), 4), "sharpe_var": round(V.sharpe(wv), 4),
            "ratio": round(V.sharpe(wv) / V.sharpe(wr), 4), "total_ref": round(float(wr.sum()), 2),
            "total_var_equal_swing": round(float(wv.sum() * k), 2), "k": round(float(k), 4)}


def main():
    out = {}
    for mode in V.MODES:
        T = S.tables(mode)
        tdec = {k: T[k][0].t_dec.to_numpy(np.int64) for k in V.KEYS}
        base = {k: E.baseline(k, mode) for k in V.KEYS}
        bref = E.book(base, {k: np.ones(len(base[k])) for k in V.KEYS}, tdec)
        st01, inf01 = S.family_i(T, 1 / 3, years=(Y,))
        st05, inf05 = ii_btc(T, False)
        st30, _ = ii_btc(T, True)
        sk = {"V01": {mode: {k: set(np.flatnonzero(st01[k] == 0).tolist()) for k in V.KEYS}},
              "V05": {mode: {k: set(np.flatnonzero(st05[k] == 0).tolist()) for k in V.KEYS}}}
        for vid in sk:                                          # realise() expects both modes: give the other empty
            for m in V.MODES:
                sk[vid].setdefault(m, {k: set() for k in V.KEYS})
        ch = E.realise(sk, verbose=False)
        res = {}
        for vid, st, chains in (("V01", st01, ch["V01"][mode]), ("V05", st05, ch["V05"][mode]), ("V30", st30, base)):
            stc = {k: st[k][chains[k].oid.to_numpy()] for k in V.KEYS}
            res[vid] = measure(E.book(chains, stc, tdec), bref)
            res[vid]["zero_signals_2018"] = int(sum(((st[k] == 0) & (T[k][0].year.to_numpy() == Y)).sum() for k in V.KEYS))
        status = E.agreement_status(base, mode, tdec=tdec)
        stc = {}
        for k in V.KEYS:
            fold = (np.asarray(tdec[k][base[k].oid.to_numpy()]).astype("datetime64[ns]").astype("datetime64[Y]")
                    .astype(int) + 1970)
            s3 = E.iii_stake(status[k], 1.5, 0.5)
            s3[fold != Y] = 1.0
            stc[k] = s3
        res["V11"] = measure(E.book(base, stc, tdec), bref)
        res["fits"] = {"V05_btc_pooled": inf05,
                       "V01": {k: (inf01[k][Y]["decision"] or {}).get("descriptor") for k in V.KEYS}}
        out[mode] = res
        print(mode, {v: res[v] for v in ("V01", "V05", "V30", "V11")}, flush=True)
    V.dump({"what": "2018 fold, reported apart, judges nothing (Addendum I)", "weeks": "server weeks with Thursday in 2018",
            "results": out}, os.path.join(V.OUT, "early_fold_2018.json"))


if __name__ == "__main__":
    main()
