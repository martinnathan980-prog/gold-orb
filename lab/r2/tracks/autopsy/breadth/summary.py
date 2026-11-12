"""Assembles results/r2/autopsy/breadth/summary.json from the files written by the other scripts.

    PYTHONDONTWRITEBYTECODE=1 python3 summary.py
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402

import common as C  # noqa: E402


def rj(name):
    p = os.path.join(C.RES, name)
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    inst = pd.read_csv(os.path.join(C.RES, "inventory_instruments.csv"))
    pairs = pd.read_csv(os.path.join(C.RES, "inventory_pairs.csv"))
    res = pd.read_csv(os.path.join(C.RES, "pairs_results.csv"))
    pooled = pd.read_csv(os.path.join(C.RES, "pooled.csv"))
    corr = pd.read_csv(os.path.join(C.RES, "correlations.csv"))
    an, tr, nl, rp, inv, decl = rj("analysis.json"), rj("truncation.json"), rj("null.json"), rj("repro.json"), rj("inventory.json"), rj("declared.json")
    n_trials = sum(1 for ln in open(os.path.join(C.RES, "trials.jsonl")) if ln.strip())
    short = {"sleeve (validated)": "SLEEVE", "tried and failed": "failed", "tried: passed in sample, FAILED validation": "IS ok / VAL failed",
             "never tried -> PART 2": "new (run here)", "never tried, out of this lens": "out of lens"}
    ns = pairs[~pairs.instrument.isin(C.STOCKS)]
    grid = ns.pivot(index="instrument", columns="rule", values="status").replace(short)
    st = pairs[pairs.instrument.isin(C.STOCKS)].groupby(["rule", "status"]).size().unstack(fill_value=0)
    qual = res[res.breadth_pass]
    fam = res.groupby(["rule", "group"]).agg(
        pairs=("id", "size"), trades=("n", "sum"), net_pf_median=("pf", "median"), gross_pf_median=("gross_pf", "median"),
        pairs_gross_positive=("gross_exp_R", lambda x: int((x > 0).sum())), net_bps_median=("bps_per_trade", "median"),
        gross_bps_median=("gross_bps", "median"), passes=("breadth_pass", "sum"),
        refused_3spreads=("refused_3spreads_fp", "sum"), orders=("orders_fp", "sum")).reset_index()
    fam.to_csv(os.path.join(C.RES, "gross_vs_net_by_family.csv"), index=False)
    cands = rj("candidates.json")
    summary = {
        "lens": "breadth -- more independent trades with the same rules (PROTOCOL_V3 Addendum H)",
        "in_sample_only": "price frames read with ts < 2022-01-01; official trades read with entry_time < 2022-01-01; no 2022+ row, no holdout file opened",
        "trials": n_trials,
        "first_check_reproduction": rp,
        "part1_inventory": {
            "instruments": inst.to_dict(orient="records"),
            "status_counts_all_pairs": pairs.groupby("status").size().to_dict(),
            "status_by_rule": inv["by_rule"] if inv else None,
            "grid_non_share_instruments": grid.to_dict(orient="index"),
            "shares_40_by_rule": st.to_dict(orient="index"),
            "tried_pairs_with_numbers": pairs[pairs.status.str.startswith("tried")][["rule", "instrument", "status", "evidence", "source"]].to_dict(orient="records"),
            "out_of_lens_reasons": pairs[pairs.status == "never tried, out of this lens"].groupby("evidence").apply(
                lambda g: sorted(f"{r}:{i}" for r, i in zip(g.rule, g.instrument))).to_dict(),
            "other_records": inv["other_records"] if inv else None,
        },
        "part2_declared": {"pairs": len(decl["pairs"]) if decl else None, "criterion": decl["criterion_breadth"] if decl else None,
                           "window": decl["judging_window"] if decl else None, "costs": decl["costs"] if decl else None,
                           "ranking_rule": decl["ranking_of_qualifiers"] if decl else None},
        "part2_results_all_pairs": res.to_dict(orient="records"),
        "part2_pooled_information_only": pooled.to_dict(orient="records"),
        "part2_gross_vs_net_by_family": fam.to_dict(orient="records"),
        "part2_pairs_gross_pf_ge_1_15": int((res.gross_pf >= 1.15).sum()),
        "part2_pairs_net_pf_ge_1_15": int((res.pf >= 1.15).sum()),
        "part2_candidates": cands,
        "part2_passes": {"count": int(res.breadth_pass.sum()), "pairs": qual[["rule", "instrument"]].to_dict(orient="records"),
                         "expected_if_no_pair_had_a_gross_edge": an["expected_passes_if_no_pair_had_a_gross_edge"] if an else None},
        "part2_ranking": an["ranking"] if an else None,
        "portfolio_ten_sleeves_window": an["portfolio_ten_sleeves"] if an else None,
        "portfolio_ten_plus_all_qualifiers": an["ten_plus_all_qualifiers"] if an else None,
        "correlations_of_qualifiers": corr[corr.id.isin(qual.id)].to_dict(orient="records"),
        "truncation_tests": {k: {kk: vv for kk, vv in v.items() if kk != "cases"} for k, v in (tr or {}).items()},
        "random_entry_null": nl,
    }
    C.jdump(summary, os.path.join(C.RES, "summary.json"))
    print("summary.json written;", n_trials, "trials;", int(res.breadth_pass.sum()), "passes")


if __name__ == "__main__":
    main()
