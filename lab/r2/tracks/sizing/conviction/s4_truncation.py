"""Criterion (e), truncation test, on the pooled crypto ridge V05 (the closest variant to a candidate) and its
nozero twin V30, FP costs.

For each of the four crypto breakouts: 30 random out-of-fold baseline chain decisions (seed 7) plus up to 30 signals
that V05 sets to 0. For each decision time t:
  1. every price descriptor is recomputed on frames CUT at t (own market and us100 keep only bars that start before t),
     with the context lens's own functions (sleevefeat + descr.generic); riskbp from the cut-frame risk and price;
  2. prev / oth24 are recomputed from the baseline chains masked at t (only trades with exit_time <= t);
  3. the fold's ridge fit is recomputed from training tables PHYSICALLY truncated at the training cut (rows with
     exit_time > 1 January Y - 7 days deleted, and every signal table cut at t);
  4. the stake is recomputed from 1-3 and compared with the stake of the pipeline (V05 and V30).
A negative control reads the price two minutes after t (the entry bar): it must differ on the cut frame.
Writes truncation.json."""
import gc
import os

import numpy as np
import pandas as pd

import cv_common as V
import cv_stakes as S
CC = V.CC
D = V.D

import signals as SG        # noqa: E402  context lens (clear_caches)
import sleevefeat as SF     # noqa: E402

DESC = [d for d in V.ELIGIBLE if d != "rel2"]
PRICE_COLS = ["risk", "trig", "vol", "al1", "al5", "al20", "room", "cushion", "rel", "P"]


def cut(df, t):
    return df.iloc[:int(np.searchsorted(df.index.values, np.datetime64(int(t), "ns").astype(df.index.values.dtype)))]


def same(a, b):
    if not np.isfinite(b):
        return not np.isfinite(a)
    return bool(np.isfinite(a) and abs(a - b) <= 1e-9 * max(1.0, abs(b)))


