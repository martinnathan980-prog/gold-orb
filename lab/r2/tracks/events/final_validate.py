"""ONE-SHOT validation (2022-2025) of the finalist fixed in finalists_preval.json.  Run once.
After the official r2.validate call of each sleeve, the SAME trades are re-read once (logged as ':diag')
only to split them by release kind / year and to build the basket view.  Nothing is re-tuned."""
import json, os, sys
import numpy as np, pandas as pd
from runner import use, RES, gl, r2, S

OUT = f"{RES}/validation.json"
if os.path.exists(OUT):
    sys.exit("validation already done: " + OUT)
assert os.path.exists(f"{RES}/finalists_preval.json"), "finalists must be fixed first"
ts = lambda x: float(np.mean(x) / (np.std(x, ddof=1) / np.sqrt(len(x)))) if len(x) > 2 else float("nan")
pf = lambda x: float(x[x > 0].sum() / -x[x < 0].sum()) if (x < 0).any() else float("inf")
res = {}
keep = {}
for name, f in S.FINALISTS.items():
    p = S.resolve(f["params"])
    for sym in f["syms"]:
        m1 = use(sym)
        val = r2.validate(sym, S.make_orders, p, "events", f"{name}:{sym}")
        d = {"val": val["val"], "val_bps_per_trade": val["val_bps_per_trade"], "val_stress": val["val_stress"],
             "val_every_signal": val["val_every_signal"], "val_criteria": val["val_criteria"]}
        # diagnostic split of the same trades (no new configuration)
        t = gl.cut(r2.run(sym, S.make_orders, p, "fp", True, m1), "val", track="events", label=f"{name}:{sym}:diag")
        t = t.assign(bps=t.pnl / t.entry * 1e4)
        d["diag"] = {
            "by_kind": {k: {"n": int(len(x)), "net_bps": round(float(x.bps.mean()), 2), "expR": round(float(x.R.mean()), 4), "t": round(ts(x.R), 2),
                            "win": round(float((x.R > 0).mean()), 2)} for k, x in t.groupby("kind")},
            "by_year": {int(y): {"n": int(len(x)), "R": round(float(x.R.sum()), 2), "net_bps": round(float(x.bps.mean()), 2)} for y, x in t.groupby(t.entry_time.dt.year)},
            "exits": t.reason.value_counts().to_dict(), "R_sd": round(float(t.R.std()), 3), "R_min": round(float(t.R.min()), 3), "R_max": round(float(t.R.max()), 3),
            "t_without_5_best": round(ts(np.sort(t.R.to_numpy())[:-5]), 2), "wins": f"{int((t.R > 0).sum())}/{len(t)}",
            "worst": [(str(r.entry_time)[:16], r.kind, round(r.R, 2), round(r.bps, 1), r.reason) for r in t.nsmallest(5, "R").itertuples()],
            "best": [(str(r.entry_time)[:16], r.kind, round(r.R, 2), round(r.bps, 1), r.reason) for r in t.nlargest(5, "R").itertuples()],
        }
        res[f"{name}:{sym}"] = d
        keep[sym] = t[["t_rel", "R", "kind"]].copy()
        v = val["val"]
        print(f"{name} {sym} VAL: n={v['n']} pf={v['pf']} t={v['t_stat']} expR={v['expectancy_R']} win={v['win_rate']} yrs={v['years_pos']} "
              f"bps={val['val_bps_per_trade']} L={v['long_R']} S={v['short_R']} | stress pf={val['val_stress'].get('pf')} | every expR={val['val_every_signal'].get('expectancy_R')} "
              f"| criteria {val['val_criteria']}", flush=True)
        print("   by kind:", d["diag"]["by_kind"])
        print("   by year:", d["diag"]["by_year"])
        print("   exits:", d["diag"]["exits"], "| R sd/min/max:", d["diag"]["R_sd"], d["diag"]["R_min"], d["diag"]["R_max"], "| wins", d["diag"]["wins"], "| t w/o 5 best", d["diag"]["t_without_5_best"])
        print("   worst:", d["diag"]["worst"])
        print("   best: ", d["diag"]["best"])
pool = pd.concat([keep["us500"].assign(sym="us500"), keep["us100"].assign(sym="us100")])
evm = pool.groupby("t_rel").R.mean()
bas = {"n_pooled": int(len(pool)), "pf_pooled": round(pf(pool.R.to_numpy()), 3), "expR_pooled": round(float(pool.R.mean()), 4),
       "t_pooled_naive": round(ts(pool.R), 2), "n_events": int(len(evm)), "t_event_clustered": round(ts(evm), 2),
       "years_pos": f"{int((pool.groupby(pool.t_rel.dt.year).R.sum() > 0).sum())}/{pool.t_rel.dt.year.nunique()}"}
res["EV_PREM_LONG:basket"] = bas
print("basket VAL:", bas)
json.dump(res, open(OUT, "w"), indent=1, default=str)
