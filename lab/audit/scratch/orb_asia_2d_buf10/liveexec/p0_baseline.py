"""P0: baseline reproduction on the current (patched) data + check of the level-rebuild helper."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

t0 = time.time()
m1, o, t = baseline()
print(f"orders {len(o)} trades {len(t)} skipped {t.attrs['skipped']} ({time.time()-t0:.1f}s)")
ti = is_part(t)
print("IS  ", fmt(stats(ti)))
# helper reproduces make_orders?
s, p = finalist_sessions(m1)
buf = p["buf_frac"] * s.width.to_numpy()
o2 = orders_from_levels(m1, s, s.hi.to_numpy() + buf, s.lo.to_numpy() - buf)
same = (len(o2) == len(o)) and all(np.allclose(o2[c].to_numpy(float), o[c].to_numpy(float), equal_nan=True)
                                   for c in ("entry_i", "side", "level", "stop", "exit_i"))
print("orders_from_levels reproduces make_orders:", same)
tv = val_part(t, "baseline-current-data")
print("VAL ", fmt(stats(tv)))
o.to_pickle(os.path.join(HERE, "orders_base.pkl"))
t.to_pickle(os.path.join(HERE, "trades_base.pkl"))
# quick facts used later
loc = t.entry_time.dt.tz_convert(PARIS)
print("entry hour Paris (all years):", loc.dt.hour.value_counts().sort_index().to_dict())
print("exit reasons:", t.reason.value_counts().to_dict())
xt = t[t.reason == "time"].exit_time.dt.tz_convert(gl.NY)
print("time exits not at 16:00 NY:", int(((xt.dt.hour != 16) | (xt.dt.minute != 0)).sum()), "of", len(xt))
