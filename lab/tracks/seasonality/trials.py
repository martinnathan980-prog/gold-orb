"""IS trial runner for the seasonality track.  Every evaluated configuration is logged with
gl.log_trial("seasonality", ...).  Only IS data (to 2022-01-10, margin for exits) is loaded here,
so validation trades are never even simulated during research."""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import RES, gl  # noqa: E402
from goldlab.evalkit import evaluate_is, is_criteria  # noqa: E402
import strategy  # noqa: E402

_M1 = {}


def m1_is():
    if "is" not in _M1:
        _M1["is"] = gl.load_m1("xauusd", "2012-11-01", "2022-01-10")
    return _M1["is"]


def evaluate(name, params, log=True, quiet=False):
    m1 = m1_is()
    o = strategy.make_orders(m1, **params)
    t, rep, rep_s = evaluate_is(m1, o)
    ti = gl.cut(t, "is")
    crit = is_criteria(rep, rep_s)
    extra = {"stress_pf": rep_s.get("pf"), "stress_exp": rep_s.get("expectancy_R"),
             "orders": int(len(o)), "skipped": int(t.attrs.get("skipped", 0)),
             "nofill": int(t.attrs.get("nofill", 0)), "pass": bool(crit.get("pass"))}
    if log:
        gl.log_trial("seasonality", {"name": name, **params}, {**rep, **extra})
        with open(os.path.join(RES, "trials_full.jsonl"), "a") as f:
            f.write(json.dumps({"name": name, "params": params, "is": rep, "stress": {k: rep_s.get(k) for k in ("pf", "expectancy_R", "t_stat")},
                                **extra}, default=str) + "\n")
    if not quiet:
        print(fmt(name, rep, rep_s, extra))
    return t, rep, rep_s, crit


def fmt(name, rep, rep_s, extra):
    if rep.get("n", 0) == 0:
        return f"{name}: no trades"
    return (f"{name:34s} n={rep['n']:4d} tpy={rep['trades_per_year']:5.1f} win={rep['win_rate']:.3f} "
            f"aw={rep['avg_win_R']:+.3f} al={rep['avg_loss_R']:+.3f} exp={rep['expectancy_R']:+.4f} t={rep['t_stat']:+5.2f} "
            f"PF={rep['pf']:.3f} stressPF={rep_s.get('pf', float('nan')):.3f} yrs={rep['years_pos']} wk+={rep['weeks_pos_pct']} "
            f"dd={rep['max_dd_R']} L={rep['long_n']}/{rep['long_R']} S={rep['short_n']}/{rep['short_R']} "
            f"hold={rep['avg_hold_h']}h nofill={extra['nofill']} skip={extra['skipped']} | {rep['by_year_R']} {rep['exit_reasons']}")
