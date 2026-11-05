"""P5: causality probe.  For random IS sessions with an order, rebuild orders on data truncated
  T1: just AFTER the decision bar (rows [.. fi])      -> that day's order must be identical (side, level, stop, entry ts)
  T0: just BEFORE the decision bar (rows [.. fi-1])   -> that day must have NO order yet
  T7: at 07:00 London (rows [.. i1-1], range complete, nothing after) -> no order for that day
  plus 6 full-history truncations (start of data) to rule out whole-series effects (daily ATR cache etc.)
Windowed rebuilds start 40 days before the session (the finalist uses no ATR / trend input)."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load()
idx = m1.index
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
o['ets'] = idx[o.entry_i.to_numpy()]
o['d'] = pd.to_datetime(o.date)
ois = o[o.d < '2022-01-01'].reset_index(drop=True)
rng = np.random.default_rng(7)
sample = ois.iloc[np.sort(rng.choice(len(ois), 150, replace=False))]
cols = ['side', 'level', 'stop']
res = []
for _, r in sample.iterrows():
    fi = int(r.entry_i)
    st = int(np.searchsorted(idx.values, (r.d - pd.Timedelta(days=40)).tz_localize('UTC').to_datetime64()))
    # T1
    sub = m1.iloc[st:fi + 1]
    oo = S.make_orders(sub, **P)
    oo['d'] = pd.to_datetime(oo.date); oo['ets'] = sub.index[np.clip(oo.entry_i.to_numpy(), 0, len(sub) - 1)]
    q = oo[oo.d == r.d]
    t1 = len(q) == 1 and q.iloc[0].ets == r.ets and all(np.isclose(q.iloc[0][c], r[c], atol=1e-9) for c in cols)
    # earlier orders in the window must also be identical to the full-data ones
    prevf = o[(o.d < r.d) & (o.d >= oo.d.min())].set_index('d')[cols + ['ets']]
    prevt = oo[oo.d < r.d].set_index('d')[cols + ['ets']]
    prev_same = prevf.index.equals(prevt.index) and np.allclose(prevf[cols].to_numpy(float), prevt[cols].to_numpy(float)) and (prevf.ets == prevt.ets).all()
    # T0
    sub0 = m1.iloc[st:fi]
    oo0 = S.make_orders(sub0, **P)
    t0 = (pd.to_datetime(oo0.date) == r.d).sum() == 0
    # T7: up to the 06:59 London bar
    re = pd.Timestamp(r.d.strftime('%Y-%m-%d') + ' 07:00', tz=gl.LDN).tz_convert('UTC')
    i1 = int(np.searchsorted(idx.values, re.to_datetime64()))
    oo7 = S.make_orders(m1.iloc[st:i1], **P)
    t7 = (pd.to_datetime(oo7.date) == r.d).sum() == 0
    res.append((r.d.date(), fi - i1, t1, prev_same, t0, t7))
R = pd.DataFrame(res, columns=['date', 'touch_bar_offset', 'T1_identical', 'prev_orders_identical', 'T0_no_order', 'T7_no_order'])
print(R[['T1_identical', 'prev_orders_identical', 'T0_no_order', 'T7_no_order']].mean())
print("failures:\n", R[~(R.T1_identical & R.prev_orders_identical & R.T0_no_order & R.T7_no_order)].to_string())
print("touch bar offset from 07:00 (min): ", R.touch_bar_offset.describe().round(1).to_dict())
# full-history truncations
full_ok = []
for _, r in sample.iloc[::25].iterrows():
    fi = int(r.entry_i)
    oo = S.make_orders(m1.iloc[:fi + 1], **P)
    oo['ets'] = idx[oo.entry_i.to_numpy()]
    a = o[o.entry_i <= fi].reset_index(drop=True); b = oo.reset_index(drop=True)
    same = len(a) == len(b) and (a.ets.values == b.ets.values).all() and np.allclose(a[cols].to_numpy(float), b[cols].to_numpy(float)) \
        and (a.exit_i.values[:-3] == b.exit_i.values[:-3]).all()
    full_ok.append((str(r.d.date()), len(a), len(b), bool(same)))
print("full-history truncations (date, n_full<=cut, n_trunc, identical):", full_ok)
