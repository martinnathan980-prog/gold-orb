"""Criterion (f), truncation test (declared.json): for each sleeve, 40 random signals of its out-of-fold years
(seed 11) plus the signals skipped by its qualifying variants (up to 60): every descriptor is recomputed on frames
CUT at t_dec (own market and related markets keep only bars whose start is < t_dec; trade lists keep exits <= t_dec)
and compared with the full-frame value; the skip / keep decision of every declared filter and of the model is
recomputed with the fold's thresholds. Writes causality.json."""
import gc
import json
import os
import sys

import numpy as np
import pandas as pd

import common as C
import descr as D
import filters as F
import signals as SG
import sleevefeat as SF

COLS = ["risk", "trig", "vol", "al1", "al5", "al20", "room", "cushion", "sprR", "rel", "rel2", "prev", "oth24", "oth24_n"]


def cut(df, t):
    return df.iloc[:int(np.searchsorted(df.index.values, np.datetime64(int(t), "ns").astype(df.index.values.dtype)))]


def close(a, b):
    if not np.isfinite(b):
        return not np.isfinite(a)
    return bool(np.isfinite(a) and abs(a - b) <= 1e-9 * max(1.0, abs(b)))


def decision_fns(sets_info, s_row, vals):
    """skip decision of each declared variant for one signal, from its fold's fitted thresholds"""
    out = {}
    y = int(s_row["year"])
    for vid, (skipset, info) in sets_info.items():
        if not (vid.endswith("_q0.333") or vid == "ridge_a1"):
            continue
        fo = info["folds"].get(y)
        if fo is None:
            out[vid] = False
            continue
        if info["kind"] == "filter":
            out[vid] = bool(F.apply_filter(np.array([vals[info["descriptor"]]]), fo)[0])
        else:
            X = np.array([[vals[c] for c in F.MODEL_X]])
            out[vid] = bool(F.predict_ridge(X, fo)[0] < 0)
    return out


