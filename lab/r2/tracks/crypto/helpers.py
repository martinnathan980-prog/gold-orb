"""Research bookkeeping for track `crypto`: every evaluated configuration goes through `run_trial`."""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/gold-orb/lab")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402

import strategy as S  # noqa: E402

TRACK = "crypto"
OUT = "/home/user/gold-orb/lab/results/r2/crypto"
os.makedirs(OUT, exist_ok=True)
DETAIL = os.path.join(OUT, "trials_detail.jsonl")


def n_trials():
    p = os.path.join(OUT, "trials.jsonl")
    return sum(1 for _ in open(p)) if os.path.exists(p) else 0


def run_trial(sym, params, full=False, stage="", note="", quiet=False):
    """Evaluate one configuration on IS (FP costs), log it (r2.log_trial + detail file), print one line."""
    t0 = time.time()
    ev = r2.evaluate(sym, S.make_orders, params, full=full)
    r2.log_trial(TRACK, sym, params, ev)
    k = n_trials()
    row = {"k": k, "stage": stage, "note": note, "sym": sym, "params": params, "full": full, "ev": ev}
    with open(DETAIL, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    if not quiet:
        print(fmt(ev, k, params, time.time() - t0), flush=True)
    return ev


def fmt(ev, k=0, params=None, dt=0.0):
    r = ev["is"]
    if r.get("n", 0) == 0:
        return f"#{k:3d} {ev['sym']} n=0 {params}"
    s = (f"#{k:3d} {ev['sym']} n={r['n']:5d} ({r['trades_per_year']:6.1f}/y) win={r['win_rate']:.3f} PF={r['pf']:.3f} "
         f"t={r['t_stat']:5.2f} exp={r['expectancy_R']:+.4f}R bps={ev['is_bps_per_trade']:+7.2f} yrs={r['years_pos']} "
         f"L={r['long_R']:+7.1f}({r['long_n']}) S={r['short_R']:+7.1f}({r['short_n']}) hold={r['avg_hold_h']:5.1f}h dd={r['max_dd_R']:5.1f} "
         f"by={r['by_year_R']}")
    if "is_stress" in ev:
        s += (f" | stressPF={ev['is_stress'].get('pf')} grossPF={ev['is_gross'].get('pf')} grossbps={ev['is_gross_bps_per_trade']}"
              f" every: n={ev['is_every_signal'].get('n')} exp={ev['is_every_signal'].get('expectancy_R')} pf={ev['is_every_signal'].get('pf')}")
    if params is not None:
        s += f" | {compact(params)}"
    return s + (f" [{dt:.0f}s]" if dt else "")


def compact(params):
    return ",".join(f"{k}={v}" for k, v in params.items())


def is_trades(sym, params, mode="fp", no_overlap=True):
    """IS trades frame of a configuration (not a new trial: use only for diagnostics of configs already logged)."""
    t = r2.run(sym, S.make_orders, params, mode, no_overlap)
    return gl.cut(t, "is")
