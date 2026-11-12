"""Lead synthesis A: the criteria declared for the 2022-2025 look, applied to the in-sample runs already made
(2018-02..2021, where the changes were picked, and the earlier in-sample years, which did not pick them).
No simulation; reads work/portfolio.json and the work/*.parquet trades.  -> work/criteria_rehearsal.json"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/numba_synthesis_A")
import synth as S  # noqa: E402

P = json.load(open(os.path.join(S.WORK, "portfolio.json")))
fac = P["equal_swing_factors_frozen"]
out = {}
for (name, sym), v in S.CHANGE.items():
    key = f"{name}:{sym}"
    lab = f"{key}:{v}"
    cs = P["changed_sleeves"][key]
    r = {}
    for w in ("main", "early"):
        if f"changed_fp_{w}" not in cs:
            r[w] = "no trades in this window"
            continue
        d = {}
        for mode in ("fp", "stress"):
            a, b = cs[f"unchanged_{mode}_{w}"], cs[f"changed_{mode}_{w}"]
            pa = P["portfolios"][f"unchanged|{mode}"][w]["weekly_sharpe"]
            pb = P["portfolios"][f"only_{lab}_equal_swing|{mode}"][w]["weekly_sharpe"]
            ya, yb = a["by_entry_year_total_R"], b["by_entry_year_total_R"]
            years = sorted(set(ya) | set(yb))
            gy = {y: round(yb.get(y, 0.0) * fac[key] - ya.get(y, 0.0), 2) for y in years}
            d[mode] = {"sleeve_weekly_sharpe": [a["weekly_sharpe"], b["weekly_sharpe"]],
                       "portfolio_weekly_sharpe_equal_swing": [pa, pb],
                       "V1_gain_per_unit_of_swing": bool(b["weekly_sharpe"] > a["weekly_sharpe"] and pb > pa),
                       "total_R_constant_stake": [a["total_R"], b["total_R"]],
                       "V2_total_R_not_lower": bool(b["total_R"] >= a["total_R"]),
                       "equal_swing_gain_by_entry_year": gy,
                       "years_positive": f"{sum(1 for x in gy.values() if x > 0)}/{len(gy)}",
                       "V5_changed_sleeve_exp_pos_and_pf_1_06": bool(b["expectancy_R"] > 0 and b["profit_factor"] >= 1.06)}
        d["V3_holds_with_x1_5"] = bool(d["stress"]["V1_gain_per_unit_of_swing"] and d["stress"]["V2_total_R_not_lower"])
        r[w] = d
    out[lab] = r
json.dump(out, open(os.path.join(S.WORK, "criteria_rehearsal.json"), "w"), indent=1)
for lab, r in out.items():
    for w, d in r.items():
        if isinstance(d, str):
            print(lab, w, d)
            continue
        f = d["fp"]
        print(f"{lab:36s} {w:5s} V1 {f['V1_gain_per_unit_of_swing']} sleeve {f['sleeve_weekly_sharpe']} port {f['portfolio_weekly_sharpe_equal_swing']} "
              f"V2 {f['V2_total_R_not_lower']} V3 {d['V3_holds_with_x1_5']} years+ {f['years_positive']} {f['equal_swing_gain_by_entry_year']} V5 {f['V5_changed_sleeve_exp_pos_and_pf_1_06']}")
