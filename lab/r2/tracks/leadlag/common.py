"""leadlag track - research driver helpers (evaluation + logging)."""
import gc
import json
import os
import sys
import time

import numpy as np
import pandas as pd

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
import strategy  # noqa: E402

TRACK = "leadlag"
RES = os.path.join(LAB, "results", "r2", TRACK)
os.makedirs(RES, exist_ok=True)
_cur = {"sym": None}


def use(sym):
    """One follower frame in the r2 cache at a time."""
    if _cur["sym"] != sym:
        r2.free()
        gc.collect()
        _cur["sym"] = sym


def run(sym, params, full=False, tag="", quiet=False):
    use(sym)
    t = time.time()
    ev = r2.evaluate(sym, strategy.make_orders, params, full=full)
    r2.log_trial(TRACK, sym, params, ev)
    r = ev["is"]
    row = {"tag": tag, "sym": sym, "params": params, "full": full, "is": r, "is_bps": ev.get("is_bps_per_trade")}
    for k in ("is_stress", "is_gross", "is_every_signal"):
        if k in ev:
            row[k] = ev[k]
    if "is_gross_bps_per_trade" in ev:
        row["gross_bps"] = ev["is_gross_bps_per_trade"]
    with open(os.path.join(RES, "explore.jsonl"), "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    if not quiet:
        if r.get("n", 0) == 0:
            print(f"[{tag}] {sym} {json.dumps(params)} -> no trades", flush=True)
        else:
            s = (f"[{tag}] {sym} n={r['n']} ({r['trades_per_year']}/yr) win={r['win_rate']} PF={r['pf']} t={r['t_stat']} "
                 f"expR={r['expectancy_R']} bps={ev.get('is_bps_per_trade')} yrs+={r['years_pos']} L/S R={r['long_R']}/{r['short_R']} "
                 f"hold={r['avg_hold_h']}h maxDD={r['max_dd_R']}R")
            if full:
                s += (f" | stressPF={ev['is_stress'].get('pf')} grossPF={ev['is_gross'].get('pf')} gross_bps={ev.get('is_gross_bps_per_trade')} "
                      f"everyExpR={ev['is_every_signal'].get('expectancy_R')} (n={ev['is_every_signal'].get('n')})")
            print(s, f"| {time.time()-t:.0f}s", flush=True)
            print("      ", json.dumps({k: v for k, v in params.items() if k not in ('rule',)}), "| by year:", r.get("by_year_R"), "| exits:", r.get("exit_reasons"), flush=True)
    return ev


def n_trials():
    p = os.path.join(RES, "trials.jsonl")
    if not os.path.exists(p):
        return 0, 0
    rows = [json.loads(l) for l in open(p)]
    distinct = {(r["sym"], json.dumps(r["params"], sort_keys=True)) for r in rows}
    return len(rows), len(distinct)
