"""Single-shot validation (2022-2025) of the finalists declared in finalists_preval.json.
One r2.validate call per finalist sleeve; refuses to run a finalist twice.  No re-tuning afterwards."""
import datetime as dt
import json
import os

from research import OUT, r2, S

PRE = os.path.join(OUT, "finalists_preval.json")
RES = os.path.join(OUT, "val_results.json")


def main():
    pre = json.load(open(PRE))
    res = json.load(open(RES)) if os.path.exists(RES) else {}
    for name, f in S.FINALISTS.items():
        assert name in pre["finalists"], f"{name} was not declared before validation"
        assert json.dumps(pre["finalists"][name]["params"], sort_keys=True) == json.dumps(f["params"], sort_keys=True), \
            f"{name}: parameters differ from the pre-validation declaration"
        for sym in f["syms"]:
            key = f"{name}:{sym}"
            if key in res:
                print(key, "already validated -- not run again")
                continue
            out = r2.validate(sym, S.make_orders, f["params"], "idx_eu", name)
            out["run_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            res[key] = out
            json.dump(res, open(RES, "w"), indent=1, default=str)
            v = out["val"]
            print(f"\n== {key} VALIDATION 2022-2025: n={v.get('n')} /yr={v.get('trades_per_year')} win={v.get('win_rate')} expR={v.get('expectancy_R')} "
                  f"PF={v.get('pf')} t={v.get('t_stat')} yrs={v.get('years_pos')} dd={v.get('max_dd_R')} L={v.get('long_R')}({v.get('long_n')}) S={v.get('short_R')}({v.get('short_n')}) "
                  f"bps={out['val_bps_per_trade']}")
            print("   by year R:", v.get("by_year_R"), "| exits:", v.get("exit_reasons"))
            print("   stress: PF", out["val_stress"].get("pf"), "expR", out["val_stress"].get("expectancy_R"),
                  "| every-signal expR", out["val_every_signal"].get("expectancy_R"))
            print("   criteria:", out["val_criteria"])


if __name__ == "__main__":
    main()