def test_sleeve(k, m1, rel_df, rel2_df, us_full, chains, cands):
    name = C.registry()[k][1]
    dec_f, feat_f = SF.FUNCS[name]
    s = pd.read_parquet(os.path.join(SG.SIG_DIR, f"{k}__fp.parquet"))
    sets_info, years, _ = F.skip_sets(s)
    resp = None
    if k == "brk72_24h_wd__ethusd":                     # declared_addendum.json: riskbp re-specification
        import respec
        resp, _ = respec.sets_for(s)
        sets_info = {**sets_info, **{v: resp[v] for v in ("riskbp_q0.333",)}}
        cands = {**cands, k: list(cands.get(k, [])) + ["riskbp_q0.333"]}
        s = s.copy()
        s["riskbp"] = s.risk / s.P * 1e4
    rng = np.random.default_rng(11)
    pool = np.flatnonzero(s.year.isin(years).to_numpy() & s.filled.to_numpy())
    pick = list(rng.choice(pool, size=min(40, len(pool)), replace=False))
    extra = []
    for vid in cands.get(k, []):
        sk = sorted(sets_info[vid][0])
        extra += list(s.index[s.oid.isin(sk)])
    extra = [i for i in dict.fromkeys(extra) if i not in pick]
    if len(extra) > 60:
        extra = list(np.random.default_rng(12).choice(extra, 60, replace=False))
    rows = pick + extra
    full_dec = {vid: set(v[0]) for vid, v in sets_info.items()}
    res = {"n_tested": len(rows), "n_random": len(pick), "n_skipped_by_candidates": len(extra), "mismatch_values": 0,
           "mismatch_decisions": 0, "max_abs_diff": 0.0, "examples": []}
    dcols = [c for c in s.columns if c.startswith("dec_")]
    for i in rows:
        r = s.loc[i]
        t = int(r.t_dec)
        mc = cut(m1, t)
        own = D.Market(mc)
        relm = D.Market(cut(rel_df, t), hourly=False) if rel_df is not None else None
        rel2m = D.Market(cut(rel2_df, t), hourly=False) if rel2_df is not None else None
        if name == "nq_btc_follow":
            C.leadlag_module().set_leader("us100", cut(us_full, t))
        dec = pd.DataFrame({"t_dec": [t], "side": [int(r.side)], **{c[4:]: [r[c]] for c in dcols}})
        SG.clear_caches()
        fe = feat_f(mc, own, dec)
        ge = D.generic(own, np.array([t]), np.array([r.side]), fe["risk"], relm, rel2m)
        chs = {q: c[D.ns_of(c.exit_time) <= t] for q, c in chains.items()}
        cc = D.chain_context(np.array([t]), chs[k], [chs[q] for q in C.KEYS if q != k])
        vals = {}
        for c in COLS:
            src = fe if c in fe else (ge if c in ge else cc)
            vals[c] = float(np.asarray(src[c])[0])
        cols = list(COLS)
        if resp is not None:
            # riskbp from the cut frame alone: 3 x ATR24 recomputed on the cut frame, over P at t_dec of the cut frame
            vals["riskbp"] = float(3.0 * np.asarray(fe["vol_cur"])[0] / np.asarray(ge["P"])[0] * 1e4)
            cols.append("riskbp")
        bad = [c for c in cols if not close(vals[c], float(r[c]))]
        for c in cols:
            if np.isfinite(vals[c]) and np.isfinite(r[c]):
                res["max_abs_diff"] = max(res["max_abs_diff"], abs(vals[c] - float(r[c])))
        vals_full = {c: float(r[c]) for c in cols}
        # `hour` is the clock time of the fill (no price data enters it): it is known at the fill by definition
        vals["hour"] = vals_full["hour"] = float(r["hour"])
        d_cut = decision_fns(sets_info, r, vals)
        d_full = {vid: (int(r.oid) in full_dec[vid]) for vid in d_cut}
        d_full_recomputed = decision_fns(sets_info, r, vals_full)
        dbad = [v for v in d_cut if d_cut[v] != d_full[v] or d_full_recomputed[v] != d_full[v]]
        if bad:
            res["mismatch_values"] += 1
        if dbad:
            res["mismatch_decisions"] += 1
        if (bad or dbad) and len(res["examples"]) < 5:
            res["examples"].append({"t_dec": str(D.to_ts([t])[0]), "values_differ": {c: [vals[c], float(r[c])] for c in bad},
                                    "decisions_differ": dbad})
        del mc, own
    if name == "nq_btc_follow":
        C.set_leader_is(us_full)
    res["pass"] = res["mismatch_values"] == 0 and res["mismatch_decisions"] == 0
    print(k, {q: res[q] for q in ("n_tested", "mismatch_values", "mismatch_decisions", "max_abs_diff", "pass")}, flush=True)
    return res


def main():
    v = json.load(open(os.path.join(C.OUT, "part2_verdicts.json")))
    cands = v["candidates_before_causality"]
    chains = {q: pd.read_parquet(os.path.join(SG.CH_DIR, f"{q}__fp.parquet")) for q in C.KEYS}
    out = {}
    cols = ["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]
    us = C.load_fp_is("us100")
    jpy = C.load_raw_is("usdjpy", ["bc", "ac", "bh", "ah", "bl", "al"])
    for k in ("ocm4__us100", "noise30__us100"):
        out[k] = test_sleeve(k, us, jpy, None, None, chains, cands)
    del jpy
    gc.collect()
    C.set_leader_is(us)
    eur = C.load_raw_is("eurusd", ["bc", "ac", "bh", "ah", "bl", "al"])
    xau = C.load_fp_is("xauusd", cols)
    for k in ("donch4h_stop__xauusd", "orb_asia_2d_buf10__xauusd", "GOLD_FRI_PM__xauusd"):
        out[k] = test_sleeve(k, xau, eur, us, None, chains, cands)
    del xau, eur
    gc.collect()
    for sym, keys in (("btcusd", ("brk72_24h_wd__btcusd", "F1_brk_ridge_filter__btcusd", "nq_btc_follow__btcusd")),
                      ("ethusd", ("brk72_24h_wd__ethusd", "F1_brk_ridge_filter__ethusd"))):
        m1 = C.load_fp_is(sym, cols)
        for k in keys:
            out[k] = test_sleeve(k, m1, us, None, us, chains, cands)
        del m1
        gc.collect()
    C.dump(out, os.path.join(C.OUT, "causality.json"))
    print("ALL PASS" if all(r["pass"] for r in out.values()) else "SOME FAIL")


if __name__ == "__main__":
    main()
