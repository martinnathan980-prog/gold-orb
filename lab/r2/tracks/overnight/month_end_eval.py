"""IS evaluation of the month-end-night basket (configs of trials 24-26): pooled metrics, per-sleeve and basket nulls."""
import json, sys, time
import numpy as np, pandas as pd
from common import RES, S, r2, trial, use
from basket import basket_ev, null_basket, bps

WD = (0, 1, 2, 3, 4)
US = dict(tz="NY", entry="15:55", exit="09:30", exit_next=True, weekdays=WD, side=1, stop_atr=1.0, atr_tf="D", cond="month_end")
DE = dict(tz="BER", entry="17:25", exit="09:00", exit_next=True, weekdays=WD, side=1, stop_atr=1.0, atr_tf="D", cond="month_end",
          sess_open="09:00", sess_close="17:30")
SLEEVES = [("us500", US), ("us100", US), ("ger40", DE)]

if __name__ == "__main__":
    out = {}
    ev, pooled, per = basket_ev(SLEEVES)
    keep = lambda r: {k: v for k, v in r.items() if k != "exit_reasons"}
    out["basket"] = {k: (keep(v) if isinstance(v, dict) else v) for k, v in ev.items()}
    out["basket_criteria_no_neighbors"] = r2.is_criteria(ev)
    r = ev["is"]
    print("BASKET IS:", {k: r[k] for k in ("n", "trades_per_year", "win_rate", "pf", "t_stat", "expectancy_R", "years_pos", "max_dd_R", "avg_hold_h", "max_hold_h")},
          "cluster_t", ev["cluster_t"], "n_nights", ev["n_clusters"], "bp", ev["is_bps_per_trade"], "gross bp", ev["is_gross_bps_per_trade"])
    print("  by year:", r["by_year_R"], "exits:", r["exit_reasons"])
    print("  stress:", {k: ev["is_stress"][k] for k in ("pf", "t_stat", "expectancy_R")}, "gross:", {k: ev["is_gross"][k] for k in ("pf", "t_stat", "expectancy_R")},
          "every:", {k: ev["is_every_signal"][k] for k in ("n", "pf", "expectancy_R")})
    print("  criteria (no neighbours yet):", out["basket_criteria_no_neighbors"])
    # halves (gross bp per trade), per sleeve
    g = pooled["gross"]; g = g.assign(bp=g.pnl / g.entry * 1e4)
    h1 = g.entry_time < pd.Timestamp("2017-07-01", tz="UTC")
    out["gross_bp_halves"] = {"basket": [round(float(g.bp[h1].mean()), 2), round(float(g.bp[~h1].mean()), 2)]}
    for s, _ in SLEEVES:
        gs = g[g.sym == s]; hh = gs.entry_time < pd.Timestamp("2017-07-01", tz="UTC")
        out["gross_bp_halves"][s] = [round(float(gs.bp[hh].mean()), 2), round(float(gs.bp[~hh].mean()), 2)]
    print("  gross bp/trade first half vs second half:", out["gross_bp_halves"])
    if "null" in sys.argv:
        for s, p in SLEEVES:
            use(s)
            t0 = time.time()
            nt = r2.null_test(s, S.make_orders, p, mode="time")
            out[f"null_{s}"] = nt
            print(f"  null {s}:", nt, f"({time.time()-t0:.0f}s)", flush=True)
        t0 = time.time()
        nb = null_basket(SLEEVES, n_seeds=200, sync=True)
        out["null_basket_sync"] = nb
        print("  null basket (synchronised):", nb, f"({time.time()-t0:.0f}s)", flush=True)
    r2.free()
    json.dump(out, open(f"{RES}/month_end_is.json", "w"), indent=1, default=str)
