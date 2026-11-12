"""PART 2: the filters and the regularised model of declared.json, judged by walk-forward inside the sample.

For every sleeve, cost mode and variant: the skip set is computed fold by fold (thresholds from the years before,
purge 7 days), the skipped orders are removed, and the sleeve's chain is RE-SIMULATED with no_overlap=True on the
in-sample frame (a skipped signal frees the sleeve for a later one). Writes trials.jsonl (one line per variant),
part2.json (every variant, both modes, per year, in-fold beside out-of-fold) and part2_table.csv."""
import gc
import json
import os
import sys
import time

import numpy as np
import pandas as pd

import common as C
import descr as D
import signals as SG

FILTERS = ["hour", "vol", "al1", "al5", "al20", "room", "trig", "sprR", "rel", "prev"]
QS = {"q0.333": 1 / 3, "q0.25": 0.25, "q0.40": 0.40}
MODEL_X = ["vol", "al1", "al5", "al20", "room", "trig", "sprR", "rel"]
ALPHAS = {"a1": 1.0, "a0.5": 0.5, "a2": 2.0}
PURGE = 7 * D.D_NS
IS_END_NS = int(C.IS_END.value)
CRYPTO = ("btcusd", "ethusd")


def year_start_ns(y):
    return int(pd.Timestamp(f"{y}-01-01", tz="UTC").value)


def usable(s):
    return (s.filled & ~s.refused & ~s.boundary & np.isfinite(s.label)).to_numpy()


def oof_years(s):
    first = int(s.t_dec.min())
    out = []
    for y in range(2013, 2022):
        if first > int(pd.Timestamp(f"{y - 1}-01-31", tz="UTC").value):
            continue
        tr = usable(s) & (s.t_dec.to_numpy() < year_start_ns(y) - PURGE)
        if tr.sum() >= 100:
            out.append(y)
    return out


# ------------------------------------------------------------------------------------------- fits
def fit_filter(x, y, q):
    ok = np.isfinite(x)
    x, y = x[ok], y[ok]
    q_lo, q_hi = np.quantile(x, [q, 1 - q])
    lo, hi = x <= q_lo, x >= q_hi
    e_lo = float(y[lo].mean()) if lo.any() else np.nan
    e_hi = float(y[hi].mean()) if hi.any() else np.nan
    side = None
    if np.nanmin([e_lo, e_hi]) < 0:
        side = "lo" if e_lo < e_hi else "hi"
    return {"q_lo": float(q_lo), "q_hi": float(q_hi), "E_lo": e_lo, "E_hi": e_hi, "n_lo": int(lo.sum()),
            "n_hi": int(hi.sum()), "skip": side, "n_train": int(len(x))}


def apply_filter(x, f):
    x = np.asarray(x, float)
    if f["skip"] is None:
        return np.zeros(len(x), bool)
    with np.errstate(invalid="ignore"):
        return (x <= f["q_lo"]) if f["skip"] == "lo" else (x >= f["q_hi"])   # NaN compares False: never skipped


def fit_ridge(X, y, factor):
    mu = np.nanmean(X, axis=0)
    sd = np.nanstd(X, axis=0)
    sd = np.where(np.isfinite(sd) & (sd > 0), sd, 1.0)
    Z = np.nan_to_num(np.clip((X - mu) / sd, -4, 4), nan=0.0)
    yy = np.clip(y, -2, 4)
    zc = Z.mean(axis=0)
    Zc = Z - zc
    alpha = factor * len(yy)
    beta = np.linalg.solve(Zc.T @ Zc + alpha * np.eye(Z.shape[1]), Zc.T @ (yy - yy.mean()))
    b0 = float(yy.mean() - zc @ beta)
    return {"mu": mu.tolist(), "sd": sd.tolist(), "coef": beta.tolist(), "intercept": b0, "alpha": alpha,
            "n_train": int(len(yy))}


def predict_ridge(X, m):
    Z = np.nan_to_num(np.clip((X - np.asarray(m["mu"])) / np.asarray(m["sd"]), -4, 4), nan=0.0)
    return m["intercept"] + Z @ np.asarray(m["coef"])


