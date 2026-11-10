"""Stage 3 - neighbour robustness of the two candidate finalists (declared before running):
   A = noise-area, paper parameters (lookback 14, checks every 30 min 10:00-15:30, band x1.0, exit 15:55)
   B = opening-candle momentum n=5, stop 0.3 ATR14, size filter >= 1.0 x median(20), exit 15:55
Each tuned / structural parameter is moved to about +/-20% or to its adjacent grid value, one at a time, on us100
and us500.  Quick evaluations (PF under FP costs)."""
from harness import *     # noqa
A = dict(rule="noise")
B = dict(rule="ocm", stop="atr", k=0.3, size_min=1.0)
NEIGH = {
    "A": [("lookback", 11), ("lookback", 17), ("vm", 0.8), ("vm", 1.2), ("step", 15), ("step", 60),
          ("first_min", 585), ("first_min", 630), ("last_min", 900), ("exit_min", 945), ("exit_min", 959), ("hs_atr", 0.5)],
    "B": [("n", 4), ("n", 6), ("k", 0.24), ("k", 0.36), ("size_min", 0.8), ("size_min", 1.2), ("size_win", 16), ("size_win", 24),
          ("atr_n", 11), ("atr_n", 17), ("exit_min", 930), ("exit_min", 959)],
}
out = {}
for sym in ("us100", "us500"):
    for name, base in (("A", A), ("B", B)):
        ev0 = trial(sym, base, full=True, note=f"S3 {name} base FULL")
        rows = []
        for k, v in NEIGH[name]:
            ev = trial(sym, {**base, k: v}, note=f"S3 {name} {k}={v}")
            rows.append({"param": k, "value": v, "n": ev["is"]["n"], "pf": ev["is"]["pf"], "t": ev["is"]["t_stat"], "expR": ev["is"]["expectancy_R"],
                         "years_pos": ev["is"]["years_pos"], "bp": ev["is_bps_per_trade"]})
        pfs = [r["pf"] for r in rows]
        out[f"{name}:{sym}"] = {"base_pf": ev0["is"]["pf"], "neighbors": rows, "median_pf": float(np.median(pfs)), "min_pf": float(np.min(pfs)),
                                "criteria": r2.is_criteria(ev0, neighbor_median_pf=float(np.median(pfs)))}
        print(f"   >>> {name}:{sym} neighbour PFs median={np.median(pfs):.3f} min={np.min(pfs):.3f} max={np.max(pfs):.3f}  criteria={out[f'{name}:{sym}']['criteria']}", flush=True)
    r2.free()
json.dump(out, open(os.path.join(RES, "neighbors.json"), "w"), indent=1, default=str)
print("trials (lines, distinct):", n_trials())
