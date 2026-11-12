"""Collects the declared run, the causality test, the hand check and the correlation into
results/r2/round4/fomc_cycle/summary.json (in sample only; nothing is simulated here)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def J(name):
    return json.load(open(os.path.join(C.OUT, name)))


def main():
    decl, res, tru, hc, cor = J("declared.json"), J("results.json"), J("truncation.json"), J("handcheck.json"), J("correlation.json")
    L = [json.loads(x) for x in open(os.path.join(C.OUT, "trials.jsonl"))]
    assert [l["id"] for l in L] == list(range(1, 11))
    m = L[0]["is"]
    g = pd.read_parquet(os.path.join(C.OUT, "trades_01_main_gross_accounting.parquet"))
    mk = (g.pnl / g.entry * 1e4) * g.side
    ev, od = mk[g.week % 2 == 0], mk[g.week % 2 == 1]
    d = float(ev.mean() - od.mean())
    se = float(np.sqrt(ev.var() / len(ev) + od.var() / len(od)))
    out = {
        "rule": decl["frozen_name"], "short_name": "fomc_cycle", "addendum": decl["addendum"],
        "declared_utc": decl["_written_utc"], "trials": len(L),
        "passes_in_sample": res["passes_in_sample"], "criteria": res["criteria"],
        "main": {k: m[k] for k in ("n", "pf", "t_stat", "expectancy_R", "total_R", "years_pos", "win_rate", "bp_net_per_trade",
                                   "bp_swap_per_trade", "bp_swap_per_long_trade", "mean_risk_bp", "max_hold_nyse_days", "max_hold_h",
                                   "n_hold_over_192h", "n_partial_weeks", "n_stop_exits", "long", "short", "by_year", "by_week_label",
                                   "decisions_by_status")},
        "main_first_entry": L[0]["first_entry"], "main_last_exit": L[0]["last_exit"],
        "main_gross_accounting": L[0]["is_gross_accounting"],
        "market_move_even_minus_odd_weeks_bp": {"diff": round(d, 2), "se": round(se, 2), "t": round(d / se, 2),
                                                 "n_even": int(len(ev)), "n_odd": int(len(od)),
                                                 "by_week_mean_bp": {w: round(float(v), 2) for w, v in mk.groupby(g.wlabel).mean().items()}},
        "every_signal": L[0]["every_signal"],
        "configs": {l["name"]: ({k: l["is"][k] for k in ("n", "pf", "t_stat", "expectancy_R", "total_R", "years_pos", "bp_net_per_trade")}
                                if "is" in l else l["null"]) for l in L},
        "stress_info_only_swap_x1": L[8]["info_only_stress_with_swap_x1"],
        "null_main": L[9]["null"], "null_diag_long_even": L[7]["null_own_trades"],
        "correlation_2014_2021": {"main": {k: cor["main"][k] for k in ("corr_with_sum_of_ten", "corr_with_clusters")},
                                  "diag_long_even": {k: cor["diag_long_even"][k] for k in ("corr_with_sum_of_ten", "corr_with_clusters")},
                                  "n_weeks": cor["n_weeks"]},
        "causality": {k: tru[k] for k in ("decisions_tested", "a_decisions_identical", "b_outcomes_identical", "pass", "all_trades_checks")},
        "handcheck": {k: hc[k] for k in ("n_checked", "all_match", "max_abs_R_diff")},
    }
    C.jdump(out, os.path.join(C.OUT, "summary.json"))
    print(json.dumps({k: out[k] for k in ("passes_in_sample", "market_move_even_minus_odd_weeks_bp", "causality", "handcheck")}, indent=1))


if __name__ == "__main__":
    main()
