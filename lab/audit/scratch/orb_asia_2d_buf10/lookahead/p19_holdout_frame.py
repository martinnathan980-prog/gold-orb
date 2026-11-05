"""P19: holdout.py builds orders on a frame that starts 2025-06-01 (warm-up) + 2026 data.  Check that a frame
starting 2025-06-01 yields exactly the same orders/trades as the full history for the overlapping dates
(equality only, no performance printed; VAL-period trades accessed through one logged cut)."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load()
sub = gl.load_m1("xauusd", start="2025-06-01")
of = S.make_orders(m1, **P); os_ = S.make_orders(sub, **P)
of['d'] = pd.to_datetime(of.date); os_['d'] = pd.to_datetime(os_.date)
a = of[of.d >= '2025-06-02'].reset_index(drop=True); b = os_[os_.d >= '2025-06-02'].reset_index(drop=True)
same_orders = len(a) == len(b) and np.allclose(a[['side', 'level', 'stop']].to_numpy(float), b[['side', 'level', 'stop']].to_numpy(float)) \
    and (m1.index[a.entry_i.to_numpy()] == sub.index[b.entry_i.to_numpy()]).all()
tf = gl.simulate(m1, of); ts = gl.simulate(sub, os_)
both = pd.concat([tf.assign(src='full'), ts.assign(src='sub')])
v = gl.cut(both, "val", track="review", label=vlabel("holdout-frame-equivalence(2025-06 warm-up start)"))
x = v[(v.src == 'full') & (v.entry_time >= '2025-06-02')].set_index('entry_time'); y = v[v.src == 'sub'].set_index('entry_time')
print("orders identical:", same_orders, "| trades identical:", x.index.equals(y.index) and np.allclose(x.R, y.R))
onlyx = x.index.difference(y.index); onlyy = y.index.difference(x.index)
com = x.index.intersection(y.index)
dR = (x.loc[com, 'R'] - y.loc[com, 'R']).abs()
print("only-full:", list(onlyx), "\nonly-sub:", list(onlyy))
print("common", len(com), "R mismatches", int((dR > 1e-9).sum()), "| last divergence:", max(list(onlyx) + list(onlyy)) if len(onlyx) + len(onlyy) else None)
