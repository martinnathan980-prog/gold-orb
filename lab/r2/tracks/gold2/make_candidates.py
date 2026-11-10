"""Assemble results/r2/gold2/candidates.json and trials_table.csv from the logged results."""
import csv, json, os
from research import RES, S, load_detail, key_of
import stageA, stageB, stageD

D = load_detail()
pre = json.load(open(os.path.join(RES, "finalists_preval.json")))
val = json.load(open(os.path.join(RES, "validation.json")))
NAME = "sq24_breakout_1h"
fs = pre["finalists"][NAME]["sleeves"]["xauusd"]
v = val["results"][f"{NAME}:xauusd"]


def brief(d):
    r = d["is"]
    return {"label": d["label"], "sym": d["sym"], "n": r["n"], "trades_per_year": r["trades_per_year"], "pf": r["pf"], "t": r["t_stat"],
            "exp_R": r["expectancy_R"], "years_pos": r["years_pos"], "long_R": r["long_R"], "short_R": r["short_R"],
            "net_bps": d["is_bps"], "stress_pf": d["stress"]["pf"], "gross_pf": d["gross"]["pf"], "gross_exp_R": d["gross"]["expectancy_R"],
            "gross_t": d["gross"]["t_stat"], "gross_bps": d["gross_bps"], "every_signal_exp_R": d["every"]["expectancy_R"],
            "every_signal_pf": d["every"]["pf"], "is_basic_criteria_pass": d["crit"]["pass"],
            "failed": [k for k, x in d["crit"].items() if not x and k != "pass"]}


by_stage = {}
for d in D.values():
    by_stage.setdefault(d["stage"], []).append(brief(d))
out = {
    "track": "gold2", "n_configurations_logged": len(D),
    "verdict": "NOTHING SURVIVES: the single finalist (volatility-contraction breakout on gold, 1h) passed every in-sample criterion and FAILED the single-shot validation 2022-2025.",
    "finalists": {NAME: {
        "syms": ["xauusd"], "params": pre["finalists"][NAME]["params"], "rule": pre["finalists"][NAME]["rule"],
        "is": fs["is"], "is_bps_per_trade": fs["is_bps_per_trade"], "is_stress": fs["is_stress"], "is_gross": fs["is_gross"],
        "is_gross_bps_per_trade": fs["is_gross_bps_per_trade"], "is_every_signal": fs["is_every_signal"],
        "neighbour_median_pf": fs["neighbours"]["neighbour_median_pf"], "neighbours": fs["neighbours"]["neighbours"],
        "controls": fs["neighbours"]["controls"], "null_test_day": fs["null_test_day"], "is_criteria": fs["is_criteria"],
        "long_net": fs["long_net"], "short_net": fs["short_net"],
        "gross_first_half": fs["gross_first_half_2013-2017H1"], "gross_second_half": fs["gross_second_half_2017H2-2021"],
        "stop_2024_2025": fs["stop_2024_2025"], "cost_sensitivity": fs["cost_sensitivity_pf_exp_t"],
        "relation_to_legacy_sleeve": fs["relation_to_legacy_sleeve"],
        "val": v["val"], "val_bps_per_trade": v["val_bps_per_trade"], "val_stress": v["val_stress"],
        "val_every_signal": v["val_every_signal"], "val_criteria": v["val_criteria"], "passes": False,
    }},
    "passed_is_but_not_submitted": pre["not_selected"],
    "trials_by_stage": by_stage,
    "supporting_files": sorted(f for f in os.listdir(RES)),
}
json.dump(out, open(os.path.join(RES, "candidates.json"), "w"), indent=1, default=str)
with open(os.path.join(RES, "trials_table.csv"), "w", newline="") as f:
    w = csv.writer(f)
    cols = ["stage", "label", "sym", "n", "trades_per_year", "pf", "t", "exp_R", "years_pos", "long_R", "short_R", "net_bps", "stress_pf",
            "gross_pf", "gross_exp_R", "gross_t", "gross_bps", "every_signal_exp_R", "every_signal_pf", "is_basic_criteria_pass"]
    w.writerow(cols)
    for st, rows in by_stage.items():
        for r in rows:
            w.writerow([st] + [r[c] for c in cols[1:]])
print("candidates.json written;", len(D), "configurations")
