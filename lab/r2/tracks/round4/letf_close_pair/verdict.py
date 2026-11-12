"""Verdict of LETF_CLOSE_PAIR on its main configuration, from the files written by run.py, correlation.py,
truncation.py, handcheck.py, crosscheck_idxrs.py and data_check.py (no new simulation). Writes
results/r2/round4/letf_close_pair/summary.json."""
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

NEIGH = ["n_thr_1.0", "n_thr_1.5", "n_entry_1540", "n_exit_1557", "n_exit_1605", "n_stop_1.25", "n_stop_1.75",
         "n_us100_us500"]


def load(name):
    return json.load(open(os.path.join(C.OUT, name)))


def main():
    cf, nul, cor = load("configs.json"), load("null.json"), load("correlation.json")
    tru, hc, xc, dc = load("truncation.json"), load("handcheck.json"), load("crosscheck_idxrs.json"), load("data_check.json")
    trials = [json.loads(l) for l in open(os.path.join(C.OUT, "trials.jsonl"))]
    assert [t["id"] for t in trials] == list(range(1, 12))
    m = cf["main"]["report"]
    npf = {k: cf[k]["report"]["pf"] for k in NEIGH}
    med = float(np.median(list(npf.values())))
    yp, yn = (int(v) for v in m["years_pos"].split("/"))
    pf5, pf6 = cf["n_exit_1557"]["report"]["pf"], cf["n_exit_1605"]["report"]["pf"]
    st = cf["stress_x1.5"]["report"]
    crit = [
        ("n >= 250", m["n"], m["n"] >= 250),
        ("PF >= 1.12", m["pf"], m["pf"] >= 1.12),
        ("t >= 2.5", m["t_stat"], m["t_stat"] >= 2.5),
        (">= 60 % of years positive", f"{m['years_pos']} ({yp / yn:.1%})", yp >= 0.6 * yn),
        ("PF >= 1.04 with costs x1.5", st["pf"], st["pf"] >= 1.04),
        ("neighbours' median PF >= 1.06 (configurations 2-9)", round(med, 4), med >= 1.06),
        ("every-signal expectancy > 0 (= main, one pair a day)", m["expectancy_R"], m["expectancy_R"] > 0),
        ("hold <= 5 trading days", f"max {m['max_hold_h']} h", m["max_hold_h"] <= 5 * 24),
        ("random-entry null >= 97.5th percentile", nul["percentile"], nul["percentile"] >= 97.5),
        ("extra (knife-edge): PF of exit 15:57 >= 1.06 and PF of exit 16:05 >= 1.06", f"{pf5} / {pf6}",
         pf5 >= 1.06 and pf6 >= 1.06),
    ]
    passed = all(c[2] for c in crit)
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    sig = pd.read_parquet(os.path.join(C.OUT, "signals_main.parquet"))
    tk = sig[sig["take"]]
    # information on the main's own 355 days (no new configuration): the unstopped mid pair return 15:30 -> 15:59
    unstopped = {("d>0" if s > 0 else "d<0"): {"days": int(len(g)), "mean_bp": round(float(g.pi_mid.mean() * 1e4), 3),
                                               "t": round(C.tstat(g.pi_mid.dropna()), 2)}
                 for s, g in tk.groupby("dir")}
    unstopped["all"] = {"days": int(len(tk)), "mean_bp": round(float(tk.pi_mid.mean() * 1e4), 3),
                        "t": round(C.tstat(tk.pi_mid.dropna()), 2)}
    t6 = pd.read_parquet(os.path.join(C.OUT, "trades_06_n_exit_1605.parquet"))
    split6 = {nm: {"n": int(len(g)), "pf": round(C.pf(g.R), 3), "expectancy_R": round(float(g.R.mean()), 4),
                   "years": sorted({int(y) for y in g.entry_time.dt.year})}
              for nm, g in (("exit at a real 16:05 quote", t6[~t6.exit_fallback]),
                            ("fallback: last close before 16:05 (no quote after 16:00)", t6[t6.exit_fallback]))}
    out = {
        "rule": "LETF_CLOSE_PAIR (PROTOCOL_V3 Addendum J, rule 5), in sample only",
        "declared_json_sha256": hashlib.sha256(open(os.path.join(C.OUT, "declared.json"), "rb").read()).hexdigest(),
        "period": f"entries {t.entry_time.min().date()} .. {t.entry_time.max().date()} (sessions 2013-09-30 .. "
                  f"2021-12-31, warm-up), frames ts < 2022-01-01",
        "costs": "FP frames (spreads us100 0.37 / us30 0.35 / us500 0.54 bp at the reference price, Dukascopy shape), "
                 "market slippage 0.2 bp per side per leg, stop slippage 0.5 bp per leg, no swap; stress x1.5",
        "verdict_main": "PASS" if passed else "FAIL",
        "criteria": [{"criterion": c[0], "value": c[1], "pass": bool(c[2])} for c in crit],
        "main": {k: m[k] for k in ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R",
                                   "t_stat", "pf", "total_R", "max_dd_R", "years_pos", "by_year_R", "by_year_n",
                                   "by_year_pf", "by_year_net_bp", "exit_reasons", "avg_hold_h", "max_hold_h",
                                   "net_bp_per_pair", "mid_bp_per_pair_same_exits", "cost_bp_per_pair",
                                   "gross_bp_per_pair", "gross_pf", "gross_expectancy_R", "gross_t",
                                   "money_expectancy_R", "money_pf", "sd_pi_bp_median", "h_median", "stop_share",
                                   "by_direction", "worst_week_R", "weeks_pos_pct", "first_entry", "last_entry")},
        "main_counts": cf["main"]["counts"],
        "information_unstopped_mid_pair_return_on_the_main_days": unstopped,
        "neighbours": {k: {kk: cf[k]["report"].get(kk) for kk in ("n", "pf", "t_stat", "expectancy_R", "years_pos",
                                                                  "net_bp_per_pair", "gross_bp_per_pair", "stop_share")}
                       for k in NEIGH},
        "neighbours_median_pf": round(med, 4),
        "neighbour_6_exit_quality": {"exit_fallback_by_year": cf["n_exit_1605"]["counts"]["exit_fallback_by_year"],
                                     "split": split6,
                                     "why": "the frames carry no us100 / us30 quote after the 16:00 bar on 2016-2017 "
                                            "and on part of 2015 and 2018 (data_after1600.json); declared R10 "
                                            "fallback = last close"},
        "stress": {kk: st.get(kk) for kk in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "net_bp_per_pair",
                                             "cost_bp_per_pair", "by_year_R")},
        "null": nul if "means" not in nul else {kk: v for kk, v in nul.items() if kk != "means"},
        "correlation": cor,
        "causality_truncation": {kk: tru[kk] for kk in ("decisions_checked", "total", "pass", "problems")},
        "handcheck": {"days": hc["days_checked"], "pass": hc["pass"], "problems": hc["problems"]},
        "crosscheck_idxrs_engine": {kk: xc[kk] for kk in ("n_pairs", "same_exit_reason", "same_stop_decision_bar",
                                                          "R_max_abs_diff", "pass", "idxrs_common_sha256")},
        "data": {"sessions": dc["sessions_total"], "sessions_after_an_early_close": dc["sessions_after_an_early_close_total"],
                 "R19_drop_rule_of_6": dc["R19_drop_rule_of_6"]},
        "trials": len(trials),
    }
    C.jdump(out, os.path.join(C.OUT, "summary.json"))
    for c in out["criteria"]:
        print(("PASS " if c["pass"] else "FAIL ") + c["criterion"], "->", c["value"])
    print("VERDICT:", out["verdict_main"])
    print("unstopped mid pair return on the main's days:", unstopped)
    print("neighbour 6 split:", split6)
    print("neighbours:", {k: (v["n"], v["pf"], v["t_stat"]) for k, v in out["neighbours"].items()}, "median", round(med, 4))


if __name__ == "__main__":
    main()
