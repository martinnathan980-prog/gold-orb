"""Stage 6 - candidate B4: opening-candle momentum with a 4-minute candle (entry 09:34, one minute BEFORE the
5-minute crowd; no first-minute burst to capture at its own entry), stop 0.3 ATR14, size filter >= 1.0 x median(20),
exit 15:55, us100.  Full IS evaluation + neighbours (one parameter at a time) + one-minute latency test."""
from harness import *     # noqa
B4 = dict(rule="ocm", n=4, stop="atr", k=0.3, size_min=1.0)
NEIGH = [("n", 3), ("n", 5), ("k", 0.24), ("k", 0.36), ("size_min", 0.8), ("size_min", 1.2), ("size_win", 16), ("size_win", 24),
         ("atr_n", 11), ("atr_n", 17), ("exit_min", 930), ("exit_min", 959), ("delay", 1)]
sym = "us100"
ev0 = trial(sym, B4, full=True, note="S6 B4 base FULL")
rows = []
for k, v in NEIGH:
    ev = trial(sym, {**B4, k: v}, note=f"S6 B4 {k}={v}")
    rows.append({"param": k, "value": v, "n": ev["is"]["n"], "pf": ev["is"]["pf"], "t": ev["is"]["t_stat"], "expR": ev["is"]["expectancy_R"],
                 "years_pos": ev["is"]["years_pos"], "bp": ev["is_bps_per_trade"]})
pfs = [r["pf"] for r in rows]
out = {"B4:us100": {"base_pf": ev0["is"]["pf"], "neighbors": rows, "median_pf": float(np.median(pfs)), "min_pf": float(np.min(pfs)),
                    "criteria": r2.is_criteria(ev0, neighbor_median_pf=float(np.median(pfs)))}}
print(f"   >>> B4:us100 neighbour PFs median={np.median(pfs):.3f} min={np.min(pfs):.3f} max={np.max(pfs):.3f} criteria={out['B4:us100']['criteria']}")
json.dump(out, open(os.path.join(RES, "neighbors_B4.json"), "w"), indent=1, default=str)
print("trials (lines, distinct):", n_trials())
