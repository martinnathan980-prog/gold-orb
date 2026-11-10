"""In-sample research harness for track idx_eu (round 2).

Every configuration goes through `trial()`: r2.evaluate (IS reports only) + r2.log_trial, once per
distinct (sym, params) -- a cache prevents double logging.  Nothing here touches the validation period.
"""
import json
import os
import sys

sys.path.insert(0, "/home/user/gold-orb/lab")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.split import cut  # noqa: E402

import strategy as S  # noqa: E402

TRACK = "idx_eu"
SYM = "ger40"
OUT = os.path.join("/home/user/gold-orb/lab/results/r2", TRACK)
CACHE = os.path.join(OUT, "research_cache.jsonl")
BUDGET = 120
os.makedirs(OUT, exist_ok=True)


def _key(sym, params):
    return json.dumps({"sym": sym, **{k: (list(v) if isinstance(v, tuple) else v) for k, v in sorted(params.items())}},
                      sort_keys=True, default=str)


def _load_cache():
    c = {}
    if os.path.exists(CACHE):
        for line in open(CACHE):
            r = json.loads(line)
            c[r["key"]] = r
    return c


def n_trials():
    return len(_load_cache())


def trial(params, tag, sym=SYM, full=True, quiet=False):
    """Evaluate one configuration on IS (FP costs; full=True adds stress x1.5, gross, every-signal).
    Logged exactly once."""
    cache = _load_cache()
    k = _key(sym, params)
    if k in cache:
        r = cache[k]
        if not quiet:
            _show(r, cached=True)
        return r
    if len(cache) >= BUDGET:
        raise RuntimeError("trial budget exhausted")
    ev = r2.evaluate(sym, S.make_orders, params, full=full)
    r2.log_trial(TRACK, sym, {"_tag": tag, **{k_: (list(v) if isinstance(v, tuple) else v) for k_, v in params.items()}}, ev)
    row = {"key": k, "tag": tag, "sym": sym, "params": {k_: (list(v) if isinstance(v, tuple) else v) for k_, v in params.items()},
           "n_trial": len(cache) + 1, "ev": ev}
    with open(CACHE, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    row = json.loads(json.dumps(row, default=str))
    if not quiet:
        _show(row)
    return row


def _show(r, cached=False):
    ev = r["ev"]
    i = ev["is"]
    if i.get("n", 0) == 0:
        print(f"[{r['n_trial']:3d}] {r['tag']:<34s} n=0")
        return
    g = ev.get("is_gross", {})
    s = ev.get("is_stress", {})
    e = ev.get("is_every_signal", {})
    print(f"[{r['n_trial']:3d}] {r['tag']:<34s} n={i['n']:5d} /yr={i['trades_per_year']:6.1f} win={i['win_rate']:.3f} "
          f"expR={i['expectancy_R']:+.4f} PF={i['pf']:.3f} t={i['t_stat']:+.2f} yrs={i['years_pos']} dd={i['max_dd_R']:.1f} "
          f"L={i['long_R']:+.1f}({i['long_n']}) S={i['short_R']:+.1f}({i['short_n']}) hold={i['avg_hold_h']:.1f}h "
          f"bps={ev.get('is_bps_per_trade')} | gross PF={g.get('pf')} bps={ev.get('is_gross_bps_per_trade')} "
          f"| stress PF={s.get('pf')} | every expR={e.get('expectancy_R')}" + (" (cached)" if cached else ""), flush=True)


def by_year(r):
    return r["ev"]["is"].get("by_year_R")


if __name__ == "__main__":
    print("trials so far:", n_trials())
