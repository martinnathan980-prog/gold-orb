"""IS research runner for the meanrev track.

Every configuration evaluated through `ev()` is logged with goldlab.log_trial (trial budget
<= 150).  Research loads M1 only up to 2022-01-10 (IS + a few days so that late-2021 trades can
close) so that validation data cannot leak into the study by accident.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, LAB)
sys.path.insert(0, HERE)
import goldlab as gl  # noqa: E402
from goldlab.evalkit import evaluate_is, is_criteria  # noqa: E402
from strategy import make_orders  # noqa: E402

TRACK = "meanrev"
TRIALS = os.path.join(LAB, "results", TRACK, "trials.jsonl")
SCRATCH = os.environ.get("MR_SCRATCH", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad")
_M1 = None


def m1_is():
    global _M1
    if _M1 is None:
        _M1 = gl.load_m1("xauusd", end="2022-01-10")
    return _M1


def n_trials():
    if not os.path.exists(TRIALS):
        return 0
    with open(TRIALS) as f:
        return sum(1 for _ in f)


def _pf(x):
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return round(float(g / l), 3) if l > 0 else float("nan")


def side_stats(t):
    out = {}
    for nm, s in (("long", 1), ("short", -1)):
        x = t.loc[t.side == s, "R"].to_numpy()
        out[f"{nm}_pf"] = _pf(x) if len(x) else float("nan")
        out[f"{nm}_exp"] = round(float(x.mean()), 4) if len(x) else float("nan")
    return out


def ev(cfg, stage, note="", save=True, log=True, quiet=False):
    """Evaluate one config on IS (normal + costs x1.5). Logs it. Returns (t_is, rep, rep_stress)."""
    m1 = m1_is()
    orders = make_orders(m1, **cfg)
    t, rep, rs = evaluate_is(m1, orders)
    t_is = gl.cut(t, "is")
    extra = {"stress_pf": rs.get("pf"), "stress_exp": rs.get("expectancy_R"),
             "by_year": json.dumps(rep.get("by_year_R", {})),
             "orders": int(len(orders)), "skipped": int(t.attrs.get("skipped", 0))}
    if len(t_is):
        extra.update(side_stats(t_is))
    if log:
        gl.log_trial(TRACK, dict(cfg, _stage=stage, _note=note), dict(rep, **extra))
    k = n_trials()
    if save:
        t_is.to_pickle(os.path.join(SCRATCH, f"t_{k:03d}.pkl"))
    if not quiet:
        print(line(k, cfg, rep, extra))
    return t_is, rep, rs


def line(k, cfg, rep, extra):
    if rep.get("n", 0) == 0:
        return f"#{k:03d} {cfg} -> no trades"
    c = {kk: v for kk, v in cfg.items()}
    return (f"#{k:03d} {json.dumps(c)}\n      n={rep['n']} tpy={rep['trades_per_year']} win={rep['win_rate']}"
            f" W={rep['avg_win_R']} L={rep['avg_loss_R']} exp={rep['expectancy_R']} PF={rep['pf']}"
            f" t={rep['t_stat']} yrs+={rep['years_pos']} wk+={rep['weeks_pos_pct']} dd={rep['max_dd_R']}"
            f" | stressPF={extra['stress_pf']} | L n={rep['long_n']} R={rep['long_R']} pf={extra.get('long_pf')}"
            f" | S n={rep['short_n']} R={rep['short_R']} pf={extra.get('short_pf')} | hold={rep['avg_hold_h']}h"
            f" max={rep['max_hold_h']}h\n      by_year={rep['by_year_R']} exits={rep['exit_reasons']}")
