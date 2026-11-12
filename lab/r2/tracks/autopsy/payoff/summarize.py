"""Builds results/r2/autopsy/payoff/summary.json (every table reported by the payoff lens).  IN SAMPLE ONLY.

Inputs (all in results/r2/autopsy/payoff/): declared.json, reproduce.json, trials.jsonl, evaluation.json,
causality.json, anatomy_*.csv, reference_*.parquet / .json, trades_*.parquet.
Candidates = variants passing (a)-(e) (evaluation.json) and (f) (causality.json); ranked per sleeve by the DECLARED
rule (expectancy with costs x1.5 on the common window, then FP total R).  A second ranking by the per-trade Sharpe
ratio is added FOR INFORMATION ONLY (it was not declared before the run).
The pooled ten-sleeve view (monthly sums of R, common window, FP costs) is context, not a criterion.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

FAMILY_TEXT = {"S": "stop distance x k at constant money risk", "T": "clock exit replaced by a trailing stop",
               "H": "hold 1-2 more sessions when >= +1 R at the clock exit", "B": "stop to break-even after +b R"}


def pooled(sel):
    """sel: {sleeve key: variant id or 'reference'} -> pooled statistics of the ten sleeves (common window, FP)."""
    parts = []
    for key, vid in sel.items():
        name, sym = key.split(":")
        if vid == "reference":
            t = pd.read_parquet(os.path.join(C.OUT, f"reference_{name}__{sym}.parquet"))
            t = t[t["mode"] == "fp"]
        else:
            t = pd.read_parquet(os.path.join(C.OUT, f"trades_{name}__{sym}.parquet"))
            t = t[(t["mode"] == "fp") & (t["variant"] == vid)]
        parts.append(C.window(t, "common")[["exit_time", "R"]])
    d = pd.concat(parts).sort_values("exit_time")
    R = d["R"].to_numpy()
    mo = d.groupby(d.exit_time.dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period("M"))["R"].sum()
    cum = np.cumsum(R)
    dd = float((np.maximum.accumulate(np.r_[0.0, cum]) - np.r_[0.0, cum]).max())
    return {"n": int(len(R)), "exp_R": round(float(R.mean()), 4), "sd_R": round(float(R.std(ddof=1)), 3),
            "sharpe_trade": round(float(R.mean() / R.std(ddof=1)), 4), "total_R": round(float(R.sum()), 1),
            "months": int(len(mo)), "month_mean_R": round(float(mo.mean()), 2), "month_sd_R": round(float(mo.std(ddof=1)), 2),
            "month_sharpe": round(float(mo.mean() / mo.std(ddof=1)), 3), "months_pos": round(float((mo > 0).mean()), 3),
            "worst_month_R": round(float(mo.min()), 1), "max_dd_R": round(dd, 1)}


def main():
    decl = json.load(open(os.path.join(C.OUT, "declared.json")))
    rep = json.load(open(os.path.join(C.OUT, "reproduce.json")))
    ev = json.load(open(os.path.join(C.OUT, "evaluation.json")))
    cau = json.load(open(os.path.join(C.OUT, "causality.json")))
    trials = [json.loads(x) for x in open(os.path.join(C.OUT, "trials.jsonl"))]
    out = {"lens": "payoff", "protocol": decl["protocol"], "windows": decl["windows"], "costs": decl["costs"],
           "broker_minimum_stop": decl["broker_minimum_stop"], "censoring": decl["censoring"],
           "n_trials": len(trials), "n_declared": decl["n_variants_total"],
           "trials_per_sleeve": {k: sum(1 for t in trials if t["sleeve"] == k) for k in decl["sleeves"]}}
    out["baseline_reproduced"] = {k: {x: v[x] for x in ("official_rows_before_2022", "censored_in_sample",
                                                         "censored_entry_times", "ours", "matched", "max_abs_diff",
                                                         "same_exit_time", "same_reason", "total_R_official_compared",
                                                         "total_R_ours", "common_window", "reproduced")}
                                  for k, v in rep.items()}
    out["anatomy"] = {"sleeves": pd.read_csv(os.path.join(C.OUT, "anatomy_sleeves.csv")).to_dict("records"),
                      "mae_of_winners_R": pd.read_csv(os.path.join(C.OUT, "anatomy_mae_winners.csv")).to_dict("records"),
                      "mfe_of_losers_R": pd.read_csv(os.path.join(C.OUT, "anatomy_mfe_losers.csv")).to_dict("records"),
                      "loss_buckets_R": pd.read_csv(os.path.join(C.OUT, "anatomy_loss_buckets.csv")).to_dict("records")}
    an = pd.read_csv(os.path.join(C.OUT, "anatomy_sleeves.csv"))
    out["anatomy"]["ten_sleeves_pooled"] = {
        "trades": int(an["n"].sum()), "losers": int(an["losers"].sum()), "gross_loss_R": round(float(an["gross_loss_R"].sum()), 1),
        "losers_at_stop": int(an["losers_at_stop"].sum()),
        "gross_loss_from_stopped_trades_R": round(float(-an["losers_at_stop_sum_R"].sum()), 1),
        "share_of_gross_loss_from_stopped_trades": round(float(-an["losers_at_stop_sum_R"].sum() / an["gross_loss_R"].sum()), 3)}
    # variants table per sleeve
    tables, cands = {}, []
    for key, sl in ev["sleeves"].items():
        ref = sl["reference"]
        rows = []
        for vid, v in sl["variants"].items():
            cr = v["criteria"]
            fam = v["spec"]["family"]
            ckey = f"{key}|{fam}"
            caus = cau.get(ckey) if cr.get("candidate_a_to_e") else None
            f_ok = bool(caus and caus["passed"] and vid in caus["variants"])
            rows.append({"variant": vid, "spec": v["spec"], "fp": v["fp"], "stress": v["stress"], "early": v["early"],
                         "by_year_fp": v["by_year"],
                         "risk_fp": {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v["risk"]["fp"].items()},
                         "risk_stress": {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v["risk"]["stress"].items()},
                         "refused_orders_fp": v["refused_orders_fp"], "refused_share_of_orders_fp": v["refused_share_fp"],
                         "refused_orders_stress": v["refused_orders_stress"],
                         "refused_share_of_orders_stress": v["refused_share_stress"],
                         "trades_with_stop_under_3_spreads_if_accepted": v["diag_no_refusal_fp"],
                         "witness_fp": v["witness_fp"], "extended_trades_fp": v["extended_trades_fp"],
                         "censored_fp": v["censored_fp"], "criteria": cr,
                         "causality": None if caus is None else {"decision": f"{caus['decision_tests'] - caus['decision_mismatches']}/{caus['decision_tests']}",
                                                                 "path": f"{caus['path_tests'] - caus['path_mismatches']}/{caus['path_tests']}",
                                                                 "passed": caus["passed"]},
                         "candidate": bool(cr.get("candidate_a_to_e") and f_ok)})
            if rows[-1]["candidate"]:
                cands.append({"sleeve": key, "variant": vid, "stress_exp_R": v["stress"]["exp_R"], "fp_total_R": v["fp"]["total_R"],
                              "sharpe_fp": v["risk"]["fp"]["sharpe_trade"], "sharpe_ratio_vs_ref": v["risk"]["fp"]["sharpe_ratio_vs_ref"]})
        tables[key] = {"reference": {"fp": ref["fp"], "stress": ref["stress"], "early": ref["early"], "by_year_fp": ref["by_year"],
                                     "risk_fp": {k: (round(x, 4) if isinstance(x, float) else x) for k, x in ref["risk"]["fp"].items()},
                                     "risk_stress": {k: (round(x, 4) if isinstance(x, float) else x) for k, x in ref["risk"]["stress"].items()}},
                       "variants": rows}
    out["variants"] = tables
    cd = pd.DataFrame(cands)
    # declared ranking: expectancy with costs x1.5 (common window) first, then FP total R
    cd = cd.sort_values(["sleeve", "stress_exp_R", "fp_total_R"], ascending=[True, False, False]).reset_index(drop=True)
    cd["rank_declared"] = cd.groupby("sleeve").cumcount() + 1
    cd["rank_sharpe_info_only"] = cd.groupby("sleeve")["sharpe_fp"].rank(ascending=False, method="first").astype(int)
    out["candidates_ranked"] = cd.to_dict("records")
    sel_decl = {f"{n}:{s}": "reference" for n, s in C.TEN}
    sel_sh = dict(sel_decl)
    for r in cd.itertuples():
        if r.rank_declared == 1:
            sel_decl[r.sleeve] = r.variant
        if r.rank_sharpe_info_only == 1 and r.sharpe_ratio_vs_ref > 1:
            sel_sh[r.sleeve] = r.variant
    out["pooled_ten_sleeves_context"] = {
        "note": "monthly sums of R of the ten sleeves at one risk unit per trade, common window, FP costs; context only, "
                "not a criterion; 'sharpe-best' was not declared before the run",
        "reference": pooled({k: "reference" for k in sel_decl}),
        "rank1_declared": {"selection": sel_decl, **pooled(sel_decl)},
        "best_sharpe_if_above_reference_info_only": {"selection": sel_sh, **pooled(sel_sh)}}
    out["shape_track_quoted"] = {"what_it_found": "results/r2/shape (48 variants, whole in-sample period, FP costs): targets "
                                 "at 0.5-3 R raise the share of winning trades and cut the expectancy (T0.5 keeps 6-25 % of it "
                                 "on 9 sleeves); half-and-half exits keep 42-90 %; break-even at +1 R (BE1) changes the "
                                 "expectancy by +6 % (noise30), +7 % (ocm4), -3 % (brk72 btcusd), -5 % (F1 btcusd), -36 % "
                                 "(orb) and lowers the win rate; the selection kept half-target variants on 5 sleeves for "
                                 "their win rate at 87-95 % of the expectancy",
                                 "BE1_figures": {k: v for k, v in __import__("evaluate").SHAPE_BE1.items()}}
    json.dump(out, open(os.path.join(C.OUT, "summary.json"), "w"), indent=1, default=str)
    pd.set_option("display.width", 250)
    print(cd.to_string(index=False))
    print(json.dumps(out["pooled_ten_sleeves_context"], indent=1))
    print("trials", out["n_trials"], out["trials_per_sleeve"])


if __name__ == "__main__":
    main()
