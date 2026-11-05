"""Checker fix check: start the lab FLAT at the EA's first LEVELS time (first decision after the
first-run bucket skip) -> start-up mismatches disappear?"""
import os, sys
import numpy as np
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ea_port import compare, lab_trades, run  # noqa: E402
import goldlab as gl  # noqa: E402
m1 = gl.load_m1("xauusd", start="2012-12-01", end="2026-12-31")
for y in range(2014, 2026):
    s, e = f"{y}-01-01", f"{y+1}-01-01"
    t0 = m1.index[m1.index.searchsorted(pd.Timestamp(s, tz="UTC"))]
    first_levels = t0.floor("4h") + pd.Timedelta(hours=4)        # EA skips the bucket of its first bar
    first_levels = m1.index[m1.index.searchsorted(first_levels)].floor("4h")
    ea = run(m1, s, e, first_run="ea")
    un = compare(lab_trades(m1, s, e, flat_from=first_levels), ea, f"{y}: lab flat from first LEVELS {first_levels:%m-%d %H:%M}")
    if len(un):
        print(un[["entry_time", "side", "_merge", "R_lab", "R_ea"]].to_string())
