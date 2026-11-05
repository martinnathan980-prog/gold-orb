"""Write results/meanrev/candidates.json from the logged trials / neighbour / VAL files."""
import json
import os
import numpy as np
from run import TRIALS, LAB
from goldlab.evalkit import is_criteria
from strategy import FINALISTS

R = os.path.join(LAB, "results", "meanrev")
rows = [json.loads(l) for l in open(TRIALS)]
TRIAL_OF = {"meanrev-A-failedbreak-D5": 28}
KEEP = ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "t_stat", "pf",
        "total_R", "max_dd_R", "years_pos", "weeks_pos_pct", "worst_week_R", "long_n", "long_R",
        "short_n", "short_R", "avg_hold_h", "max_hold_h")
out = {"track": "meanrev", "n_trials_logged": len(rows), "verdict": "NOTHING SURVIVES: no meanrev configuration met the pre-registered IS criteria; the best-effort finalist also fails VAL.", "finalists": []}
for name, params in FINALISTS.items():
    tr = rows[TRIAL_OF[name] - 1]
    assert {k: v for k, v in tr["config"].items() if not k.startswith("_")} == params, "trial/param mismatch"
    m = tr["is"]
    crit = is_criteria(m, {"pf": m["stress_pf"]})
    neigh = json.load(open(os.path.join(R, "neighbours_A.json")))
    med = float(np.median([x["pf"] for x in neigh]))
    crit["neighbour_median_pf>=1.10"] = med >= 1.10
    crit["pass"] = all(v for k, v in crit.items() if k != "pass")
    fis = json.load(open(os.path.join(R, "finalist_A_is.json")))
    val = json.load(open(os.path.join(R, f"val_{name}.json")))
    out["finalists"].append({
        "name": name, "params": params, "selected_by": "highest IS PF among frequency-feasible configs (IS n>=200, 25-750 trades/yr); chosen before VAL",
        "trial_id": TRIAL_OF[name],
        "is": {k: m[k] for k in KEEP}, "is_by_year_R": json.loads(m["by_year"]),
        "is_long": {k: fis["is_long"][k] for k in ("n", "win_rate", "expectancy_R", "pf", "t_stat", "total_R")},
        "is_short": {k: fis["is_short"][k] for k in ("n", "win_rate", "expectancy_R", "pf", "t_stat", "total_R")},
        "is_cost_R_per_trade": round(fis["cost_R"]["gross_R"] - fis["cost_R"]["R"], 4), "is_gross_R_per_trade": fis["cost_R"]["gross_R"],
        "stress_pf_costs_x1.5": m["stress_pf"],
        "neighbours": neigh, "neighbour_median_pf": med,
        "is_criteria": crit,
        "val": {k: val["val"][k] for k in KEEP}, "val_by_year_R": val["val"]["by_year_R"],
        "val_long": {k: val["val_long"][k] for k in ("n", "win_rate", "expectancy_R", "pf", "t_stat", "total_R")},
        "val_short": {k: val["val_short"][k] for k in ("n", "win_rate", "expectancy_R", "pf", "t_stat", "total_R")},
        "val_criteria": val["val_criteria"],
        "overlap_allowed_diagnostic": json.load(open(os.path.join(R, "overlap_diag_A.json"))),
    })
json.dump(out, open(os.path.join(R, "candidates.json"), "w"), indent=1)
print(json.dumps(out["finalists"][0]["is_criteria"]), json.dumps(out["finalists"][0]["val_criteria"]))
