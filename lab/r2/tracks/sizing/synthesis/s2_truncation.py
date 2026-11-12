"""Step 2: truncation tests of the stakes simulated in step 1 (FP costs). IN SAMPLE ONLY.

T1 (fits). For each fold year Y in 2019-2021, the four crypto breakout chains and the K1 signal table are rebuilt on
   frames PHYSICALLY cut (a) at Y-01-01 00:00 UTC (the first instant the fit is used) and (b) at the training cut
   Y-01-01 minus 7 days; trades or labels not finished inside the cut frame are dropped; V05 (exit <= cut), V05
   strict (exit < cut) and K1 are refitted from those tables and compared with the step-1 fits.
T2 (decisions). Random out-of-fold decisions of the four crypto sleeves (seed 11: 12 chain decisions and up to 6
   signals that V05 sets to 0, per sleeve) and 12 brk72 ethusd signals around K1's threshold: every price descriptor
   is recomputed on frames cut at the decision time (own market and us100: bars that start before t) with the
   context lens's functions; the stop distance is recomputed from the cut frame's volatility unit (3 x ATR24 or
   2 x A70); prev / oth24 from the reference chains masked at t; the stake (V05) or the skip (K1) is recomputed from
   the T1(a) fit. Negative control: a price read 2 minutes after t must differ on the cut frame.
Writes out/s2_truncation.json.

    NUMBA_CACHE_DIR=/tmp/synthI_numba PYTHONDONTWRITEBYTECODE=1 python3 s2_truncation.py
"""
import gc
import os
import sys
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import sy_common as C  # noqa: E402
import s1_variants as V  # noqa: E402

C.registry()                                   # loads the rule modules once (sleevefeat reads them from sys.modules)
CTX_CODE = os.path.join(C.LAB, "r2", "tracks", "autopsy", "context")
sys.path.insert(0, CTX_CODE)
import descr as D  # noqa: E402  (context lens, verified; imported, never modified)
import sleevefeat as SF  # noqa: E402

MODE = "fp"
FEAT = {"brk72_24h_wd": (SF.brk_features, 3.0), "F1_brk_ridge_filter": (SF.f1_features, 2.0)}
PRICE = ["trig", "vol", "al1", "al5", "al20", "room", "cushion", "rel", "P"]


def cut_frame(df, t_ns):
    return df.iloc[:int(np.searchsorted(C.ns_of(df.index), int(t_ns), side="left"))]


def same(a, b, rel=1e-9):
    if not np.isfinite(b):
        return not np.isfinite(a)
    return bool(np.isfinite(a) and abs(a - b) <= rel * max(1.0, abs(b)))


def fits_equal(f, g):
    if f is None or g is None:
        return f is g
    return (f["descriptors"] == g["descriptors"] and np.allclose(f["beta"], g["beta"], rtol=0, atol=1e-12)
            and abs(f["b_lo"] - g["b_lo"]) < 1e-12 and abs(f["b_hi"] - g["b_hi"]) < 1e-12
            and all(abs(f["m_lo"][k] - g["m_lo"][k]) < 1e-12 for k in C.CRYPTO_BRK))


def k1_table_on(mk):
    """K1 every-signal table on a (cut) frame, as in s0_repro.k1_signal_table"""
    o = C.build_orders("brk72_24h_wd", mk)
    es = C.every_signal(mk, o, "ethusd", MODE)
    last_start = mk.index[-1]
    ref = pd.Series(C.refused_mask(mk, es), index=es.oid.to_numpy())
    bnd = pd.Series((es.exit_time >= last_start).to_numpy(), index=es.oid.to_numpy())
    lab = pd.Series(es.R.to_numpy(), index=es.oid.to_numpy())
    s = pd.DataFrame({"oid": o.oid.to_numpy(), "t_dec": C.ns_of(o.dec_time), "stop_dist": o.stop_dist.to_numpy(float)})
    s["filled"] = s.oid.isin(es.oid).to_numpy()
    s["refused"] = ref.reindex(s.oid).fillna(False).to_numpy(bool)
    s["boundary"] = bnd.reindex(s.oid).fillna(False).to_numpy(bool)
    s["label"] = np.where(s.boundary, np.nan, lab.reindex(s.oid).to_numpy())
    ns = C.ns_of(mk.index)
    j = np.searchsorted(ns, s.t_dec.to_numpy(np.int64), side="left") - 1
    mid = (mk["bc"].to_numpy(np.float64) + mk["ac"].to_numpy(np.float64)) / 2
    s["P"] = np.where(j >= 0, mid[np.maximum(j, 0)], np.nan)
    s["riskbp"] = 1e4 * s.stop_dist / s.P
    return s


def k1_fold_from(s, y):
    use = (s.filled & ~s.refused & ~s.boundary & np.isfinite(s.label)).to_numpy()
    tr = use & (s.t_dec.to_numpy(np.int64) < C.train_cut_ns(y))
    return V.k1_fit(s.riskbp.to_numpy()[tr], s.label.to_numpy()[tr])


