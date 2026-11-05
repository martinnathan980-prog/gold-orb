"""P14: are entries/stop-outs triggered by spread spikes (Ask spike for buy-stops / short stops, Bid spike for
sell-stops / long stops) rather than by a real price move?  Touch bar spread vs the median spread of the
previous 60 minutes; R of spike-triggered trades.  IS only."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load(); idx = m1.index; ns = idx.as_unit('ns').asi8
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
t = is_part(pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/trades_base_full.pkl')).copy()
spr_c = (m1.ac - m1.bc)
med60 = spr_c.rolling(60, min_periods=20).median().shift(1).to_numpy()
ah, bh, al, bl = (m1[c].to_numpy() for c in ('ah', 'bh', 'al', 'bl'))
fi = o.loc[t.index, 'entry_i'].to_numpy()
# spread at the extreme that triggered: buy -> ask high minus bid high ; sell -> ask low minus bid low
trig_spr = np.where(t.side > 0, ah[fi] - bh[fi], al[fi] - bl[fi])
t['trig_spread_x'] = trig_spr / med60[fi]
for thr in (2, 3, 5):
    sub = t[t.trig_spread_x >= thr]
    print(f"entries whose triggering extreme had spread >= {thr}x the prior-hour median: {len(sub)}  sumR {sub.R.sum():.1f}  PF {pf(sub.R):.2f}")
# stop-outs
st = t[t.reason == 'stop']
xi = np.searchsorted(ns, pd.DatetimeIndex(st.exit_time - pd.Timedelta(minutes=1)).as_unit('ns').asi8)
stop_spr = np.where(st.side > 0, al[xi] - bl[xi], ah[xi] - bh[xi])  # long stopped on bid low; short on ask high
x = stop_spr / med60[xi]
for thr in (2, 3, 5):
    print(f"stop-outs whose triggering extreme had spread >= {thr}x prior-hour median: {int((x >= thr).sum())} of {len(st)}")
# would those stop-outs have happened on MID +- normal half spread?  (count stop-outs not confirmed by the other quote)
conf = np.where(st.side > 0, bh[xi] * 0 + (al[xi] - med60[xi] <= st.stop), (bh[xi] + med60[xi] >= st.stop))
print("stop-outs NOT confirmed by the other side +- median spread (pure spread-spike stops):", int((~conf.astype(bool)).sum()))
