"""Research harness for the pivots track: every evaluated config is logged (IS only)."""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strategy as S  # noqa: E402
import goldlab as gl  # noqa: E402
from goldlab.evalkit import evaluate_is, is_criteria  # noqa: E402

OUT = os.path.join(S._LAB, "results", "pivots")
_M1 = {}


def m1():
    """IS research frame: data strictly before 2022 (VAL never loaded during research)."""
    if "is" not in _M1:
        _M1["is"] = gl.load_m1("xauusd", end="2022-01-01")
    return _M1["is"]


def ntrials():
    f = os.path.join(OUT, "trials.jsonl")
    return sum(1 for _ in open(f)) if os.path.exists(f) else 0


def fmt(r, rs=None):
    if r.get("n", 0) == 0:
        return "n=0"
    s = (f"n={r['n']:4d} tpy={r['trades_per_year']:5.1f} win={r['win_rate']:.3f} "
         f"aw={r['avg_win_R']:.2f} al={r['avg_loss_R']:.2f} exp={r['expectancy_R']:+.3f} "
         f"PF={r['pf']:.3f} t={r['t_stat']:+.2f} yrs={r['years_pos']} wk+={r['weeks_pos_pct']:.0f}% "
         f"dd={r['max_dd_R']:.1f} L={r['long_n']}/{r['long_R']:+.1f} S={r['short_n']}/{r['short_R']:+.1f}")
    if rs is not None:
        s += f" | stressPF={rs.get('pf', float('nan')):.3f}"
    return s


def run(name, params, log=True, show=True, data=None):
    """Simulate (normal + costs x1.5), log, return (trades, rep, rep_stress, crit)."""
    d = m1() if data is None else data
    o = S.make_orders(d, **params)
    t, rep, rs = evaluate_is(d, o)
    crit = is_criteria(rep, rs) if rep.get("n", 0) else {"pass": False}
    if log:
        gl.log_trial("pivots", {"name": name, **params},
                     {**rep, "stress_pf": rs.get("pf"), "is_pass": crit.get("pass")})
    if show:
        print(f"[{ntrials():3d}] {name:28s} {fmt(rep, rs)}")
        if rep.get("n", 0):
            print(f"      by year: {rep['by_year_R']}  exits: {rep['exit_reasons']}")
    return t, rep, rs, crit


def run_placebo(name, params, seeds=range(1, 11), log=True):
    """Same rules on randomly shifted levels; pooled report + per-seed PF.  ONE logged trial."""
    d = m1()
    ts, pfs, exps = [], [], []
    for sd in seeds:
        o = S.make_orders(d, **{**params, "placebo": int(sd)})
        t = gl.simulate(d, o)
        t = gl.cut(t, "is")
        r = gl.report(t)
        pfs.append(r.get("pf", np.nan))
        exps.append(r.get("expectancy_R", np.nan))
        ts.append(t.assign(seed=sd))
    T = pd.concat(ts)
    rp = gl.report(T.sort_values("entry_time"))
    rp_short = {k: v for k, v in rp.items() if k not in ("by_year_R", "exit_reasons")}
    out = {**rp_short, "n_per_seed": round(rp["n"] / len(pfs), 1), "seed_pf": [round(x, 3) for x in pfs],
           "seed_exp": [round(x, 4) for x in exps], "pf_median": round(float(np.median(pfs)), 3),
           "pf_p90": round(float(np.quantile(pfs, 0.9)), 3)}
    if log:
        gl.log_trial("pivots", {"name": name + "/PLACEBO", **params, "placebo_seeds": list(seeds)}, out)
    print(f"[{ntrials():3d}] {name + '/PLACEBO':28s} pooled PF={rp['pf']:.3f} exp={rp['expectancy_R']:+.3f} "
          f"n/seed={out['n_per_seed']} seedPF med={out['pf_median']} range=[{min(pfs):.3f},{max(pfs):.3f}]")
    return out
