"""Per-year exact-entry match of the literal EA port in MT5-like data mode (one spread value per
bar at its open; 4h mid from M5 bid + spread/2), first run as coded, versus the lab: the spread
of the yearly match rate that the user's single 2025 tester run will be judged on (README: >= 90 %).
Also the compare_journal.py style (+-4 h, same side) match rate."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ea_port import lab_trades, run  # noqa: E402
import goldlab as gl  # noqa: E402

m1 = gl.load_m1("xauusd", start="2012-12-01", end="2026-12-31")


def journal_match(lab, ea, tol_h=4.0):
    used, pairs = set(), []
    for i, r in ea.iterrows():
        d = (lab.entry_time - r.entry_time).abs()
        ok = (lab.side == r.side) & (d <= pd.Timedelta(hours=tol_h))
        cand = [k for k in lab.index[ok] if k not in used]
        if cand:
            k = min(cand, key=lambda q: d[q]); used.add(k); pairs.append((i, k))
    return len(pairs)


for y in range(2014, 2027):
    s, e = f"{y}-01-01", (f"{y+1}-01-01" if y < 2026 else "2026-10-20")
    lab = lab_trades(m1, s, e)
    ea = run(m1, s, e, mt5like=True, first_run="ea")
    exact = len(lab.merge(ea, on=["entry_time", "side"]))
    jm = journal_match(lab, ea)
    print(f"{y}: lab {len(lab):3d} ea {len(ea):3d} | exact same entry {exact/len(lab):6.1%} | "
          f"compare_journal-style match {jm/len(ea):6.1%} of EA | sumR lab {lab.R.sum():+6.1f} ea {ea.R.sum():+6.1f}")
