"""P5b: explain the 'prev_orders_identical' failures of P5 (window-start artefact?)."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load(); idx = m1.index
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
o['ets'] = idx[o.entry_i.to_numpy()]; o['d'] = pd.to_datetime(o.date)
cols = ['side', 'level', 'stop']
for ds in ('2013-12-03', '2016-05-24', '2020-08-11'):
    r = o[o.d == ds].iloc[0]; fi = int(r.entry_i)
    st = int(np.searchsorted(idx.values, (r.d - pd.Timedelta(days=40)).tz_localize('UTC').to_datetime64()))
    sub = m1.iloc[st:fi + 1]
    oo = S.make_orders(sub, **P); oo['d'] = pd.to_datetime(oo.date); oo['ets'] = sub.index[np.clip(oo.entry_i.to_numpy(), 0, len(sub) - 1)]
    a = o[(o.d < r.d) & (o.d >= oo.d.min())].set_index('d')[cols + ['ets']]; b = oo[oo.d < r.d].set_index('d')[cols + ['ets']]
    j = a.join(b, rsuffix='_t', how='outer')
    bad = j[~(np.isclose(j.level, j.level_t) & (j.side == j.side_t))]
    print(ds, "window start", sub.index[0], "| differing order dates:", list(bad.index.date))
    print("   after dropping the first window date, identical:",
          bool(np.allclose(a[a.index > b.index.min()][cols].to_numpy(float), b[b.index > b.index.min()][cols].to_numpy(float))))
