"""Pre-validation checks (IS ONLY for every performance number): halves, long/short, null, extra cost stress,
stop distance 2024-2025 (order sizes only - no trade outcome of the validation period is read)."""
import json, sys
import numpy as np, pandas as pd
from dataclasses import replace
from runner import use, RES, gl, r2, S
from goldlab.sim import apply_spread_mult, simulate

FIN = {
    "EV_PREM_LONG": {"syms": ["us500", "us100"], "params": dict(rule="long", kinds="fomc+nfp+cpi", lead=5, exit="hold", hold=15, stop_atr=1.0, atr_n=14), "null": "time"},
    "XAU_FOMC_MOM": {"syms": ["xauusd"], "params": dict(rule="mom", kinds="fomc", k=5, exit="hhmm", exit_hhmm="15:55", exit_days=1, stop_atr=0.5, atr_n=14), "null": "day"},
}
ts = lambda x: float(np.mean(x) / (np.std(x, ddof=1) / np.sqrt(len(x)))) if len(x) > 2 else float("nan")
pf = lambda x: float(x[x > 0].sum() / -x[x < 0].sum()) if (x < 0).any() else float("inf")
MID = pd.Timestamp("2017-07-01", tz="UTC")
out = {}
keep_R = {}
for name, f in FIN.items():
    for sym in f["syms"]:
        m1 = use(sym)
        p = S.resolve(f["params"])
        o = S.make_orders(m1, **p)
        t = gl.cut(r2.run(sym, S.make_orders, p, "fp", True, m1), "is")
        g = gl.cut(r2.run(sym, S.make_orders, p, "gross", True, m1), "is")
        gb = (g.pnl / g.entry * 1e4)
        d = {"is_n": int(len(t)), "is_long_n": int((t.side > 0).sum()), "is_short_n": int((t.side < 0).sum()),
             "is_long_R": round(float(t.R[t.side > 0].sum()), 2), "is_short_R": round(float(t.R[t.side < 0].sum()), 2),
             "is_long_expR": round(float(t.R[t.side > 0].mean()), 4) if (t.side > 0).any() else None,
             "is_short_expR": round(float(t.R[t.side < 0].mean()), 4) if (t.side < 0).any() else None,
             "gross_bps_first_half": round(float(gb[g.entry_time < MID].mean()), 2), "gross_bps_second_half": round(float(gb[g.entry_time >= MID].mean()), 2),
             "gross_t_first_half": round(ts(gb[g.entry_time < MID]), 2), "gross_t_second_half": round(ts(gb[g.entry_time >= MID]), 2),
             "n_first_half": int((g.entry_time < MID).sum()), "n_second_half": int((g.entry_time >= MID).sum()),
             "gross_pf": round(pf(g.R.to_numpy()), 3), "gross_bps": round(float(gb.mean()), 2),
             "R_sd": round(float(t.R.std()), 3), "R_p05": round(float(t.R.quantile(.05)), 3), "R_min": round(float(t.R.min()), 3),
             "exits": t.reason.value_counts().to_dict(),
             "by_year_R": {int(k): round(float(v), 2) for k, v in t.groupby(t.entry_time.dt.year).R.sum().items()}}
        # extra cost stress x3 (spread and slippage tripled) - IS only
        mk = apply_spread_mult(m1, 3.0)
        t3 = gl.cut(simulate(mk, S.make_orders(mk, **p), sym=sym, costs=r2.costs(sym, 3.0)), "is")
        d["cost_x3"] = {"pf": round(pf(t3.R.to_numpy()), 3), "expR": round(float(t3.R.mean()), 4), "t": round(ts(t3.R), 2), "bps": round(float((t3.pnl / t3.entry).mean() * 1e4), 2)}
        del mk
        # break-even extra cost per round trip in bp of price = net bps per trade
        d["net_bps"] = round(float((t.pnl / t.entry).mean() * 1e4), 2)
        # stop distance of the ORDERS of 2024-2025 (sizes only)
        o2 = o[(o.t_rel >= pd.Timestamp("2024-01-01", tz="UTC")) & (o.t_rel < pd.Timestamp("2026-01-01", tz="UTC"))]
        sp = r2.SPEC[sym]
        med = float(o2.stop_dist.median())
        d["median_stop_2024_25"] = round(med, 2)
        d["n_orders_2024_25"] = int(len(o2))
        d["min_lot_stop_money_quote"] = round(med * sp["units_per_lot"] * sp["min_lot"], 2)
        d["min_lot"] = sp["min_lot"]; d["units_per_lot"] = sp["units_per_lot"]; d["quote"] = sp["quote"]
        # null
        nul = r2.null_test(sym, S.make_orders, p, n_seeds=200, mode=f["null"])
        d["null"] = nul
        out[f"{name}:{sym}"] = d
        keep_R[(name, sym)] = t[["t_rel", "R", "side", "kind"]].copy()
        print(name, sym, json.dumps(d, default=str), flush=True)
# basket view of EV_PREM_LONG (us500 + us100): pooled trades and event-clustered t
a, b = keep_R[("EV_PREM_LONG", "us500")], keep_R[("EV_PREM_LONG", "us100")]
pool = pd.concat([a.assign(sym="us500"), b.assign(sym="us100")])
evm = pool.groupby("t_rel").R.mean()
j = a.set_index("t_rel").R.to_frame("a").join(b.set_index("t_rel").R.to_frame("b"), how="inner")
bas = {"n_pooled": int(len(pool)), "pf_pooled": round(pf(pool.R.to_numpy()), 3), "expR_pooled": round(float(pool.R.mean()), 4), "t_pooled_naive": round(ts(pool.R), 2),
       "n_events": int(len(evm)), "t_event_clustered": round(ts(evm), 2), "corr_R_us500_us100": round(float(j.a.corr(j.b)), 3),
       "years_pos": f"{int((pool.groupby(pool.t_rel.dt.year).R.sum() > 0).sum())}/{pool.t_rel.dt.year.nunique()}"}
out["EV_PREM_LONG:basket"] = bas
print("basket", bas)
json.dump(out, open(f"{RES}/preval_checks.json", "w"), indent=1, default=str)
