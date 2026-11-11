"""Causality: orders built on frames cut at random times equal the full-frame orders up to the cut
(orders whose scheduled exit is before the cut; end-of-file exits are excluded)."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import strategy as S
CFGS = [dict(family="fix", dec="16:00", look_min=60, exit="16:30", monthend_n=1, stop_atr=1.5),
        dict(family="fix", monthend_n=0, look_min=120, exit="17:00"),
        dict(family="tod", start="07:00", end="12:00", dir="usd_long", stop_atr=2.0, pair="eurusd"),
        dict(family="ldnbrk")]
COLS = ["entry_i", "side", "etype", "level", "stop", "stop_dist", "exit_i"]
res = []
rng = np.random.default_rng(7)
for sym in ("eurusd", "usdjpy"):
    m1 = C.load_is(sym)
    m1 = m1[m1.index < pd.Timestamp("2022-01-01", tz="UTC")]
    cuts = np.sort(rng.integers(len(m1) // 10, len(m1) - 10, 6))
    for p in CFGS:
        full = S.make_orders(m1, **p)
        for c in cuts:
            T = m1.index[c]
            sub = S.make_orders(m1.iloc[:c], **p)
            f = full[full.sched_exit < T - pd.Timedelta(minutes=1)][COLS].reset_index(drop=True)
            s = sub[sub.sched_exit < T - pd.Timedelta(minutes=1)][COLS].reset_index(drop=True)
            same = len(f) == len(s) and bool(np.allclose(f.fillna(-9).to_numpy(float), s.fillna(-9).to_numpy(float), rtol=0, atol=1e-12))
            res.append({"sym": sym, "family": p["family"], "cut": str(T), "n": len(f), "identical": same})
            if not same:
                print("MISMATCH", sym, p, T, len(f), len(s))
print(sum(r["identical"] for r in res), "of", len(res), "identical")
C.save(res, "truncation_test.json")
