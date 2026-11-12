"""synthesis_B step 4: one JSON line per declared variant (R0, C1, N1, N2, I3, P0, P1, P2, P3), losing ones alike, plus
the non-variant lines (truncation tests T1 / T2, descriptive anatomy), in trials.jsonl. Reads only out/*.json.

    NUMBA_CACHE_DIR=/tmp/numba_synthesis_B PYTHONDONTWRITEBYTECODE=1 python3 s4_trials.py
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

PKEYS = ("n", "exp", "eur_per_100_risked", "win", "avg_win", "avg_loss", "pf", "total", "sd", "mean_over_sd",
         "worst_week_R", "max_dd_R_trade_by_trade", "max_dd_R_weekly", "longest_losing_run_weeks", "winning_weeks_pct",
         "week_mean_over_sd", "weekly_sharpe_annualised", "worst_day_R", "by_year", "half_2018_02_2019_12",
         "half_2020_2021")


def main():
    if os.path.exists(C.TRIALS):
        raise SystemExit("trials.jsonl exists already: not appended twice")
    s1 = json.load(open(os.path.join(C.OUT, "s1_info.json")))
    s2 = json.load(open(os.path.join(C.OUT, "s2_portfolio.json")))
    s3 = json.load(open(os.path.join(C.OUT, "s3_truncation.json")))
    rows = []
    rep = {k: {kk: v[kk] for kk in ("n_mine", "n_official", "totR_mine", "totR_official", "matched", "rows_differing",
                                    "official_exits_in_2022", "reproduced", "differing")}
           | {"fp_window": v["reference"]["fp"]["window"], "stress_window": v["reference"]["stress"]["window"],
              "refused_3spreads": [v["reference"]["fp"]["refused_3spreads"], v["reference"]["stress"]["refused_3spreads"]],
              "boundary_dropped": v["reference"]["fp"]["boundary_dropped"]}
           for k, v in s1.items() if not k.startswith("frame") and "reference" in v}
    rows.append({"trial": 1, "id": "R0", "declared": True, "kind": "first check + reference sleeves",
                 "params": "the ten sleeves of r2/recalc.py::sleeves(), frozen; FP and x1.5; 3-spread refusal",
                 "result": rep, "all_reproduced": all(v["reproduced"] for v in rep.values())})
    c1 = s1["C1_brk72_24h_wd_riskbp__ethusd"]
    rows.append({"trial": 2, "id": "C1", "declared": True, "kind": "kept change K1 (context-ETH-brk72-riskbp), re-run",
                 "params": {"descriptor": "riskbp = 1e4 x 3 x ATR24 / P", "q": 1 / 3, "purge_days": 7, "min_train": 100,
                            "refit": "every 1 January", "sleeve": "brk72_24h_wd ethusd"},
                 "fp": c1["fp"], "stress": c1["stress"]})
    for i, (vid, k) in enumerate((("N1", "N1_orb_asia_2d_buf10__ethusd"), ("N2", "N2_orb_asia_2d_buf10__btcusd"),
                                  ("I3", "I3_donch4h_stop__ethusd"))):
        rows.append({"trial": 3 + i, "id": vid, "declared": True,
                     "kind": "kept new sleeve" if vid != "I3" else "information only (dropped B3), not kept",
                     "params": "frozen rule, parameters unchanged (FINALISTS), one position, 3-spread refusal",
                     "rule": k.split("_", 1)[1], "fp": s1[k]["fp"], "stress": s1[k]["stress"]})
    desc = {"P0": "ten sleeves unchanged", "P1": "ten with K1", "P2": "ten with K1 + K2 + K3 (kept set)",
            "P3": "information only: P2 + donch4h_stop ethusd"}
    for i, p in enumerate(("P0", "P1", "P2", "P3")):
        rows.append({"trial": 6 + i, "id": p, "declared": True, "kind": "portfolio, constant stake 1 R, no cap",
                     "params": desc[p], "window": s2["window"],
                     "fp": {k: s2["fp"][p][k] for k in PKEYS}, "stress": {k: s2["stress"][p][k] for k in PKEYS},
                     "by_sleeve_fp": s2["fp"][p]["by_sleeve"]})
    rows.append({"trial": None, "id": "T1+T2", "declared": True, "kind": "truncation tests (not a variant)",
                 "T1": {k: v for k, v in s3["T1_riskbp_ethusd"].items() if k != "rows"},
                 "T2_eth": {k: v for k, v in s3["T2_orb_ethusd"].items() if k != "rows"},
                 "T2_btc": {k: v for k, v in s3["T2_orb_btcusd"].items() if k != "rows"},
                 "note": "T1 used two provisional bars (declared_addendum.json, written before T1 ran)"})
    rows.append({"trial": None, "id": "ANATOMY", "declared": True, "kind": "descriptive, no variant",
                 "window": "2018-02-01 .. 2021-12-31, FP, R0 reference trades", "result": s2["anatomy_fp"]})
    for r in rows:
        C.append_trial(r)
    print(len(rows), "lines;", sum(1 for r in rows if r["trial"]), "variants")


if __name__ == "__main__":
    main()
