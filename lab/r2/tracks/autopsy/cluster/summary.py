"""Lens `cluster`: compiles results/r2/autopsy/cluster/summary.json (every table reported) and guards_per_sleeve.csv
from the outputs of repro.py, check_engine.py, anatomy.py, guards.py and truncation_frames.py. Computes nothing new
except descriptive splits of trial results already logged (the trades a logged variant removes) and arithmetic."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

J = lambda f: json.load(open(os.path.join(C.OUT, f)))


def main():
    repro, eng, ana, gd, tf = J("repro.json"), J("engine_check.json"), J("anatomy.json"), J("guards.json"), J("truncation_frames.json")
    decl = J("declared.json")
    ref, refs = gd["reference"]["fp"], gd["reference"]["stress"]

    base = {}
    for k, v in repro.items():
        c = v["vs_official"]
        base[k] = {"official_is_trades": c["n_official"], "official_is_total_R": c["total_R_official"],
                   "mine_trades": c["n_mine"], "mine_total_R": c["total_R_mine"], "identical_trades": c["n_identical"],
                   "differing_trades": c["different_trades"], "stress_trades": v["stress"]["n"],
                   "stress_total_R": v["stress"]["total_R"], "stop_closer_than_3_spreads_fp": v["fp"]["stop_lt_3_spreads"],
                   "stop_closer_than_3_spreads_stress": v["stress"]["stop_lt_3_spreads"],
                   "min_stop_in_spreads_fp": v["fp"]["min_stop_spreads"], "first_entry": v["fp"]["first_entry"]}

    # descriptive splits of logged variants: the trades each variant removes (FP, common window, unit-stake R)
    s = pd.read_parquet(os.path.join(C.OUT, "stakes_fp.parquet"))
    c = s[s.t_in >= C.COMMON_START]
    removed = {}
    for v in decl["variants"]:
        k = v["id"]
        rem = c[(c.ref > 0) & (c[k] <= 0)]
        kept = c[(c.ref > 0) & (c[k] > 0)]
        shr = c[(c.ref > 0) & (c[k] > 0) & (c[k] < 1)]
        removed[k] = {"removed_n": int(len(rem)), "removed_mean_R": round(float(rem.R.mean()), 4) if len(rem) else None,
                      "removed_sum_R": round(float(rem.R.sum()), 3), "kept_n": int(len(kept)),
                      "kept_mean_R": round(float(kept.R.mean()), 4), "reduced_n": int(len(shr)),
                      "reduced_mean_R": round(float(shr.R.mean()), 4) if len(shr) else None}
    sec = c[(c.ref > 0) & (c.A1 <= 0)]
    second_by_sleeve = sec.groupby("sleeve").R.agg(["count", "mean", "sum"]).round(4)
    all_by_sleeve = c[c.ref > 0].groupby("sleeve").R.agg(["count", "mean", "sum"]).round(4)
    agreement = {"what": "trades entered while another sleeve of the account holds the same side of the same market (the set variant A1 removes), FP costs, entries 2018-02..2021-12",
                 "n": int(len(sec)), "mean_R": round(float(sec.R.mean()), 4),
                 "others_n": removed["A1"]["kept_n"], "others_mean_R": removed["A1"]["kept_mean_R"],
                 "by_sleeve": {k: {"n": int(r["count"]), "mean_R": float(r["mean"]), "sleeve_mean_R_all_taken": float(all_by_sleeve.loc[k, "mean"])}
                               for k, r in second_by_sleeve.iterrows()}}
    # arithmetic on A1..A4 (the taken set is the same for any second-position stake p > 0: totals are linear in p)
    a_tot = {k: gd["variants"][k]["fp"]["total_R"] for k in ("A2", "A3", "A4")}
    slope = (a_tot["A4"] - a_tot["A2"]) / 0.5            # sum of R of the second positions of A2..A4
    n2 = removed["A2"]["reduced_n"]                        # number of second positions (same set in A2, A3, A4, REF)
    assert gd["variants"]["A2"]["fp"]["n_taken"] == ref["n_taken"]
    base_tot = ref["total_R"] - slope
    base_st = ref["stakes"] - n2
    E_at = {str(p): round((base_tot + p * slope) / (base_st + p * n2), 5) for p in (0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3)}
    assert abs(E_at["1"] - ref["exp_per_stake"]) < 1e-4 and abs(E_at["0.5"] - gd["variants"]["A3"]["fp"]["exp_per_stake"]) < 1e-4
    arith = {"what": "arithmetic on the logged variants A2-A4 (same taken set as the reference; totals linear in the second-position stake p), not a declared or simulated variant: E(p) = (total_ref - S + p S) / (stakes_ref - n2 + p n2)",
             "S_sum_R_second_positions": round(slope, 3), "n2_second_positions": n2,
             "mean_R_second_positions": round(slope / n2, 4), "E_at_p": E_at, "E_ref": ref["exp_per_stake"],
             "E_needed_for_criterion_a": round(1.2 * ref["exp_per_stake"], 5)}

    rows = []
    for k, v in [("REF", None)] + list(gd["variants"].items()):
        f = ref if v is None else v["fp"]
        st = refs if v is None else v["stress"]
        crit = {} if v is None else v["criteria"]
        rows.append({
            "id": k, "family": "" if v is None else v["family"], "rule": "reference account" if v is None else v["rule"],
            "n_taken": f["n_taken"], "stakes": f["stakes"], "total_R": f["total_R"], "E": f["exp_per_stake"],
            "E_vs_ref_pct": round(100 * (f["exp_per_stake"] / ref["exp_per_stake"] - 1), 1),
            "total_vs_ref_pct": round(100 * (f["total_R"] / ref["total_R"] - 1), 1),
            "AL": f["avg_loss_per_stake"], "AL_vs_ref_pct": round(100 * (f["avg_loss_per_stake"] / ref["avg_loss_per_stake"] - 1), 1),
            "win_rate": f["win_rate"], "pf": f["pf"], "worst_day": f["worst_day"], "worst_week": f["worst_week"],
            "max_dd": f["max_dd"], "total_over_dd": round(f["total_R"] / f["max_dd"], 2),
            "longest_losing_days": f["longest_losing_days"], "longest_losing_weeks": f["longest_losing_weeks"],
            "eq_stakes_total": None if v is None else f["equal_stakes"]["total_R"],
            "eq_stakes_worst_day": None if v is None else f["equal_stakes"]["worst_day"],
            "eq_stakes_worst_week": None if v is None else f["equal_stakes"]["worst_week"],
            "eq_stakes_max_dd": None if v is None else f["equal_stakes"]["max_dd"],
            "stress_n": st["n_taken"], "stress_total_R": st["total_R"], "stress_E": st["exp_per_stake"],
            "stress_E_vs_ref_pct": round(100 * (st["exp_per_stake"] / refs["exp_per_stake"] - 1), 1),
            "by_year_E": {y: x["exp_per_stake"] for y, x in f["by_year"].items()},
            "by_year_total": {y: x["total_R"] for y, x in f["by_year"].items()},
            "earlier_years_total": {y: x["total_R"] for y, x in f["earlier_years"].items()},
            "removed": None if v is None else removed[k],
            "criteria": crit,
            "truncation_trade_level": None if v is None else v["truncation_trade_level"]})
    tab = pd.DataFrame(rows)
    psl = []
    for k, v in gd["variants"].items():
        for sl, x in v["fp"]["per_sleeve"].items():
            psl.append({"id": k, "sleeve": sl, **x})
    pd.DataFrame(psl).to_csv(os.path.join(C.OUT, "guards_per_sleeve.csv"), index=False)

    runs = pd.read_csv(os.path.join(C.OUT, "anatomy_runs.csv"))
    pairs = pd.read_csv(os.path.join(C.OUT, "anatomy_pairs_same_market.csv"))
    clock = pd.read_csv(os.path.join(C.OUT, "anatomy_weekday_hour.csv"))
    worst = pd.read_csv(os.path.join(C.OUT, "anatomy_worst_days_weeks.csv"))
    out = {
        "lens": "cluster (PROTOCOL_V3 Addendum H): losses that come together, and an algorithm that adapts",
        "data": "in sample only: price frames read with the row filter ts < 2022-01-01; trades files read with entry_time < 2022-01-01; no 2022+ bar or 2026 file touched",
        "units": "R = multiples of the base stake, one base stake per trade, no compounding; FP costs unless 'stress' (spread and slippage x1.5, trades re-simulated)",
        "window": "entries 2018-02-01 .. 2021-12-31 (common window); earlier years reported separately where frames start earlier (gold 2013, us100 2014, btc 2017-05, eth 2018-01)",
        "account": "reference = the ten sleeves' chains through an account of at most 6 positions and 2 per market, ties in the same minute by ASCII order of name_sym; stop closer than 3 spreads = not taken (no such trade in sample)",
        "trials": {"declared": decl["declared_in_this_batch"], "evaluated": len(gd["variants"]), "budget": decl["budget"],
                   "spare_unused": decl["budget"] - len(gd["variants"])},
        "baseline_reproduced": base,
        "engine_check": eng,
        "reference": {"fp": ref, "stress": refs},
        "anatomy": {
            "runs_within_sleeves": runs.to_dict(orient="records"),
            "pairs_same_market": pairs.to_dict(orient="records"),
            "coloss_same_market": ana["coloss_same_market_sleeve_days"],
            "markets": ana["markets"],
            "clock": {"note": ana["clock_note"], "table": clock.to_dict(orient="records")},
            "worst_days_weeks": {"table": worst.to_dict(orient="records"), "days": ana["worst_days"], "weeks": ana["worst_weeks"]},
            "persistence_trailing_vs_next_month": ana["persistence"],
            "portfolio_time": ana["portfolio_time"],
            "agreement_trades": agreement},
        "guards": {"table": tab.to_dict(orient="records"), "arithmetic_second_position_stake": arith},
        "truncation": {"trade_level_reference": gd["reference_truncation_trade_level"], "price_frames": tf},
        "candidates": [],
        "verdict": "no variant passes criterion (a): the largest expectancy gain is +14.7 % (B1, total -9.5 %); the only variants with total R not lower are D4-D7 (weights) and E3; D5 reaches +13.1 % (+15.6 % with costs x1.5) and its static control D7 +11.0 %",
    }
    json.dump(out, open(os.path.join(C.OUT, "summary.json"), "w"), indent=1, default=str)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(tab[["id", "n_taken", "total_R", "E", "E_vs_ref_pct", "total_vs_ref_pct", "AL_vs_ref_pct", "worst_day", "worst_week",
               "max_dd", "total_over_dd", "eq_stakes_max_dd", "stress_E_vs_ref_pct"]].to_string())
    print(json.dumps(arith, indent=1))
    print(json.dumps(agreement, indent=1))


if __name__ == "__main__":
    main()
