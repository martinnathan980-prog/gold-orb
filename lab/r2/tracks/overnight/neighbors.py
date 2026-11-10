"""Neighbour robustness (IS) of the two candidate finalists. Every neighbour of every sleeve is a logged trial.
Usage: python3 neighbors.py gold | month_end | btc
"""
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd

from common import LAB, RES, S, gl, r2, trial, use
from goldlab.metrics import report
from goldlab.split import cut

WD = (0, 1, 2, 3, 4)
ALL = (0, 1, 2, 3, 4, 5, 6)
US = dict(tz="NY", entry="15:55", exit="09:30", exit_next=True, weekdays=WD, side=1, stop_atr=1.0, atr_tf="D", cond="month_end")
DE = dict(tz="BER", entry="17:25", exit="09:00", exit_next=True, weekdays=WD, side=1, stop_atr=1.0, atr_tf="D", cond="month_end",
          sess_open="09:00", sess_close="17:30")


def gold():
    """Round-1 neighbour set of FRI_PM_LIM (entry +-30 min, adjacent exits, stop +-20 %, limit window +-20 %,
    limit offset +0.1 ATR), re-run under FP costs."""
    spec = importlib.util.spec_from_file_location("seasonality_strategy", os.path.join(LAB, "tracks", "seasonality", "strategy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    base = dict(mod.FINALISTS["FRI_PM_LIM"])
    var = [("entry 13:00", dict(entry_time="13:00")), ("entry 14:00", dict(entry_time="14:00")),
           ("exit 16:30", dict(exit_time="16:30")), ("exit 16:55", dict(exit_time="16:55")),
           ("k 2.4", dict(stop_atr=2.4)), ("k 3.6", dict(stop_atr=3.6)),
           ("lim 48m", dict(limit_min=48)), ("lim 72m", dict(limit_min=72)), ("off 0.1", dict(limit_off=0.1))]
    rows = []
    for lab, ch in var:
        p = {**base, **ch}
        ev = trial("xauusd", p, f"NB gold FRI_PM_LIM {lab}", make_orders=mod.make_orders, extra={"neighbor_of": "GOLD_FRI_PM"})
        rows.append({"neighbor": lab, "params": p, "n": ev["is"]["n"], "pf": ev["is"]["pf"], "t": ev["is"]["t_stat"],
                     "exp": ev["is"]["expectancy_R"], "years_pos": ev["is"]["years_pos"], "bp": ev["is_bps_per_trade"]})
    med = float(np.median([r["pf"] for r in rows]))
    print(f"### GOLD_FRI_PM: median neighbour PF = {med:.3f} (min {min(r['pf'] for r in rows):.3f}, max {max(r['pf'] for r in rows):.3f})")
    return {"median_neighbor_pf": med, "neighbors": rows}


def month_end():
    """Month-end night basket: stop +-20 %, entry -25 / +15 min (US) or -25 / +20 min (DE), exit +-30 min."""
    var = [("stop 0.8", dict(stop_atr=0.8), dict(stop_atr=0.8)), ("stop 1.2", dict(stop_atr=1.2), dict(stop_atr=1.2)),
           ("entry earlier", dict(entry="15:30"), dict(entry="17:00")), ("entry later", dict(entry="16:10"), dict(entry="17:45")),
           ("exit earlier", dict(exit="09:00"), dict(exit="08:30")), ("exit later", dict(exit="10:00"), dict(exit="09:30"))]
    rows = []
    for lab, chu, chd in var:
        pooled, sl = [], {}
        for sym, base, ch in (("us500", US, chu), ("us100", US, chu), ("ger40", DE, chd)):
            p = {**base, **ch}
            ev = trial(sym, p, f"NB month-end {lab}", extra={"neighbor_of": "MONTH_END_NIGHT"})
            t = cut(r2.run(sym, S.make_orders, p, "fp", True, r2.load(sym)), "is")
            pooled.append(t)
            sl[sym] = {"n": ev["is"]["n"], "pf": ev["is"]["pf"], "t": ev["is"]["t_stat"], "exp": ev["is"]["expectancy_R"]}
        rep = report(pd.concat(pooled).sort_values("entry_time"))
        rows.append({"neighbor": lab, "us": chu, "de": chd, "basket_n": rep["n"], "basket_pf": rep["pf"], "basket_t": rep["t_stat"],
                     "basket_exp": rep["expectancy_R"], "basket_years_pos": rep["years_pos"], "sleeves": sl})
        print(f"    basket {lab}: n={rep['n']} PF={rep['pf']} t={rep['t_stat']} expR={rep['expectancy_R']} yrs={rep['years_pos']}", flush=True)
    med = float(np.median([r["basket_pf"] for r in rows]))
    per = {s: float(np.median([r["sleeves"][s]["pf"] for r in rows])) for s in ("us500", "us100", "ger40")}
    print(f"### MONTH_END_NIGHT: median neighbour basket PF = {med:.3f}; per-sleeve medians {per}")
    return {"median_neighbor_pf": med, "median_neighbor_pf_by_sleeve": per, "neighbors": rows}


def btc():
    """Bitcoin late-day drift (rejected near-miss): documentation neighbours -- exit 18:30 / 19:30, Monday-Friday only."""
    base = dict(tz="NY", entry="17:05", exit="19:00", weekdays=ALL, side=1, stop_atr=2.0, atr_tf="1h")
    rows = []
    for lab, ch in [("exit 18:30", dict(exit="18:30")), ("exit 19:30", dict(exit="19:30")), ("Mon-Fri only", dict(weekdays=WD))]:
        p = {**base, **ch}
        ev = trial("btcusd", p, f"NB btc late {lab}", extra={"neighbor_of": "BTC_LATE (rejected)"})
        rows.append({"neighbor": lab, "params": p, "n": ev["is"]["n"], "pf": ev["is"]["pf"], "t": ev["is"]["t_stat"],
                     "exp": ev["is"]["expectancy_R"], "years_pos": ev["is"]["years_pos"], "bp": ev["is_bps_per_trade"]})
    return {"neighbors": rows}


if __name__ == "__main__":
    p = os.path.join(RES, "neighbors.json")
    out = json.load(open(p)) if os.path.exists(p) else {}
    for nm in sys.argv[1:]:
        out[nm] = {"gold": gold, "month_end": month_end, "btc": btc}[nm]()
        json.dump(out, open(p, "w"), indent=1, default=str)
    r2.free()
