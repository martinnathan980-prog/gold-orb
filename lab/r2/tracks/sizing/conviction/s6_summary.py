"""summary.json of the conviction lens: every table reported, from the result files of s0-s5 (nothing is re-simulated
here)."""
import json
import os

import numpy as np
import pandas as pd

import cv_common as V

OUT = V.OUT
J = lambda f: json.load(open(os.path.join(OUT, f)))
CRYPTO = list(V.CRYPTO_BRK)


def part1_rows(p1):
    rows = []
    for mode, d in p1["results"].items():
        for k, dd in d.items():
            for desc, r in dd.items():
                p = r["pooled_2019_2021"]
                if p is None:
                    continue
                if desc == "agree":
                    rows.append({"mode": mode, "sleeve": k, "descriptor": "agreement",
                                 "n_disagree": p["disagree"]["n"], "mean_disagree": p["disagree"]["mean_R"],
                                 "n_neither": p["neither"]["n"], "mean_neither": p["neither"]["mean_R"],
                                 "n_agree": p["agree"]["n"], "mean_agree": p["agree"]["mean_R"],
                                 "t_agree_vs_rest": p["welch_t_agree_vs_rest"],
                                 "years_agree_above_rest": p["years_agree_above_rest"],
                                 "by_year": {y: r["by_year"][y] for y in ("2019", "2020", "2021")}})
                    continue
                rows.append({"mode": mode, "sleeve": k, "descriptor": desc,
                             "n_lo": p["lo"]["n"], "mean_lo": p["lo"]["mean_R"], "n_mid": p["mid"]["n"],
                             "mean_mid": p["mid"]["mean_R"], "n_hi": p["hi"]["n"], "mean_hi": p["hi"]["mean_R"],
                             "hi_minus_lo": p["oof_hi_minus_lo"], "t_hi_vs_lo": p["welch_t_hi_vs_lo_oof"],
                             "years_sign_as_training": p["years_oof_sign_as_training"],
                             "by_year": {y: {"train_t": r["by_year"][y]["train"]["t_hi_minus_lo"],
                                             **{g: r["by_year"][y]["applied"][g] for g in ("lo", "mid", "hi")}}
                                         for y in ("2019", "2020", "2021")}})
    return rows


def part2_rows(trials, verdicts):
    rows = []
    for r in trials:
        vid = r["trial"]
        if "fp" not in r:
            continue
        row = {"id": vid, "family": r.get("family"), "rule": r.get("rule"), "declared": r.get("declared")}
        for m in V.MODES:
            e = r[m]
            p = e["pooled"]
            row[m] = {"sharpe": p["sharpe"], "sharpe_ref": e["pooled_ref"]["sharpe"],
                      "ratio": p["sharpe_ratio_vs_ref"], "years_up": e.get("years_up"),
                      "by_year_sharpe": {y: [e["by_year"][y]["variant"]["sharpe"], e["by_year"][y]["ref"]["sharpe"]]
                                         for y in e["by_year"]},
                      "k_equal_swing": e["scale_k"], "total_R": p["total_R"], "total_R_ref": e["pooled_ref"]["total_R"],
                      "losing_weeks_pct": p["losing_weeks_pct"], "worst_week": p["worst_week"],
                      "longest_losing_weeks": p["longest_losing_weeks"],
                      "losing_trades_per_month": p["losing_trades_per_month"], "trades": p["trades"],
                      "mean_stake_after_k": p["mean_stake"], "stake_profile_oof": e.get("stake_profile_oof"),
                      "oof_signals_at_zero": e.get("oof_signals_at_zero"),
                      "baseline_trades_removed": sum(v["removed_baseline_trades"] for v in e["chain_changes"].values())
                      if "chain_changes" in e else 0,
                      "new_trades": sum(v["new_trades"] for v in e["chain_changes"].values()) if "chain_changes" in e else 0}
        row["verdict"] = verdicts.get(vid) or r.get("verdict")
        if "components" in r:
            row["components"] = r["components"]
        rows.append(row)
    return rows


def crypto_split(trials):
    out = {}
    for r in trials:
        if "fp" not in r:
            continue
        e = r["fp"]["per_sleeve_oof"]
        cs = sum(e[k]["stakes"] for k in CRYPTO)
        cr = sum(e[k]["R_at_stake"] for k in CRYPTO)
        os_ = sum(e[k]["stakes"] for k in e if k not in CRYPTO)
        orr = sum(e[k]["R_at_stake"] for k in e if k not in CRYPTO)
        out[r["trial"]] = {"crypto4_stakes": round(cs, 1), "crypto4_R": round(cr, 1),
                           "crypto4_R_per_stake": round(cr / cs, 4) if cs else None,
                           "other6_stakes": round(os_, 1), "other6_R": round(orr, 1),
                           "per_sleeve": {k: [e[k]["R_at_stake"], e[k]["R_ref"], e[k]["stakes"], e[k]["n_ref"]] for k in e}}
    return out


