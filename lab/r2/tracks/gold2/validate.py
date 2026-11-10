"""Single-shot validation (2022-2025) of the finalist fixed in finalists_preval.json.  Refuses to run twice."""
import json, os, sys
import pandas as pd
from research import RES, LAB, r2, S, use

if __name__ == "__main__":
    out_path = os.path.join(RES, "validation.json")
    pre = json.load(open(os.path.join(RES, "finalists_preval.json")))
    if os.path.exists(out_path):
        sys.exit("validation.json exists: validation was already run (single shot)")
    out = {"run_utc": pd.Timestamp.now("UTC").isoformat(timespec="seconds"), "results": {}}
    for name, f in pre["finalists"].items():
        assert S.resolve(S.FINALISTS[name]["params"]) == f["params"], "strategy.FINALISTS differs from the pre-validation decision"
        for sym in f["syms"]:
            use(sym)
            # the in-sample numbers must reproduce exactly before the validation period is touched
            ev = r2.evaluate(sym, S.make_orders, f["params"], full=False)
            ref = f["sleeves"][sym]["is"]
            assert all(ev["is"][k] == ref[k] for k in ("n", "pf", "t_stat", "expectancy_R", "total_R")), "IS numbers do not reproduce"
            val = r2.validate(sym, S.make_orders, f["params"], "gold2", name)
            out["results"][f"{name}:{sym}"] = val
            r = val["val"]
            print(name, sym, "VAL n", r.get("n"), "PF", r.get("pf"), "exp", r.get("expectancy_R"), "t", r.get("t_stat"),
                  "years+", r.get("years_pos"), "L", r.get("long_R"), "S", r.get("short_R"), "by year", r.get("by_year_R"))
            print("  stress:", {k: val["val_stress"].get(k) for k in ("n", "pf", "expectancy_R")},
                  "| every-signal:", {k: val["val_every_signal"].get(k) for k in ("n", "pf", "expectancy_R", "t_stat", "long_R", "short_R")})
            print("  criteria:", val["val_criteria"], "| bps/trade", val["val_bps_per_trade"])
    json.dump(out, open(out_path, "w"), indent=1, default=str)
