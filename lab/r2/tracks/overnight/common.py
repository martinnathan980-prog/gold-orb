"""Trial runner for the overnight track: every evaluated configuration goes through `trial()`, which logs it
with r2.log_trial("overnight", ...) (the official count) and to trials_full.jsonl (with by-year detail)."""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
for p in (LAB, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
import strategy as S  # noqa: E402

TRACK = "overnight"
RES = os.path.join(LAB, "results", "r2", TRACK)
os.makedirs(RES, exist_ok=True)
_cur = {"sym": None}


def use(sym):
    """Keep only one symbol in memory."""
    if _cur["sym"] != sym:
        r2.free()
        _cur["sym"] = sym


def n_trials():
    p = os.path.join(RES, "trials.jsonl")
    return sum(1 for _ in open(p)) if os.path.exists(p) else 0


def line(ev, label=""):
    r = ev["is"]
    if r.get("n", 0) == 0:
        return f"{label:<44} n=0"
    s = (f"{label:<44} n={r['n']:>4} /yr={r['trades_per_year']:>5} win={r['win_rate']:.3f} PF={r['pf']:.3f} t={r['t_stat']:>5.2f} "
         f"expR={r['expectancy_R']:+.4f} yrs={r['years_pos']} ddR={r['max_dd_R']:>5} L={r['long_R']:+.1f}/S={r['short_R']:+.1f} "
         f"bp={ev['is_bps_per_trade']:+.2f} hold={r['avg_hold_h']}h")
    if "is_stress" in ev:
        s += (f" | stressPF={ev['is_stress'].get('pf')} grossPF={ev['is_gross'].get('pf')} "
              f"gross_bp={ev.get('is_gross_bps_per_trade')}")
    if "is_every_signal" in ev:
        s += f" everyR={ev['is_every_signal'].get('expectancy_R')}"
    return s


def trial(sym, params, label="", full=False, make_orders=None, extra=None):
    """Evaluate ONE configuration on IS under FP costs and log it. Returns the evaluation dict."""
    use(sym)
    mo = make_orders or S.make_orders
    t0 = time.time()
    ev = r2.evaluate(sym, mo, params, full=full)
    r2.log_trial(TRACK, sym, params, ev)
    row = {"k": n_trials(), "label": label, "sym": sym, "params": params, "full": full,
           "is": ev["is"], "is_bps_per_trade": ev.get("is_bps_per_trade")}
    for k in ("is_stress", "is_gross", "is_every_signal"):
        if k in ev:
            row[k] = ev[k]
    if "is_gross_bps_per_trade" in ev:
        row["is_gross_bps_per_trade"] = ev["is_gross_bps_per_trade"]
    if extra:
        row.update(extra)
    with open(os.path.join(RES, "trials_full.jsonl"), "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    msg = f"[{row['k']:>3}] {sym:<7} " + line(ev, label) + f"  ({time.time() - t0:.0f}s)"
    print(msg, flush=True)
    with open(os.path.join(RES, "trials_log.txt"), "a") as f:
        f.write(msg + "\n")
        if ev["is"].get("n", 0):
            f.write("       by year R: " + json.dumps(ev["is"].get("by_year_R")) + " exits: "
                    + json.dumps(ev["is"].get("exit_reasons")) + "\n")
    return ev