def main():
    t0 = time.time()
    T = V.tables(MODE)
    st01, fit01 = V.v05_stakes(T, strict=False)
    _, fit02 = V.v05_stakes(T, strict=True)
    k1_skip, k1_folds = V.k1_skips(MODE)
    res = {"T1": {}, "T2": {"decisions": 0, "value_mismatch": 0, "stop_mismatch": 0, "stake_mismatch": 0,
                            "k1_mismatch": 0, "max_abs_diff": 0.0, "negative_control_identical": 0, "examples": [],
                            "per_sleeve": {}}}
    frames = {sym: C.load_is(sym) for sym in ("btcusd", "ethusd")}
    chains_full = {k: C.load_trades(f"ref__{k}__{MODE}") for k in C.CRYPTO_BRK}
    cut_chain_check = {}
    res["T1_cut_chain_check"] = cut_chain_check
    # ---------------------------------------------------------------- T1
    for y in C.OOF_YEARS:
        for label, cut_ns in (("a_cut_at_Y0101", C.year_start_ns(y)), ("b_cut_at_training_cut", C.train_cut_ns(y))):
            Tt = {}
            k1s = None
            for k in C.CRYPTO_BRK:
                name, sym = C.split_key(k)
                mk = cut_frame(frames[sym], cut_ns)
                o = C.build_orders(name, mk)
                t = C.chain(mk, o, sym, MODE)
                s_full, _ = T[k]
                tr = s_full.set_index("oid").loc[t.oid.to_numpy()].reset_index()
                # the cut-frame orders are a prefix of the full-frame orders (same oid = same decision): every trade
                # of the cut-frame chain is the full-frame reference trade with the same oid, same entry and same R
                assert (s_full.side.to_numpy()[t.oid.to_numpy()] == t.side.to_numpy()).all()
                fullc = chains_full[k].set_index("oid")
                inn = t.oid.isin(fullc.index).to_numpy()
                same_entry = (C.ns_of(t.entry_time[inn]) == C.ns_of(fullc.loc[t.oid[inn], "entry_time"])).all()
                same_R = np.allclose(t.R.to_numpy()[inn], fullc.loc[t.oid[inn], "R"].to_numpy(), rtol=0, atol=1e-12)
                cut_chain_check.setdefault(f"{y}_{label}", {})[k] = {
                    "trades_cut_chain": int(len(t)), "not_in_full_chain": int((~inn).sum()),
                    "same_entry": bool(same_entry), "same_R": bool(same_R)}
                tr["exit_ns"] = C.ns_of(t.exit_time)
                tr["R"] = t.R.to_numpy(float)
                Tt[k] = (s_full[s_full.t_dec.to_numpy(np.int64) < cut_ns], tr)
                if k == "brk72_24h_wd__ethusd":
                    k1s = k1_table_on(mk)
                del mk
            f1 = V.fit_v05(Tt, y, strict=False)
            f2 = V.fit_v05(Tt, y, strict=True)
            kf = k1_fold_from(k1s, y)
            kref = k1_folds[y]
            r = {"V05_identical": fits_equal(f1, fit01[y]), "V05_n_train_cut": f1["n_train"],
                 "V05_n_train_full": fit01[y]["n_train"],
                 "V05_strict_identical": fits_equal(f2, fit02[y]), "V05_strict_n_train_cut": f2["n_train"],
                 "K1_identical": bool(abs(kf["q_hi"] - kref["q_hi"]) < 1e-9 and abs(kf["q_lo"] - kref["q_lo"]) < 1e-9
                                      and kf["skip"] == kref["skip"] and kf["n_train"] == kref["n_train"]),
                 "K1_q_hi_cut": round(kf["q_hi"], 4), "K1_q_hi_full": round(kref["q_hi"], 4),
                 "K1_n_train_cut": kf["n_train"], "K1_n_train_full": kref["n_train"]}
            if not r["V05_identical"]:
                st_cut = {}
                diff = 0
                for k in C.CRYPTO_BRK:
                    s = T[k][0]
                    m = s.year.to_numpy() == y
                    a, _ = V.stake_v05(f1, k, s.loc[m, V.DESC].to_numpy(float))
                    diff += int((a != st01[k][m]).sum())
                r["V05_stakes_changed_in_year_by_cut_fit"] = diff
                r["V05_max_abs_coef_diff"] = float(np.max(np.abs(np.asarray(f1["beta"]) - np.asarray(fit01[y]["beta"])))) \
                    if f1["descriptors"] == fit01[y]["descriptors"] else "descriptor set differs"
            res["T1"][f"{y}_{label}"] = r
            print("T1", y, label, r, flush=True)
    # ---------------------------------------------------------------- T2
    chains = {k: C.load_trades(f"ref__{k}__{MODE}") for k in C.KEYS}
    us = C.load_is("us100")
    rng = np.random.default_rng(11)
    for k in C.CRYPTO_BRK:
        name, sym = C.split_key(k)
        feat_f, mult = FEAT[name]
        s, tr = T[k]
        fold = s.year.to_numpy()
        pool = [int(o) for o in tr.oid.to_numpy() if fold[o] in C.OOF_YEARS]
        pick = [int(x) for x in rng.choice(pool, size=12, replace=False)]
        zeros = [int(o) for o in np.flatnonzero((st01[k] == 0) & np.isin(fold, C.OOF_YEARS)) if o not in pick]
        if len(zeros) > 6:
            zeros = [int(x) for x in rng.choice(zeros, 6, replace=False)]
        k1rows = []
        if k == "brk72_24h_wd__ethusd":
            near = np.flatnonzero(np.isin(fold, C.OOF_YEARS))
            k1rows = [int(x) for x in rng.choice(near, 12, replace=False)]
        dcols = [c for c in s.columns if c.startswith("dec_")]
        ps = {"chain_decisions": len(pick), "zero_stake_signals": len(zeros), "k1_signals": len(k1rows),
              "value_mismatch": 0, "stake_mismatch": 0}
        full_mk = D.Market(frames[sym], hourly=False)
        for o in pick + zeros + k1rows:
            r = s.loc[o]
            t = int(r.t_dec)
            y = int(r.year)
            mc = cut_frame(frames[sym], t)
            own = D.Market(mc)
            relm = D.Market(cut_frame(us, t), hourly=False)
            dec = pd.DataFrame({"t_dec": [t], "side": [int(r.side)], **{c[4:]: [r[c]] for c in dcols}})
            C.clear_rule_caches()
            fe = feat_f(mc, own, dec)
            risk_cut = mult * float(np.asarray(fe["vol_cur"])[0])
            ge = D.generic(own, np.array([t]), np.array([r.side]), np.array([risk_cut]), relm, None)
            vals = {c: float(np.asarray(fe[c] if c in fe else ge[c])[0]) for c in PRICE}
            vals["risk"] = risk_cut
            vals["riskbp"] = risk_cut / vals["P"] * 1e4
            msk = {q: c[C.ns_of(c.exit_time) <= t] for q, c in chains.items()}
            cc = D.chain_context(np.array([t]), msk[k], [msk[q] for q in C.KEYS if q != k])
            vals["prev"] = float(np.asarray(cc["prev"])[0])
            vals["oth24"] = float(np.asarray(cc["oth24"])[0])
            cols = PRICE + ["risk", "riskbp", "prev", "oth24"]
            bad = [c for c in cols if not same(vals[c], float(r[c]))]
            for c in cols:
                if np.isfinite(vals[c]) and np.isfinite(r[c]):
                    res["T2"]["max_abs_diff"] = max(res["T2"]["max_abs_diff"], abs(vals[c] - float(r[c])))
            res["T2"]["decisions"] += 1
            if bad:
                res["T2"]["value_mismatch"] += 1
                ps["value_mismatch"] += 1
            if not same(vals["risk"], float(r["risk"])):
                res["T2"]["stop_mismatch"] += 1
            if y in C.OOF_YEARS:
                X = np.array([[vals[d] for d in V.DESC]])
                st_cut = float(V.stake_v05(fit01[y], k, X)[0][0])
                if st_cut != st01[k][o]:
                    res["T2"]["stake_mismatch"] += 1
                    ps["stake_mismatch"] += 1
                if k == "brk72_24h_wd__ethusd":
                    f = k1_folds[y]
                    sk_cut = f["skip"] == "hi" and vals["riskbp"] >= f["q_hi"]
                    if sk_cut != (o in k1_skip):
                        res["T2"]["k1_mismatch"] += 1
            if bad and len(res["T2"]["examples"]) < 5:
                res["T2"]["examples"].append({"sleeve": k, "oid": o, "bad": {c: [vals[c], float(r[c])] for c in bad}})
            res["T2"]["negative_control_identical"] += int(
                full_mk.P([t + 120 * 10 ** 9])[0] == own.P([t + 120 * 10 ** 9])[0])
            del mc, own, relm
        res["T2"]["per_sleeve"][k] = ps
        print("T2", k, ps, flush=True)
        gc.collect()
    res["T2"]["pass"] = (res["T2"]["value_mismatch"] == 0 and res["T2"]["stake_mismatch"] == 0
                         and res["T2"]["k1_mismatch"] == 0 and res["T2"]["stop_mismatch"] == 0)
    res["sec"] = round(time.time() - t0, 1)
    C.dump(res, os.path.join(C.OUT, "s2_truncation.json"))
    print({q: res["T2"][q] for q in ("decisions", "value_mismatch", "stop_mismatch", "stake_mismatch", "k1_mismatch",
                                     "max_abs_diff", "negative_control_identical", "pass")}, flush=True)


if __name__ == "__main__":
    main()