def skip_sets(s):
    """{variant: (set of skipped oids, info)} for one sleeve and one cost mode"""
    years = oof_years(s)
    use = usable(s)
    td = s.t_dec.to_numpy()
    yr = s.year.to_numpy()
    lab = s.label.to_numpy()
    out = {}
    applicable = [f for f in FILTERS if np.isfinite(s.loc[use, f]).any()
                  and len(np.unique(s.loc[use, f].dropna())) >= 3]
    for f in applicable:
        x = s[f].to_numpy(float)
        for qn, q in QS.items():
            skip = np.zeros(len(s), bool)
            folds = {}
            for y in years:
                tr = use & (td < year_start_ns(y) - PURGE)
                fo = fit_filter(x[tr], lab[tr], q)
                te = yr == y
                m = apply_filter(x[te], fo)
                skip[np.flatnonzero(te)[m]] = True
                fo["n_skipped"] = int(m.sum())
                fo["n_test"] = int(te.sum())
                folds[y] = fo
            out[f"{f}_{qn}"] = (set(s.oid[skip].tolist()), {"kind": "filter", "descriptor": f, "q": q, "folds": folds})
        # in-fold: fitted on every in-sample signal, applied to every year
        tr = use & (td < IS_END_NS - PURGE)
        fo = fit_filter(x[tr], lab[tr], 1 / 3)
        m = apply_filter(x, fo)
        out[f"{f}_q0.333_infold"] = (set(s.oid[m].tolist()), {"kind": "filter_infold", "descriptor": f, "q": 1 / 3, "fit": fo,
                                                             "n_skipped": int(m.sum())})
    X = s[MODEL_X].to_numpy(float)
    for an, a in ALPHAS.items():
        skip = np.zeros(len(s), bool)
        folds = {}
        for y in years:
            tr = use & (td < year_start_ns(y) - PURGE)
            mo = fit_ridge(X[tr], lab[tr], a)
            te = yr == y
            pr = predict_ridge(X[te], mo)
            m = pr < 0
            skip[np.flatnonzero(te)[m]] = True
            mo["n_skipped"] = int(m.sum())
            mo["n_test"] = int(te.sum())
            folds[y] = mo
        out[f"ridge_{an}"] = (set(s.oid[skip].tolist()), {"kind": "model", "alpha_factor": a, "folds": folds})
    tr = use & (td < IS_END_NS - PURGE)
    mo = fit_ridge(X[tr], lab[tr], 1.0)
    m = predict_ridge(X, mo) < 0
    out["ridge_a1_infold"] = (set(s.oid[m].tolist()), {"kind": "model_infold", "alpha_factor": 1.0, "fit": mo,
                                                       "n_skipped": int(m.sum())})
    return out, years, applicable


# ------------------------------------------------------------------------------------------- evaluation
def year_stats(t):
    y = t.entry_time.dt.year.to_numpy()
    R = t.R.to_numpy()
    out = {}
    for yy in np.unique(y):
        out[int(yy)] = C.stats(R[y == yy])
    return out


def window(t, years):
    m = t.entry_time.dt.year.isin(years).to_numpy()
    return C.stats(t.R.to_numpy()[m])


def compare(tb, tv, W, oof):
    b, v = window(tb, W), window(tv, W)
    yb, yv = year_stats(tb), year_stats(tv)
    per = {}
    for y in sorted(set(yb) | set(yv)):
        eb = yb.get(y, {}).get("exp")
        ev = yv.get(y, {}).get("exp")
        per[y] = {"n_b": yb.get(y, {}).get("n", 0), "n_v": yv.get(y, {}).get("n", 0), "exp_b": eb, "exp_v": ev,
                  "tot_b": yb.get(y, {}).get("total", 0.0), "tot_v": yv.get(y, {}).get("total", 0.0)}
    return {"W": W, "base_W": b, "var_W": v, "base_oof": window(tb, oof), "var_oof": window(tv, oof), "by_year": per}


def crit_ab(c):
    b, v = c["base_W"], c["var_W"]
    if not b["n"] or not v["n"]:
        return False, False
    a = (v["exp"] >= b["exp"] + 0.2 * abs(b["exp"])) or \
        (abs(v["avg_loss"]) <= 0.8 * abs(b["avg_loss"]) and v["exp"] >= b["exp"])
    return bool(a), bool(v["total"] >= b["total"])


