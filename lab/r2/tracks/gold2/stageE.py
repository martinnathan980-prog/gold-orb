"""Stage E -- diagnostics of the single finalist candidate SQ (declared before running):
  * reproduction: the final strategy.py gives exactly the logged in-sample numbers (not a new configuration)
  * timing probes (logged as trials, stage 'E-diagnostic'): the bracket becomes active 1 / 5 / 30 minutes
    late -- results should degrade smoothly
  * median stop distance of the orders in 2024-2025 (orders only, no P&L) and its money value on the
    minimum lot."""
import json, os, sys
import numpy as np, pandas as pd
from research import RES, run, n_configs, r2, S, use, load_detail, key_of
import stageB

SQ = stageB.B["B5_sq1h_n24_07"]
FX = 0.87      # USD -> EUR, lab convention (goldlab/portfolio.py)

if __name__ == "__main__":
    out = {}
    use("xauusd")
    ev = r2.evaluate("xauusd", S.make_orders, S.resolve(SQ), full=True)
    ref = load_detail()[key_of("xauusd", SQ)]
    same = all(ev["is"][k] == ref["is"][k] for k in ("n", "pf", "t_stat", "expectancy_R", "total_R", "max_dd_R"))
    out["reproduction_identical"] = bool(same)
    print("reproduction identical:", same, ev["is"]["n"], ev["is"]["pf"], ev["is"]["t_stat"])
    probes = {}
    for d in (1, 5, 30):
        r = run(f"E_SQ_delay{d}m", "E-diagnostic", "xauusd", {**SQ, "delay_min": d}, full=True, quiet=True)
        probes[f"delay_{d}min"] = {"n": r["is"]["n"], "pf": r["is"]["pf"], "t": r["is"]["t_stat"], "exp_R": r["is"]["expectancy_R"],
                                   "gross_exp_R": r["gross"]["expectancy_R"], "every_exp_R": r["every"]["expectancy_R"]}
        print(d, probes[f"delay_{d}min"], flush=True)
    out["timing_probes"] = probes
    # stop distance of the orders placed in 2024-2025 (orders only)
    m1 = r2.load("xauusd")
    o = S.make_orders(m1, **S.resolve(SQ))
    t_dec = m1.index[o.entry_i.to_numpy()]
    spec = r2.SPEC["xauusd"]
    oz = spec["min_lot"] * spec["units_per_lot"]
    for lab, a, b in (("2024-2025", "2024-01-01", "2026-01-01"), ("2025", "2025-01-01", "2026-01-01"), ("2013-2021", "2013-01-01", "2022-01-01")):
        m = (t_dec >= pd.Timestamp(a, tz="UTC")) & (t_dec < pd.Timestamp(b, tz="UTC"))
        sd = o.stop_dist.to_numpy()[m]
        px = o.level.to_numpy()[m]
        out["stop_" + lab] = {"n_orders": int(m.sum()), "median_stop_usd": round(float(np.median(sd)), 2),
                              "p10_usd": round(float(np.percentile(sd, 10)), 2), "p90_usd": round(float(np.percentile(sd, 90)), 2),
                              "median_stop_bp": round(float(np.median(sd / px) * 1e4), 1),
                              "min_lot_oz": oz, "min_lot_stop_usd": round(float(np.median(sd) * oz), 2),
                              "min_lot_stop_eur": round(float(np.median(sd) * oz * FX), 2),
                              "p90_min_lot_stop_eur": round(float(np.percentile(sd, 90) * oz * FX), 2)}
        print(lab, out["stop_" + lab])
    json.dump(out, open(os.path.join(RES, "finalist_checks_preval.json"), "w"), indent=1)
    print("configurations so far:", n_configs())
