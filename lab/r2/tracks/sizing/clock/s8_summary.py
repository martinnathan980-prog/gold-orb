"""summary.json of the clock lens: every table reported, from the result files of s1..s7 (nothing simulated here).

    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s8_summary.py
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402

J = lambda name: C.jload(os.path.join(C.OUT, name))  # noqa: E731
USER_KEYS = ("weekly_sharpe", "total_R", "losing_weeks_pct", "worst_week_R", "longest_losing_run_weeks",
             "max_dd_weekly_R", "trades_per_month", "losing_trades_per_month")


def user_view(ev):
    r, v = ev["ref"], ev["var_equal_swing"]
    return {"reference": {k: r[k] for k in USER_KEYS}, "variant_at_equal_weekly_swing": {k: v[k] for k in USER_KEYS},
            "scale_k": ev["scale_k"]}


def variant_row(row, declared_rule):
    fp, st = row["costs"]["fp"], row["costs"]["stress"]
    out = {"rule": declared_rule,
           "fp_pooled_2019_2021": {"ref_sharpe": fp["ref"]["weekly_sharpe"], "var_sharpe": fp["var_equal_swing"]["weekly_sharpe"],
                                   "ratio": fp["sharpe_ratio"], "scale_k": fp["scale_k"],
                                   "max_effective_stake": fp["max_effective_stake"]},
           "fp_by_year": {str(Y): {kk: fp["by_year"][str(Y)][kk] for kk in ("ref_sharpe", "var_sharpe", "ref_total", "var_total_equal_swing")}
                          for Y in C.OOF},
           "fp_years_up": fp["years_up"],
           "stress_pooled_2019_2021": {"ref_sharpe": st["ref"]["weekly_sharpe"], "var_sharpe": st["var_equal_swing"]["weekly_sharpe"],
                                       "ratio": st["sharpe_ratio"], "years_up": st["years_up"]},
           "early_2018_info_only_fp_ratio": fp["early_2018_info_only"]["sharpe_ratio"],
           "for_the_user_fp_2019_2021": user_view(fp),
           "per_sleeve_fp_2019_2021_raw_stakes": {k: v for k, v in fp["per_sleeve_2019_2021"].items()
                                                  if v["ref_n"] != v["var_n"] or v["n_at_0.5"] or v["n_at_1.5"] or v["removed_trades"]}}
    return out


def part1_compact():
    d = pd.read_csv(os.path.join(C.OUT, "part1_cells_by_year.csv"))
    out = {}
    for (k, dim), g in d.groupby(["sleeve", "dim"], sort=False):
        rows = {}
        for (c, lab), h in g.groupby(["cell", "label"]):
            a, b = h[h.year <= 2018], h[h.year >= 2019]
            rows[lab] = {"to_2018_n": int(a.n.sum()), "to_2018_meanR": round(float(a.total.sum() / a.n.sum()), 4) if a.n.sum() else None,
                         "2019_2021_n": int(b.n.sum()), "2019_2021_meanR": round(float(b.total.sum() / b.n.sum()), 4) if b.n.sum() else None,
                         "by_year": {int(r.year): {"n": int(r.n), "meanR": round(float(r["mean"]), 4)} for _, r in h.iterrows()}}
        out.setdefault(k, {})[{"H": "hour_band", "D": "weekday"}[dim]] = rows
    return out


def wf_digest(p1):
    out = {}
    for k, dd in p1["walk_forward"].items():
        for dim, w in dd.items():
            if dim == "FD" or not w:
                continue
            rows = {}
            for Y, r in w.items():
                if not r["acts"]:
                    rows[Y] = {"acts": False, "n_train": r["n_train"]}
                    continue
                rows[Y] = {"n_train": r["n_train"], "sleeve_train_mean": r["mean_train"],
                           "worst": {kk: r["worst"][kk] for kk in ("label", "train_n", "train_mean", "year_n", "year_mean", "rest_year_mean")},
                           "best": {kk: r["best"][kk] for kk in ("label", "train_n", "train_mean", "year_n", "year_mean", "rest_year_mean")},
                           "spearman_train_vs_year": r.get("spearman_train_vs_year")}
            out.setdefault(k, {})[{"H": "hour_band", "D": "weekday"}[dim]] = rows
    fam = {}
    for f, v in p1["family_weekday"].items():
        fam[f] = {"sleeves": v["sleeves"], "folds": {Y: ({"worst": {kk: r["worst"][kk] for kk in ("label", "train_mean", "year_mean", "rest_year_mean")},
                                                           "family_train_mean": r["mean_train"]} if r["acts"] else {"acts": False})
                                                      for Y, r in v["walk_forward"].items()}}
    return out, fam


def main():
    s1 = J("s1_info.json")
    p1 = J("part1.json")
    dec = J("part1_decomposition.json")
    rem = J("stageA_C_remeasured.json")
    null = J("stageC2_oracle_null.json")
    sd = J("stageD.json")
    tr = J("truncation.json")
    declared = J("declared.json")
    dmap = {v["id"]: v["rule"] for v in declared["variants_stage_A"]}
    dmap.update({v["id"]: v["rule"] for v in J("declared_stageC.json")["variants"]})
    dmap.update({v["id"]: v["rule"] for v in J("declared_stageD.json")["variants"]})
    with open(C.TRIALS) as f:
        lines = [json.loads(x) for x in f if x.strip()]
    trial_ids = [x["id"] for x in lines if not x.get("correction_of")]
    corrections = [x["id"] for x in lines if x.get("correction_of")]
    ref = rem["P1_H0"]["costs"]["fp"]["ref"]
    ref_st = rem["P1_H0"]["costs"]["stress"]["ref"]
    first = {k: {kk: v["check"][kk] for kk in ("n_mine_entered", "n_official_entered", "n_mine_open_at_slice_end",
                                               "n_official_closed_in_2022", "totR_mine_closed", "totR_official_closed",
                                               "rows_differing", "reproduced")} for k, v in s1["sleeves"].items()}
    stageA = {}
    for vid in dmap:
        if vid in rem and not vid.startswith("O"):
            r = variant_row(rem[vid], dmap[vid])
            c = rem[vid]["criteria_abc"]
            r["criteria"] = {"a_pooled_ratio_ge_1.10": c["a"], "b_years_up_ge_2": c["b"], "c_stress_ratio_ge_1.10": c["c"],
                             "d_neighbours": "not run: (a)-(c) failed, so by the declared rule no neighbour was evaluated",
                             "e_truncation": "pipeline causal (truncation.json); moot without a candidate",
                             "f_stakes_le_2": c["f_stakes"], "verdict": "fails"}
            stageA[vid] = r
    bounds = {vid: {"rule": dmap[vid], "fp_ratio": rem[vid]["costs"]["fp"]["sharpe_ratio"],
                    "stress_ratio": rem[vid]["costs"]["stress"]["sharpe_ratio"],
                    "fp_by_year": {str(Y): {kk: rem[vid]["costs"]["fp"]["by_year"][str(Y)][kk] for kk in ("ref_sharpe", "var_sharpe")} for Y in C.OOF},
                    "for_the_user_fp_2019_2021": user_view(rem[vid]["costs"]["fp"])} for vid in ("O1_Horacle", "O2_Doracle")}
    post = {vid: variant_row(sd[vid], dmap[vid]) for vid in sd}
    wfd, famd = wf_digest(p1)
    S = {
        "lens": "clock: stakes or skips by hour band and weekday (PROTOCOL_V3 Addendum I), in sample only",
        "data_rule": declared["data_rule"],
        "account": declared["account"],
        "measure": declared["measure"],
        "first_check": {"rule": "ten sleeves rebuilt from in-sample slices, FP costs, one position at a time, compared with the official rows entered before 2022 (counts from entry/exit times only; results on the rows closed before 2022; the one trade each of donch4h_stop and orb_asia_2d_buf10 still open on 2021-12-31 is closed in 2022 in the official file and its result was not read)",
                        "sleeves": first, "all_reproduced": s1["all_reproduced"],
                        "P0_2018_02_2021_fp": s1["P0_fp"], "P0_2018_02_2021_stress": s1["P0_stress"],
                        "synthesis_B_P0": {"fp": {"n": 5205, "total_R": 788.59}, "stress": {"n": 5207, "total_R": 711.09}}},
        "reference_2019_2021": {"fp": {k: ref[k] for k in ref}, "stress": {k: ref_st[k] for k in ref_st},
                                "fp_by_year_sharpe": {str(Y): rem["P1_H0"]["costs"]["fp"]["by_year"][str(Y)]["ref_sharpe"] for Y in C.OOF}},
        "bands": declared["clock"],
        "part1": {"cells_to_2018_vs_2019_2021_fp": part1_compact(),
                  "walk_forward_fp": wfd,
                  "family_weekday_walk_forward_fp": famd,
                  "persistence_2019_2021": p1["persistence_2019_2021"],
                  "persistence_note": "sleeve-folds = sleeve x out-of-fold year where the fit acts; 'folds_in_expected_direction' = training-worst cell below the rest of the sleeve the next year (best: above); diffs in R per trade",
                  "portfolio_cuts_by_year": p1["portfolio_cuts"],
                  "decomposition_after12_friday": {kk: dec[kk] for kk in dec}},
        "part2_stage_A": stageA,
        "stage_B": "not run: no stage-A primary met (a), (b) and (c); by the declared rule neighbours are evaluated only for those",
        "bounds_perfect_foresight": bounds,
        "bounds_null": {kk: null[kk] for kk in ("H", "D", "n_permutations", "seed", "trades", "weeks")},
        "post_hoc_information_only": post,
        "truncation": {"pass_e1": tr["pass_e1"], "pass_e2": tr["pass_e2"],
                       "e1": tr["e1"], "e2": {k: {kk: v[kk] for kk in ("n_skipped_tested", "n_kept_tested", "fail", "pass")} for k, v in tr["e2"].items()}},
        "trials": {"variants_logged": len(trial_ids), "ids": trial_ids, "budget": 15,
                   "correction_lines_not_counted": len(corrections),
                   "correction_note": "per-year Sharpe of stage A and C first split by entry year (late-December trades exiting in the next year's first week dropped from both years); recomputed on the weeks of each year; pooled figures unchanged; no verdict changed"},
        "verdict": "no candidate: no walk-forward clock stake or skip raises the portfolio's weekly Sharpe at equal swing on 2019-2021; the best of the nine declared rules is x1.000 (a rule that never acted) and the others x0.933-x0.995; perfect foresight of each year would give x1.18 (hour bands) / x1.38 (weekdays), but random labels give as much (null medians x1.22 / x1.41); even the autopsy's own clock cells applied on the years they were found in give only x1.011-x1.028 (fp)",
        "to_be_said": declared["to_be_said"],
    }
    C.jdump(S, os.path.join(C.OUT, "summary.json"))
    print("summary written;", len(trial_ids), "trials,", len(corrections), "correction lines")


if __name__ == "__main__":
    main()