def crit_c(c):
    W = c["W"]
    up = 0
    for y in W:
        p = c["by_year"].get(y) or c["by_year"].get(str(y))
        if p and p["exp_v"] is not None and p["exp_b"] is not None and p["exp_v"] > p["exp_b"]:
            up += 1
    need = 3
    return bool(up >= need and len(W) >= 3), up


def improves(c):
    b, v = c["base_W"], c["var_W"]
    return bool(v["n"] and b["n"] and v["exp"] > b["exp"] and v["total"] >= b["total"])


def run_symbol(sym, keys, frames_loader):
    res = {}
    m1 = frames_loader(sym)
    for k in keys:
        res[k] = {}
        for mode in SG.MODES:
            t0 = time.time()
            s = pd.read_parquet(os.path.join(SG.SIG_DIR, f"{k}__{mode}.parquet"))
            sets, years, applicable = skip_sets(s)
            W = [y for y in years if 2018 <= y <= 2021]
            mk = C.mode_frame(m1, mode)
            SG.clear_caches()
            o = C.build_orders(k, mk)
            o["oid"] = np.arange(len(o), dtype=np.int64)
            assert len(o) == len(s)
            refused = set(s.oid[s.refused].tolist())
            last_start = mk.index[-1]

            def chain(skip):
                drop = refused | skip
                tt = C.sim(k, mk, o[~o.oid.isin(drop)], mode, no_overlap=True)
                tt = tt[tt.entry_time < C.IS_END]
                return tt[tt.exit_time < last_start].reset_index(drop=True)

            tb = chain(set())
            ref_chain = pd.read_parquet(os.path.join(SG.CH_DIR, f"{k}__{mode}.parquet"))
            assert len(tb) == len(ref_chain) and abs(tb.R.sum() - ref_chain.R.sum()) < 1e-9
            out = {"years_oof": years, "W": W, "applicable_filters": applicable, "baseline_all": C.stats(tb.R),
                   "baseline_by_year": year_stats(tb), "variants": {}}
            for vid, (skip, info) in sets.items():
                tv = chain(skip)
                comp = compare(tb, tv, W, years)
                comp["n_skipped_signals"] = len(skip)
                comp["n_skipped_chain_trades"] = int(len(set(tb.oid) & skip))
                comp["new_trades"] = int(len(set(tv.oid) - set(tb.oid)))
                comp["info"] = info
                out["variants"][vid] = comp
            res[k][mode] = out
            mk = None
            gc.collect()
            print(k, mode, len(sets), "variants", round(time.time() - t0, 1), "s", flush=True)
    del m1
    gc.collect()
    return res


def main():
    res = {}
    us = C.load_fp_is("us100")
    res.update(run_symbol("us100", ["ocm4__us100", "noise30__us100"], lambda s: us))
    C.set_leader_is(us)
    del us
    gc.collect()
    res.update(run_symbol("xauusd", ["donch4h_stop__xauusd", "orb_asia_2d_buf10__xauusd", "GOLD_FRI_PM__xauusd"], C.load_fp_is))
    res.update(run_symbol("btcusd", ["brk72_24h_wd__btcusd", "F1_brk_ridge_filter__btcusd", "nq_btc_follow__btcusd"], C.load_fp_is))
    res.update(run_symbol("ethusd", ["brk72_24h_wd__ethusd", "F1_brk_ridge_filter__ethusd"], C.load_fp_is))
    C.dump(res, os.path.join(C.OUT, "part2_raw.json"))
    judge(res)


