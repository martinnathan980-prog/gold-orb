"""Research harness for track `orb` (IS only).  Every evaluated config is logged once via
gl.log_trial("orb", ...).  Orders are restricted to IS dates BEFORE simulation, so no VAL trade is
ever simulated during research."""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import goldlab as gl  # noqa: E402
from goldlab.evalkit import evaluate_is, is_criteria  # noqa: E402

import strategy as S  # noqa: E402

RES = os.path.join(HERE, "..", "..", "results", "orb")
CACHE = os.path.join(RES, "research_cache.jsonl")
IS_END = pd.Timestamp("2022-01-01")

_m1 = None


def m1():
    global _m1
    if _m1 is None:
        _m1 = gl.load_m1("xauusd")
    return _m1


def full_params(params):
    p = dict(S.DEFAULTS)
    p.update(params)
    p["skip_dow"] = list(p["skip_dow"])
    return p


def _key(p):
    # None-valued params are "off": excluded so adding new optional params keeps old keys valid
    return json.dumps({k: v for k, v in p.items() if v is not None}, sort_keys=True, default=str)


def load_cache():
    out = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            for line in f:
                d = json.loads(line)
                out[d["key"]] = d
    return out


def side_stats(t):
    out = {}
    for nm, sub in (("long", t[t.side > 0]), ("short", t[t.side < 0])):
        R = sub.R.to_numpy()
        if len(R) < 3:
            out[nm] = {"n": int(len(R))}
            continue
        g, l = R[R > 0].sum(), -R[R < 0].sum()
        out[nm] = {"n": int(len(R)), "pf": round(float(g / l), 3) if l > 0 else None,
                   "exp": round(float(R.mean()), 4),
                   "t": round(float(R.mean() / (R.std(ddof=1) / np.sqrt(len(R)))), 2)}
    return out


def run(label, params, stage="", quiet=False, no_overlap=True):
    """Evaluate one config on IS (normal + x1.5 costs), log it, cache it. Returns summary dict.
    no_overlap=False is a DIAGNOSTIC (every session's signal traded, positions may overlap)."""
    p = full_params(params)
    if not no_overlap:
        p["no_overlap"] = False
    key = _key(p)
    cache = load_cache()
    if key in cache:
        d = cache[key]
        if not quiet:
            pr(d)
        return d
    t0 = time.time()
    o = S.make_orders(m1(), **params)
    o = o[pd.to_datetime(o.date) < IS_END].reset_index(drop=True)
    t, rep, rs = evaluate_is(m1(), o, no_overlap=no_overlap)
    t = gl.cut(t, "is")
    gl.log_trial("orb", {"label": label, "stage": stage, **p}, rep)
    crit = is_criteria(rep, rs)
    d = {"key": key, "label": label, "stage": stage, "params": p,
         "rep": rep, "stress_pf": rs.get("pf"), "stress_exp": rs.get("expectancy_R"),
         "sides": side_stats(t), "crit": crit, "orders": int(len(o)),
         "skipped": int(t.attrs.get("skipped", 0)), "secs": round(time.time() - t0, 1)}
    os.makedirs(RES, exist_ok=True)
    with open(CACHE, "a") as f:
        f.write(json.dumps(d, default=str) + "\n")
    if not quiet:
        pr(d)
    return d


def pr(d):
    r = d["rep"]
    if r.get("n", 0) == 0:
        print(f"[{d['label']}] no trades")
        return
    sd = d["sides"]
    print(f"[{d['label']}] n={r['n']} ({r['trades_per_year']}/yr) win={r['win_rate']} "
          f"avgW={r['avg_win_R']} avgL={r['avg_loss_R']} exp={r['expectancy_R']} PF={r['pf']} t={r['t_stat']} "
          f"yrs+={r['years_pos']} wk+={r['weeks_pos_pct']}% DD={r['max_dd_R']}R | stressPF={d['stress_pf']} "
          f"| L {sd['long']} S {sd['short']} | hold={r['avg_hold_h']}h pass={d['crit'].get('pass')}")
    print(f"      years: {r['by_year_R']}  exits: {r['exit_reasons']}")


def n_trials():
    p = os.path.join(RES, "trials.jsonl")
    return sum(1 for _ in open(p)) if os.path.exists(p) else 0