def main():
    T = S.tables("fp")
    st05, info05 = S.family_ii_pool(T, 1.0, 1 / 3)
    st30, _ = S.family_ii_pool(T, 1.0, 1 / 3, nozero=True)
    chains = {k: V.load_chain(k, "fp") for k in V.KEYS}
    us = CC.load_fp_is("us100")
    rel_full = us
    res = {"tested": 0, "value_mismatch": 0, "stake_mismatch_V05": 0, "stake_mismatch_V30": 0, "fit_mismatch": 0,
           "max_abs_diff": 0.0, "examples": [], "per_sleeve": {}, "negative_control": {}}
    rng = np.random.default_rng(7)
    fit_cache = {}
    for sym in ("btcusd", "ethusd"):
        m1 = CC.load_fp_is(sym)
        full = D.Market(m1, hourly=False)
        for k in [q for q in V.CRYPTO_BRK if V.SYM[q] == sym]:
            name = CC.registry()[k][1]
            dec_f, feat_f = SF.FUNCS[name]
            s, tr = T[k]
            ch_oid = tr.oid.to_numpy()
            fold = s.year.to_numpy()
            pool = [o for o in ch_oid if fold[o] in V.OOF_YEARS]
            pick = list(rng.choice(pool, size=30, replace=False))
            zeros = [o for o in np.flatnonzero((st05[k] == 0) & np.isin(fold, V.OOF_YEARS)) if o not in pick]
            if len(zeros) > 30:
                zeros = list(rng.choice(zeros, 30, replace=False))
            rows = pick + zeros
            dcols = [c for c in s.columns if c.startswith("dec_")]
            ps = {"n_random_chain": len(pick), "n_zero_stake": len(zeros), "value_mismatch": 0, "stake_mismatch": 0}
            neg_same = 0
            for o in rows:
                r = s.loc[o]
                t = int(r.t_dec)
                y = int(r.year)
                mc = cut(m1, t)
                own = D.Market(mc)
                relm = D.Market(cut(rel_full, t), hourly=False)
                dec = pd.DataFrame({"t_dec": [t], "side": [int(r.side)], **{c[4:]: [r[c]] for c in dcols}})
                SG.clear_caches()
                fe = feat_f(mc, own, dec)
                ge = D.generic(own, np.array([t]), np.array([r.side]), fe["risk"], relm, None)
                chs = {q: c[D.ns_of(c.exit_time) <= t] for q, c in chains.items()}
                cc = D.chain_context(np.array([t]), chs[k], [chs[q] for q in V.KEYS if q != k])
                vals = {}
                for c in PRICE_COLS:
                    src = fe if c in fe else ge
                    vals[c] = float(np.asarray(src[c])[0])
                vals["riskbp"] = vals["risk"] / vals["P"] * 1e4
                for c in ("prev", "oth24"):
                    vals[c] = float(np.asarray(cc[c])[0])
                bad = [c for c in PRICE_COLS + ["riskbp", "prev", "oth24"] if not same(vals[c], float(r[c]))]
                for c in PRICE_COLS + ["riskbp", "prev", "oth24"]:
                    if np.isfinite(vals[c]) and np.isfinite(r[c]):
                        res["max_abs_diff"] = max(res["max_abs_diff"], abs(vals[c] - float(r[c])))
                # fold fit from physically truncated tables
                if y not in fit_cache:
                    Tt = {}
                    for q in V.CRYPTO_BRK:
                        sq, trq = T[q]
                        keep = trq.exit_ns.to_numpy() <= V.train_cut_ns(y)
                        Tt[q] = (sq[sq.t_dec.to_numpy() < V.train_cut_ns(y)].copy(), trq[keep].copy())
                    fit_cache[y] = S.fit_ii(Tt, list(V.CRYPTO_BRK), y, 1.0, 1 / 3, 6, DESC)
                ft = fit_cache[y]
                fp_ = info05[k][y]
                fit_ok = (ft["descriptors"] == fp_["descriptors"] and np.allclose(ft["beta"], fp_["beta"], rtol=0, atol=1e-12)
                          and abs(ft["b_lo"] - fp_["b_lo"]) < 1e-12 and abs(ft["b_hi"] - fp_["b_hi"]) < 1e-12
                          and all(abs(ft["m_lo"][q] - fp_["m_lo"][q]) < 1e-12 for q in V.CRYPTO_BRK))
                X = np.array([[vals[d] for d in DESC]])
                s05 = float(S.stake_ii(ft, k, X)[0])
                s30 = float(S.stake_ii(ft, k, X, nozero=True)[0])
                res["tested"] += 1
                if bad:
                    res["value_mismatch"] += 1
                    ps["value_mismatch"] += 1
                if not fit_ok:
                    res["fit_mismatch"] += 1
                if s05 != st05[k][o]:
                    res["stake_mismatch_V05"] += 1
                    ps["stake_mismatch"] += 1
                if s30 != st30[k][o]:
                    res["stake_mismatch_V30"] += 1
                if (bad or not fit_ok or s05 != st05[k][o]) and len(res["examples"]) < 5:
                    res["examples"].append({"sleeve": k, "t_dec": str(D.to_ts([t])[0]), "bad": {c: [vals[c], float(r[c])] for c in bad},
                                            "fit_ok": fit_ok, "stake_cut": s05, "stake_pipeline": float(st05[k][o])})
                # negative control: a price read 2 minutes after t (inside the entry bar)
                neg_same += int(full.P([t + 120 * 10 ** 9])[0] == D.Market(mc, hourly=False).P([t + 120 * 10 ** 9])[0])
                del mc, own, relm
            ps["negative_control_leaky_price_identical"] = f"{neg_same}/{len(rows)}"
            res["per_sleeve"][k] = ps
            print(k, ps, flush=True)
        del m1
        gc.collect()
    res["pass"] = res["value_mismatch"] == 0 and res["fit_mismatch"] == 0 and res["stake_mismatch_V05"] == 0 \
        and res["stake_mismatch_V30"] == 0
    V.dump(res, os.path.join(V.OUT, "truncation.json"))
    print({q: res[q] for q in ("tested", "value_mismatch", "fit_mismatch", "stake_mismatch_V05", "stake_mismatch_V30",
                               "max_abs_diff", "pass")}, flush=True)


if __name__ == "__main__":
    main()