def main():
    repro = J("repro.json")
    p1 = J("part1.json")
    p2 = J("part2.json")
    post = J("posthoc.json")
    trunc = J("truncation.json")
    early = J("early_fold_2018.json")
    trials = [json.loads(l) for l in open(os.path.join(OUT, "trials.jsonl"))]
    T = {r["trial"]: r for r in trials}
    ref = T["V00"]
    reference = {m: {"pooled_2019_2021": ref[m]["pooled_ref"],
                     "by_year": {y: ref[m]["by_year"][y]["ref"] for y in ref[m]["by_year"]}} for m in V.MODES}
    # common window check (P0 of synthesis_B): plain sum of the ten chains, entries 2018-02-01 .. 2021-12-31, FP
    n0 = r0 = 0
    for k in V.KEYS:
        c = V.load_chain(k, "fp")
        w = c[c.entry_time >= pd.Timestamp("2018-02-01", tz="UTC")]
        n0 += len(w)
        r0 += float(w.R.sum())
    v05 = T["V05"]
    summ = {
        "lens": "conviction (PROTOCOL_V3 Addendum I): a stake per trade from what is known at the decision",
        "data_rule": "in sample only: price frames read with ts < 2022-01-01, official trades with entry_time < 2022-01-01, "
                     "signals / chains of the context lens (in-sample tables); no 2022+ row read, simulated or looked at",
        "account": "plain sum of the ten sleeves' one-position chains (no caps, no compounding), 1 R x stake; the same throughout",
        "weeks": "FP server weeks (New York + 7 h, Monday-Sunday), booked at the exit; 157 out-of-fold weeks = those whose "
                 "Thursday falls in 2019-2021 (Mondays 2018-12-31 .. 2021-12-27); every week counted",
        "first_check": {"all_reproduced": repro["all_reproduced"], "per_sleeve": repro["verdict"],
                        "P0_common_window_2018_02_2021_12_fp": {"trades": n0, "total_R": round(r0, 2),
                                                                "synthesis_B_P0": "5,205 trades, +788.6 R"}},
        "reference_out_of_fold": reference,
        "part1_note": "terciles fitted on the baseline chain trades whose exit is at or before 1 January minus 7 days, applied "
                      "to the next year's baseline chain trades; pooled = 2019 + 2020 + 2021; years_sign_as_training = years in "
                      "which hi - lo had the sign of that year's training hi - lo; FP and costs x1.5 (part1.json has every "
                      "year, the training statistics, and 2016-2018 reported apart)",
        "part1_table": part1_rows(p1),
        "part2_note": "every variant of declared.json (V01-V28) and of declared_addendum.json (V29-V30, post hoc), FP and "
                      "costs x1.5; ratio = pooled 2019-2021 weekly Sharpe / the reference's (equal swing changes no Sharpe); "
                      "totals, losing weeks, worst week, longest losing run at equal weekly swing (k); losing trades per "
                      "month over 36 months",
        "part2_table": part2_rows(trials, p2["verdicts"]),
        "combo_selection": p2["combo_selection"],
        "crypto_breakouts_vs_other_sleeves_fp_unit_stakes": crypto_split(trials),
        "controls": {"V21_null_of_i": p2["controls"]["V21"], "V22_null_of_iii": p2["controls"]["V22"],
                     "V29_null_of_V30": T["V29"]["null"]},
        "post_hoc_V30": post["V30"],
        "truncation_test_V05_V30": {q: trunc[q] for q in ("tested", "value_mismatch", "fit_mismatch", "stake_mismatch_V05",
                                                           "stake_mismatch_V30", "max_abs_diff", "pass", "per_sleeve")},
        "early_fold_2018_reported_apart": early["results"],
        "uncertainty_fp": J("uncertainty.json")["results"] if os.path.exists(os.path.join(OUT, "uncertainty.json")) else None,
        "V05_detail": {"folds_fp": v05["folds_fp"], "folds_stress": v05["folds_stress"],
                       "per_sleeve_oof_fp": v05["fp"]["per_sleeve_oof"], "chain_changes_fp": v05["fp"]["chain_changes"],
                       "for_the_user_equal_swing": {
                           m: {"reference": {q: v05[m]["pooled_ref"][q] for q in
                                             ("losing_trades_per_month", "losing_weeks_pct", "worst_week",
                                              "longest_losing_weeks", "total_R", "sharpe", "trades")},
                               "V05": {q: v05[m]["pooled"][q] for q in
                                       ("losing_trades_per_month", "losing_weeks_pct", "worst_week",
                                        "longest_losing_weeks", "total_R", "sharpe", "trades")},
                               "k": v05[m]["scale_k"]} for m in V.MODES}},
        "verdict": {
            "candidates": [vid for vid, v in p2["verdicts"].items() if v["candidate_before_truncation"]],
            "closest": "V05 (pooled crypto ridge): FP x1.095 (criterion (a) needs x1.10), up in 3 of 3 years, x1.102 and "
                       "3 of 3 with costs x1.5, every neighbour above the reference (x1.100 to x1.123), causal (210 of 210 "
                       "decisions), (f) about 2.25 parameters per sleeve: NOT a candidate by the declared rule.",
        },
        "trials": {"declared": 28, "post_hoc_declared_before_run": 2, "total": 30, "budget": 30,
                   "reference_logged_not_counted": "V00"},
    }
    V.dump(summ, os.path.join(OUT, "summary.json"))
    print("summary written", len(summ["part1_table"]), "part1 rows", len(summ["part2_table"]), "part2 rows")


if __name__ == "__main__":
    main()
