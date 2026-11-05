"""P0: reproduce baseline, validate the custom simulator (simulate2) against goldlab.simulate,
save orders / trades for the other probes."""
import sys
sys.path.insert(0, "/home/user/gold-orb/lab/audit/scratch/donch4h_stop/liveexec")
import numpy as np
import pandas as pd
from common import HERE, baseline, fmt, gl, is_part, simulate2, stats

m1, o, t = baseline()
print("orders", len(o), "trades", len(t))
print("IS ", fmt(stats(is_part(t))))
t2 = simulate2(m1, o, no_overlap=True, trail_mode=0)
same = (len(t2) == len(t)) and np.allclose(t2.R.to_numpy(), t.R.to_numpy(), atol=1e-12) and \
    (t2.entry_time.to_numpy() == t.entry_time.to_numpy()).all() and (t2.exit_time.to_numpy() == t.exit_time.to_numpy()).all()
print("custom simulator == engine (all 2013-2025 trades, R, entry/exit times):", same)
# every-signal parity too
te = gl.simulate(m1, o, no_overlap=False)
te2 = simulate2(m1, o, no_overlap=False, trail_mode=0)
print("every-signal parity:", len(te) == len(te2) and np.allclose(te.R.to_numpy(), te2.R.to_numpy(), atol=1e-12))
o.to_pickle(f"{HERE}/orders_base.pkl")
t.to_pickle(f"{HERE}/trades_base.pkl")
# basic facts on IS trades only (no VAL access here)
ti = is_part(t)
fi = np.searchsorted(m1.index.values, ti.entry_time.values)
arm = o.loc[ti.index, "entry_i"].to_numpy()
print("IS: fills in the first M1 bar of the bracket:", int((fi == arm).sum()), "of", len(ti))
print("IS: minutes from bracket start to fill: quantiles",
      np.percentile((pd.DatetimeIndex(ti.entry_time) - m1.index[arm]).total_seconds() / 60, [10, 25, 50, 75, 90]).round(0))
print("IS exit reasons", ti.reason.value_counts().to_dict())
