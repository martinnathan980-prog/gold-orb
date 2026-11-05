"""P3c: (b') truncate 2 bars after the fill and GARBLE the bar after the fill: the order for the
decision must be unchanged (side, level, stop_dist, trail, trig_i).  (a') 120 random decision bars
(not only taken trades): levels / ATR computed on data truncated at the decision == full data."""
import sys
import time

sys.path.insert(0, ".")
sys.path.insert(0, "tracks/trend")
import numpy as np
import pandas as pd

import goldlab as gl
import strategy as S

t0 = time.time()
m1 = gl.load_m1("xauusd")
P = S.FINALISTS["donch4h_stop"]
full = S.make_orders(m1, **P)
tr = pd.read_pickle("audit/scratch/donch4h_stop/lookahead/trades_is_base.pkl")
taken = full.loc[tr.index]
rng = np.random.default_rng(7)
pick = taken.iloc[np.sort(rng.choice(len(taken), 40, replace=False))]
ok_b, fails = 0, []
for _, od in pick.iterrows():
    S._bar_cache.clear()
    f = int(od.trig_i)
    sub = m1.iloc[:f + 2].copy()
    # garble the bar after the fill (and nothing else)
    for c_ in ("bh", "ah"):
        sub.iloc[-1, sub.columns.get_loc(c_)] *= 1.05
    for c_ in ("bl", "al"):
        sub.iloc[-1, sub.columns.get_loc(c_)] *= 0.95
    ob = S.make_orders(sub, **P)
    ob = ob[ob.dec_time == od.dec_time]
    good = (len(ob) == 1 and int(ob.side.iloc[0]) == int(od.side) and abs(ob.level.iloc[0] - od.level) < 1e-9
            and abs(ob.stop_dist.iloc[0] - od.stop_dist) < 1e-9 and abs(ob.trail.iloc[0] - od.trail) < 1e-9
            and int(ob.trig_i.iloc[0]) == f and int(ob.entry_i.iloc[0]) == int(od.entry_i))
    ok_b += good
    if not good:
        fails.append(str(od.dec_time))
print(f"(b') order unchanged with data cut 2 bars after the fill + garbled post-fill bar: {ok_b}/40", fails[:5])

S._bar_cache.clear()
b = S.bars_cached(m1, "4h")
ref = pd.DataFrame({"up": b["h"].rolling(60).max().to_numpy(), "dn": b["l"].rolling(60).min().to_numpy(),
                    "atr": gl.atr(b, 14).to_numpy()}, index=pd.DatetimeIndex(b["t_close"]))
tcs = pd.DatetimeIndex(b["t_close"])
ks = np.sort(rng.choice(np.arange(100, len(b) - 10), 120, replace=False))
ok_a = 0
for k in ks:
    S._bar_cache.clear()
    i0 = int(gl.entry_index(m1, tcs[k:k + 1])[0])
    sub = m1.iloc[:i0]
    bb = S.bars_cached(sub, "4h")
    v = pd.DataFrame({"up": bb["h"].rolling(60).max().to_numpy(), "dn": bb["l"].rolling(60).min().to_numpy(),
                      "atr": gl.atr(bb, 14).to_numpy()}, index=pd.DatetimeIndex(bb["t_close"]))
    a, r = v.loc[tcs[k]], ref.loc[tcs[k]]
    ok_a += bool(np.allclose(a.to_numpy(), r.to_numpy(), atol=1e-9, equal_nan=True))
print(f"(a') levels/ATR at random decisions identical on data truncated at the decision: {ok_a}/{len(ks)}")
print(f"time {time.time()-t0:.1f}s")
