"""Research helpers for the crossasset track (bar cache, logging wrapper).

The cache only speeds up research: strategy.py recomputes everything from M1 frames.
"""
import gc
import json
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab.evalkit import evaluate_is, is_criteria, val_criteria  # noqa: E402,F401

CACHE = os.environ.get(
    "XA_CACHE", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/cache")
SYMS = ["xauusd", "eurusd", "gbpusd", "usdjpy", "deuidxeur", "lightcmdusd"]
RULES = {"5min": "m5", "15min": "m15", "1h": "h1", "4h": "h4", "D": "d1"}
TRACK = "crossasset"
RES = os.path.join(LAB, "results", TRACK)


def build_cache(syms=SYMS, rules=tuple(RULES)):
    os.makedirs(CACHE, exist_ok=True)
    for s in syms:
        todo = [r for r in rules if not os.path.exists(os.path.join(CACHE, f"{s}_{RULES[r]}.parquet"))]
        if not todo:
            continue
        m1 = gl.load_m1(s)
        for r in todo:
            b = gl.bars(m1, r)
            b.to_parquet(os.path.join(CACHE, f"{s}_{RULES[r]}.parquet"))
            print(s, r, len(b), flush=True)
        gl.data._cache.pop(s, None)
        del m1
        gc.collect()


def load_bars(sym, rule):
    return pd.read_parquet(os.path.join(CACHE, f"{sym}_{RULES[rule]}.parquet"))


def free_m1(sym):
    gl.data._cache.pop(sym, None)
    gc.collect()


def run_and_log(m1, orders, config, sym="xauusd", log=True, quiet=False):
    """Simulate (normal + costs x1.5), log the trial, return (trades, rep, rep_stress, crit)."""
    t, rep, rs = evaluate_is(m1, orders, sym=sym)
    if log:
        gl.log_trial(TRACK, config, rep)
    crit = is_criteria(rep, rs) if rep.get("n", 0) else {"pass": False}
    if not quiet:
        keys = ["n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R",
                "t_stat", "pf", "total_R", "max_dd_R", "years_pos", "weeks_pos_pct", "long_n", "long_R",
                "short_n", "short_R", "avg_hold_h", "max_hold_h"]
        short = {k: rep.get(k) for k in keys}
        print(json.dumps(config), "\n   ", json.dumps(short), "| stressPF", rs.get("pf"),
              "| pass" if crit.get("pass") else "| fail", flush=True)
        if "by_year_R" in rep:
            print("    by year:", rep["by_year_R"], flush=True)
    return t, rep, rs, crit


def n_trials():
    p = os.path.join(RES, "trials.jsonl")
    if not os.path.exists(p):
        return 0
    with open(p) as f:
        return sum(1 for _ in f)


if __name__ == "__main__":
    build_cache()
