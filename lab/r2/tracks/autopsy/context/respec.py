"""declared_addendum.json: the brk72_24h_wd__ethusd candidate re-expressed without the modelled spread
(riskbp = stop distance / price in basis points), same walk-forward, same criteria. Appends 3 trials."""
import json
import os

import numpy as np
import pandas as pd

import common as C
import filters as F
import signals as SG

K = "brk72_24h_wd__ethusd"
QS = {"q0.333": 1 / 3, "q0.25": 0.25, "q0.40": 0.40}


def sets_for(s):
    s = s.copy()
    s["riskbp"] = s.risk / s.P * 1e4
    years = F.oof_years(s)
    use = F.usable(s)
    td, yr, lab, x = s.t_dec.to_numpy(), s.year.to_numpy(), s.label.to_numpy(), s.riskbp.to_numpy(float)
    out = {}
    for qn, q in QS.items():
        skip = np.zeros(len(s), bool)
        folds = {}
        for y in years:
            tr = use & (td < F.year_start_ns(y) - F.PURGE)
            fo = F.fit_filter(x[tr], lab[tr], q)
            te = yr == y
            m = F.apply_filter(x[te], fo)
            skip[np.flatnonzero(te)[m]] = True
            fo.update(n_skipped=int(m.sum()), n_test=int(te.sum()))
            folds[y] = fo
        out[f"riskbp_{qn}"] = (set(s.oid[skip].tolist()), {"kind": "filter", "descriptor": "riskbp", "q": q, "folds": folds})
    tr = use & (td < F.IS_END_NS - F.PURGE)
    fo = F.fit_filter(x[tr], lab[tr], 1 / 3)
    m = F.apply_filter(x, fo)
    out["riskbp_q0.333_infold"] = (set(s.oid[m].tolist()), {"kind": "filter_infold", "descriptor": "riskbp", "fit": fo,
                                                          "n_skipped": int(m.sum())})
    return out, years


def main():
    m1 = C.load_fp_is("ethusd")
    res = {}
    for mode in SG.MODES:
        s = pd.read_parquet(os.path.join(SG.SIG_DIR, f"{K}__{mode}.parquet"))
        sets, years = sets_for(s)
        W = [y for y in years if 2018 <= y <= 2021]
        mk = C.mode_frame(m1, mode)
        SG.clear_caches()
        o = C.build_orders(K, mk)
        o["oid"] = np.arange(len(o), dtype=np.int64)
        refused = set(s.oid[s.refused].tolist())
        last_start = mk.index[-1]

        def chain(skip):
            tt = C.sim(K, mk, o[~o.oid.isin(refused | skip)], mode, no_overlap=True)
            tt = tt[tt.entry_time < C.IS_END]
            return tt[tt.exit_time < last_start].reset_index(drop=True)

        tb = chain(set())
        res[mode] = {"W": W, "years": years, "variants": {}}
        for vid, (skip, info) in sets.items():
            tv = chain(skip)
            comp = F.compare(tb, tv, W, years)
            comp.update(n_skipped_signals=len(skip), n_skipped_chain_trades=int(len(set(tb.oid) & skip)),
                        new_trades=int(len(set(tv.oid) - set(tb.oid))), info=info)
            res[mode]["variants"][vid] = comp
    n0 = sum(1 for _ in open(os.path.join(C.OUT, "trials.jsonl")))
    verdict = {}
    for i, vid in enumerate(["riskbp_q0.25", "riskbp_q0.333", "riskbp_q0.40"]):
        cf, cs = res["fp"]["variants"][vid], res["stress"]["variants"][vid]
        a, b = F.crit_ab(cf)
        c, up = F.crit_c(cf)
        a_s, b_s = F.crit_ab(cs)
        crit = {"a": a, "b": b, "c": c, "c_years_up": up, "d": bool(a_s and b_s)}
        if vid == "riskbp_q0.333":
            crit["e"] = all(F.improves(res["fp"]["variants"][n]) for n in ("riskbp_q0.25", "riskbp_q0.40"))
            crit["candidate_before_f"] = all(crit[x] for x in "abcde")
            verdict = crit
        inf = res["fp"]["variants"]["riskbp_q0.333_infold"] if vid == "riskbp_q0.333" else None
        inf_s = res["stress"]["variants"]["riskbp_q0.333_infold"] if vid == "riskbp_q0.333" else None
        row = {"trial": n0 + i + 1, "sleeve": K, "variant": vid, "declared": vid == "riskbp_q0.333",
               "kind": "filter (addendum: causal re-specification of sprR)", "criteria": crit,
               "fp": {kk: cf[kk] for kk in ("W", "base_W", "var_W", "base_oof", "var_oof", "by_year",
                                            "n_skipped_signals", "n_skipped_chain_trades", "new_trades")},
               "stress": {kk: cs[kk] for kk in ("W", "base_W", "var_W", "base_oof", "var_oof", "by_year",
                                                "n_skipped_signals", "n_skipped_chain_trades", "new_trades")},
               "params": {"descriptor": "riskbp", "q": cf["info"]["q"]}, "folds_fp": cf["info"]["folds"],
               "folds_stress": cs["info"]["folds"]}
        if inf is not None:
            row["infold_fp"] = {kk: inf[kk] for kk in ("base_W", "var_W", "n_skipped_signals")}
            row["infold_fp"]["fit"] = inf["info"]["fit"]
            row["infold_stress"] = {kk: inf_s[kk] for kk in ("base_W", "var_W", "n_skipped_signals")}
            row["infold_stress"]["fit"] = inf_s["info"]["fit"]
        C.append_trial(row)
        print(vid, crit, "fp W", cf["base_W"], "->", cf["var_W"], "| stress", cs["base_W"]["exp"], "->", cs["var_W"]["exp"],
              cs["base_W"]["total"], "->", cs["var_W"]["total"])
    C.dump({"verdict_riskbp_q0.333": verdict, "results": res}, os.path.join(C.OUT, "respec.json"))


if __name__ == "__main__":
    main()
