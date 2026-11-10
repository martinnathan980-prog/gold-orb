"""Single-shot validation (2022-2025) of the two finalists frozen in finalists_preval.json.
Run ONCE.  r2.validate is called once per finalist sleeve; the month-end basket is then pooled from the same
runs (extra accesses are logged with the label '<name>:basket:<sym>').  No parameter is changed afterwards.
Also reports the median stop distance in 2024-2025 and its money value on the minimum lot.
Usage: python3 validate_finalists.py
"""
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

from common import RES, S, gl, r2, use
from basket import bps, cluster_t
from goldlab.metrics import report
from goldlab.split import cut

TRACK = "overnight"
OUT = os.path.join(RES, "finalists_val.json")
EURUSD = 1.16      # assumption for the money value of USD-quoted stops (end-2025 level, order of magnitude only)
KEEP = ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "t_stat", "pf", "total_R", "max_dd_R",
        "years_pos", "long_n", "long_R", "short_n", "short_R", "avg_hold_h", "max_hold_h", "by_year_R", "exit_reasons")
slim = lambda r: {k: r[k] for k in KEEP if k in r}


def stop_money(sym, params):
    """Median stop distance (price units) of the orders entered in 2024-2025 and its value on the minimum lot."""
    use(sym)
    m1 = r2.load(sym)
    o = S.make_orders(m1, **params)
    te = m1.index[o["entry_i"].to_numpy()]
    m = (te >= pd.Timestamp("2024-01-01", tz="UTC")) & (te < pd.Timestamp("2026-01-01", tz="UTC"))
    sd = o["stop_dist"].to_numpy()[m]
    spec = r2.SPEC[sym]
    px = ((m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2)[o["entry_i"].to_numpy()[m]]
    med = float(np.median(sd))
    money_q = med * spec["units_per_lot"] * spec["min_lot"]
    money_eur = money_q if spec["quote"] == "EUR" else money_q / EURUSD
    return {"n_orders_2024_25": int(m.sum()), "median_stop_price_units": round(med, 2),
            "median_stop_pct_of_price": round(float(np.median(sd / px) * 100), 3),
            "p90_stop_price_units": round(float(np.percentile(sd, 90)), 2),
            "min_lot": spec["min_lot"], "units_per_lot": spec["units_per_lot"], "quote": spec["quote"],
            "min_lot_stop_money_quote_ccy": round(money_q, 2), "min_lot_stop_money_eur": round(money_eur, 2),
            "p90_min_lot_stop_money_eur": round(float(np.percentile(sd, 90)) * spec["units_per_lot"] * spec["min_lot"]
                                                / (1 if spec["quote"] == "EUR" else EURUSD), 2),
            "sizeable_on_1000eur": bool(money_eur <= 30)}


if __name__ == "__main__":
    pre = json.load(open(os.path.join(RES, "finalists_preval.json")))
    if os.path.exists(OUT):
        sys.exit("finalists_val.json already exists: validation is single-shot")
    out = {"validated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "preval_written_utc": pre["written_utc"],
           "finalists": {}}
    for name, f in pre["finalists"].items():
        res = {"sleeves": {}}
        pooled = {"fp": [], "stress": [], "every": []}
        for sym in f["syms"]:
            p = S.finalist_params(name, sym)
            assert json.loads(json.dumps(p)) == f["sleeves"][sym]["params"], "parameters differ from the frozen pre-validation file"
            use(sym)
            v = r2.validate(sym, S.make_orders, p, TRACK, f"{name}:{sym}")
            res["sleeves"][sym] = {"val": slim(v["val"]), "val_bps_per_trade": v["val_bps_per_trade"],
                                   "val_stress": slim(v["val_stress"]), "val_every_signal": slim(v["val_every_signal"]),
                                   "val_criteria": v["val_criteria"], "stop_2024_25": stop_money(sym, p)}
            r = v["val"]
            print(f"VAL {name} {sym}: n={r.get('n')} PF={r.get('pf')} t={r.get('t_stat')} expR={r.get('expectancy_R')} yrs={r.get('years_pos')} "
                  f"L={r.get('long_R')}/S={r.get('short_R')} bp={v['val_bps_per_trade']} stressPF={v['val_stress'].get('pf')} "
                  f"everyR={v['val_every_signal'].get('expectancy_R')} crit={v['val_criteria']} by_year={r.get('by_year_R')}", flush=True)
            print("    stop 2024-25:", res["sleeves"][sym]["stop_2024_25"], flush=True)
            if len(f["syms"]) > 1:
                m1 = r2.load(sym)
                for mode, key, no in (("fp", "fp", True), ("stress", "stress", True), ("fp", "every", False)):
                    t = cut(r2.run(sym, S.make_orders, p, mode, no, m1), "val", track=TRACK, label=f"{name}:basket:{sym}:{key}").copy()
                    t["sym"] = sym
                    pooled[key].append(t)
        if len(f["syms"]) > 1:
            pv = {k: pd.concat(v).sort_values("entry_time") for k, v in pooled.items()}
            rb, rs, re_ = report(pv["fp"]), report(pv["stress"]), report(pv["every"])
            ct, nc = cluster_t(pv["fp"])
            crit = {"pf>=1.06": rb.get("pf", 0) >= 1.06, "expectancy>0": rb.get("expectancy_R", -1) > 0,
                    "every_signal_exp>0": re_.get("expectancy_R", -1) > 0}
            crit["pass"] = all(crit.values())
            crit["each_sleeve_expectancy>0"] = all(res["sleeves"][s]["val"].get("expectancy_R", -1) > 0 for s in f["syms"])
            night = pv["fp"].groupby(pv["fp"].entry_time.dt.tz_convert("America/New_York").dt.floor("D"))["R"].sum()
            res["basket"] = {"val": slim(rb), "val_bps_per_trade": bps(pv["fp"]), "val_stress": slim(rs), "val_every_signal": slim(re_),
                             "cluster_t_by_night": ct, "n_nights": nc, "nights_positive_pct": round(float((night > 0).mean() * 100), 1),
                             "val_criteria": crit}
            print(f"VAL {name} BASKET: n={rb['n']} PF={rb['pf']} t={rb['t_stat']} (cluster t {ct} on {nc} nights) expR={rb['expectancy_R']} "
                  f"yrs={rb['years_pos']} bp={bps(pv['fp'])} stressPF={rs['pf']} everyR={re_['expectancy_R']} crit={crit} by_year={rb['by_year_R']}",
                  flush=True)
        out["finalists"][name] = res
    r2.free()
    json.dump(out, open(OUT, "w"), indent=1, default=str)
    print("written", OUT)
