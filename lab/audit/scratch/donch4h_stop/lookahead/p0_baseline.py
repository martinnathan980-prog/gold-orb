"""P0: reproduce the finalist on IS (no VAL access) and cache orders + IS trades for later probes."""
import os
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "tracks/trend")
import numpy as np
import pandas as pd

import goldlab as gl
import strategy as S

OUT = "audit/scratch/donch4h_stop/lookahead"
t0 = time.time()
m1 = gl.load_m1("xauusd")
print("m1", m1.shape, m1.index[0], m1.index[-1], f"{time.time()-t0:.1f}s")
# basic data sanity
idx = m1.index
print("monotonic", idx.is_monotonic_increasing, "unique", idx.is_unique,
      "non-minute stamps", int((idx.second != 0).sum() + (idx.microsecond != 0).sum()))
print("NaNs", int(m1.isna().sum().sum()))
spr = m1.ac - m1.bc
print("neg spread close", int((spr < 0).sum()), "ask_high<bid_high", int((m1.ah < m1.bh).sum()),
      "ask_low<bid_low", int((m1.al < m1.bl).sum()))
print("bar internal consistency: bh<max(bo,bc)", int((m1.bh < np.maximum(m1.bo, m1.bc) - 1e-9).sum()),
      "bl>min(bo,bc)", int((m1.bl > np.minimum(m1.bo, m1.bc) + 1e-9).sum()),
      "ah<max(ao,ac)", int((m1.ah < np.maximum(m1.ao, m1.ac) - 1e-9).sum()),
      "al>min(ao,ac)", int((m1.al > np.minimum(m1.ao, m1.ac) + 1e-9).sum()))
p = S.FINALISTS["donch4h_stop"]
t1 = time.time()
o = S.make_orders(m1, **p)
print("orders", len(o), f"{time.time()-t1:.1f}s")
t = gl.simulate(m1, o, no_overlap=True)
ti = gl.cut(t, "is")
r = gl.report(ti)
print({k: r[k] for k in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "long_R", "short_R", "max_hold_h")})
o.to_pickle(f"{OUT}/orders_base.pkl")
ti.to_pickle(f"{OUT}/trades_is_base.pkl")
# order / trade internal consistency on IS
oo = o.loc[ti.index]
print("fill bar == trig_i (IS):", bool((m1.index.get_indexer(ti.entry_time) == oo.trig_i.to_numpy()).all()))
print("both-sides-same-bar ties among all orders:", "n/a (computed in p1)")
print("total", f"{time.time()-t0:.1f}s")