def judge(res):
    """criteria (a)-(e) of declared.json, trials.jsonl, part2_table.csv, part2.json"""
    tp = os.path.join(C.OUT, "trials.jsonl")
    if os.path.exists(tp):
        os.remove(tp)                       # rewritten in full from this run (the run is deterministic)
    rows, cands, verdicts = [], {}, {}
    trial_no = 0
    for k in C.KEYS:
        fp, st = res[k]["fp"], res[k]["stress"]
        declared = [v for v in fp["variants"] if v.endswith("_q0.333") or v == "ridge_a1"]
        verdicts[k] = {}
        for vid in sorted(fp["variants"]):
            if vid.endswith("_infold"):
                continue
            c_fp = fp["variants"][vid]
            c_st = st["variants"].get(vid)
            a, b = crit_ab(c_fp)
            c, up = crit_c(c_fp)
            a_s, b_s = crit_ab(c_st) if c_st else (False, False)
            row = {"trial": None, "sleeve": k, "variant": vid, "declared": vid in declared,
                   "kind": c_fp["info"]["kind"]}
            if vid in declared:
                base = vid.rsplit("_", 1)[0]
                if vid == "ridge_a1":
                    nb = ["ridge_a0.5", "ridge_a2"]
                else:
                    nb = [base + "_q0.25", base + "_q0.40"]
                e_ok = all(n in fp["variants"] and improves(fp["variants"][n]) for n in nb)
                inf = fp["variants"].get((vid + "_infold"))
                inf_s = st["variants"].get((vid + "_infold"))
                crit = {"a": a, "b": b, "c": c, "c_years_up": up, "d": bool(a_s and b_s), "e": e_ok}
                crit["candidate_before_f"] = all(crit[x] for x in ("a", "b", "c", "d", "e"))
                verdicts[k][vid] = crit
                if crit["candidate_before_f"]:
                    cands.setdefault(k, []).append(vid)
            else:
                crit = {"a": a, "b": b, "c": c, "c_years_up": up, "d": bool(a_s and b_s)}
                inf = inf_s = None
            for mode, cc in (("fp", c_fp), ("stress", c_st)):
                if cc is None:
                    continue
                rows.append({"sleeve": k, "variant": vid, "mode": mode, "declared": vid in declared,
                             "W": "-".join(map(str, cc["W"])),
                             "n_b": cc["base_W"]["n"], "n_v": cc["var_W"]["n"],
                             "exp_b": cc["base_W"]["exp"], "exp_v": cc["var_W"]["exp"],
                             "tot_b": cc["base_W"]["total"], "tot_v": cc["var_W"]["total"],
                             "avgloss_b": cc["base_W"]["avg_loss"], "avgloss_v": cc["var_W"]["avg_loss"],
                             "win_b": cc["base_W"]["win"], "win_v": cc["var_W"]["win"],
                             "skipped_signals": cc["n_skipped_signals"], "skipped_chain_trades": cc["n_skipped_chain_trades"],
                             "new_trades": cc["new_trades"],
                             "years_exp_up": crit_c(cc)[1],
                             "infold_exp_v": (inf if mode == "fp" else inf_s)["var_W"]["exp"] if (inf if mode == "fp" else inf_s) else None,
                             "infold_tot_v": (inf if mode == "fp" else inf_s)["var_W"]["total"] if (inf if mode == "fp" else inf_s) else None})
            trial_no += 1
            row["trial"] = trial_no
            row["criteria"] = crit
            row["fp"] = {kk: c_fp[kk] for kk in ("W", "base_W", "var_W", "base_oof", "var_oof", "by_year",
                                                   "n_skipped_signals", "n_skipped_chain_trades", "new_trades")}
            row["stress"] = {kk: c_st[kk] for kk in ("W", "base_W", "var_W", "base_oof", "var_oof", "by_year",
                                                       "n_skipped_signals", "n_skipped_chain_trades", "new_trades")} if c_st else None
            row["params"] = {kk: vv for kk, vv in c_fp["info"].items() if kk != "folds"}
            row["folds_fp"] = c_fp["info"].get("folds")
            if inf is not None:
                row["infold_fp"] = {kk: inf[kk] for kk in ("base_W", "var_W", "base_oof", "var_oof", "n_skipped_signals")}
                row["infold_stress"] = {kk: inf_s[kk] for kk in ("base_W", "var_W", "base_oof", "var_oof", "n_skipped_signals")} if inf_s else None
            C.append_trial(row)
    pd.DataFrame(rows).to_csv(os.path.join(C.OUT, "part2_table.csv"), index=False, float_format="%.5g")
    C.dump({"verdicts_declared": verdicts, "candidates_before_causality": cands, "trials": trial_no},
           os.path.join(C.OUT, "part2_verdicts.json"))
    print("trials", trial_no)
    print("candidates before (f):", cands)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "judge":
        judge(json.load(open(os.path.join(C.OUT, "part2_raw.json"))))
    else:
        main()
