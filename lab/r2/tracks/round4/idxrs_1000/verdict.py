"""Verdict of IDXRS_1000 on its main configuration, from the files written by run.py, correlation.py, truncation.py,
repro.py, handcheck.py and account.py (no new simulation). Writes results/r2/round4/idxrs_1000/summary.json."""
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


def load(name):
    return json.load(open(os.path.join(C.OUT, name)))


def main():
    cf, nul, cor = load("configs.json"), load("null.json"), load("correlation.json")
    tru, rep, hc, acc = load("truncation.json"), load("repro.json"), load("handcheck.json"), load("account_1000eur.json")
    trials = [json.loads(l) for l in open(os.path.join(C.OUT, "trials.jsonl"))]
    assert [t["id"] for t in trials] == list(range(1, 13))
    m = cf["main"]["report"]
    neigh = ["n_entry_0955", "n_entry_1015", "n_q67", "n_q80", "n_win40", "n_win80", "n_stop125", "n_stop175", "n_exit_1559"]
    npf = {k: cf[k]["report"]["pf"] for k in neigh}
    med = float(np.median(list(npf.values())))
    yp, yn = (int(v) for v in m["years_pos"].split("/"))
    bt = m["by_pair_type"]
    pos_types = [k for k in ("us100/us500", "us100/us30", "us500/us30") if k in bt and bt[k]["expectancy_R"] > 0]
    crit = [
        ("n >= 250", m["n"], m["n"] >= 250),
        ("PF >= 1.12", m["pf"], m["pf"] >= 1.12),
        ("t >= 2.5", m["t_stat"], m["t_stat"] >= 2.5),
        (">= 60 % of years positive", f"{m['years_pos']} ({yp / yn:.1%})", yp >= 0.6 * yn),
        ("PF >= 1.04 with costs x1.5", cf["stress_x1.5"]["report"]["pf"], cf["stress_x1.5"]["report"]["pf"] >= 1.04),
        ("neighbours' median PF >= 1.06", round(med, 3), med >= 1.06),
        ("every-signal expectancy > 0", m["expectancy_R"], m["expectancy_R"] > 0),
        ("hold <= 5 trading days", f"max {m['max_hold_h']} h", m["max_hold_h"] <= 5 * 24),
        ("random-entry null >= 97.5th percentile", nul["percentile"], nul["percentile"] >= 97.5),
        ("extra: |weekly R corr with ocm4 + noise30| <= 0.30 (2014-2021)", cor["declared_condition"]["corr_with_ocm4_plus_noise30"],
         abs(cor["declared_condition"]["corr_with_ocm4_plus_noise30"]) <= 0.30),
        ("extra: >= 2 of 3 pair types with positive expectancy", f"{len(pos_types)} ({', '.join(pos_types)})", len(pos_types) >= 2),
    ]
    passed = all(c[2] for c in crit)
    g = pd.read_parquet(os.path.join(C.OUT, "gross_main.parquet"))
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    out = {
        "rule": "IDXRS_1000 (PROTOCOL_V3 Addendum J, rule 1), in sample only",
        "declared_json_sha256": hashlib.sha256(open(os.path.join(C.OUT, "declared.json"), "rb").read()).hexdigest(),
        "period": f"entries {t.entry_time.min().date()} .. {t.entry_time.max().date()} (sessions from 2013-09-30, warm-up)",
        "verdict_main": "PASS" if passed else "FAIL",
        "criteria": [{"criterion": c[0], "value": c[1], "pass": bool(c[2])} for c in crit],
        "main": {k: m[k] for k in ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "t_stat", "pf",
                                   "total_R", "max_dd_R", "years_pos", "by_year_R", "by_year_n", "exit_reasons", "avg_hold_h",
                                   "max_hold_h", "net_bp_per_pair", "cost_bp_per_pair", "gross_bp_per_pair", "gross_pf",
                                   "gross_expectancy_R", "money_expectancy_R", "money_pf", "sd_pi_bp_median", "h_median",
                                   "stop_share", "by_pair_type", "by_side_of_us100", "worst_week_R", "weeks_pos_pct")},
        "main_gross_t": round(float(g.R.mean() / (g.R.std(ddof=1) / math.sqrt(len(g)))), 2),
        "neighbours": {k: {kk: cf[k]["report"][kk] for kk in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "net_bp_per_pair")}
                       for k in neigh},
        "neighbours_median_pf": round(med, 3),
        "stress": {kk: cf["stress_x1.5"]["report"][kk] for kk in ("n", "pf", "t_stat", "expectancy_R", "years_pos",
                                                                  "net_bp_per_pair", "cost_bp_per_pair", "by_year_R")},
        "null": {kk: v for kk, v in nul.items() if kk != "means"},
        "correlation": cor,
        "causality_truncation": {kk: tru[kk] for kk in ("decisions_checked", "total", "pass", "problems")},
        "reproduction_check": {kk: rep[kk] for kk in ("reproduced", "difference", "pass")},
        "handcheck": {"days": hc["days_checked"], "pass": hc["pass"]},
        "account_1000eur_reported": acc["run"],
        "trials": len(trials),
    }
    C.jdump(out, os.path.join(C.OUT, "summary.json"))
    for c in out["criteria"]:
        print(("PASS " if c["pass"] else "FAIL ") + c["criterion"], "->", c["value"])
    print("VERDICT:", out["verdict_main"], "| gross t", out["main_gross_t"])


if __name__ == "__main__":
    main()
