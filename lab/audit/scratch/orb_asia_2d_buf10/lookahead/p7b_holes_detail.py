"""P7b: are the in-hold data holes hiding stop-outs, or is the PF of hole trades just a hold-length effect?
For every IS trade whose hold contains an unexpected gap >= 5 min: price just before/after the gap vs the stop,
in units of the trade's risk.  Control: compare R of time-exit trades with vs without holes."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load(); idx = m1.index; ns = idx.as_unit('ns').asi8
bl, ah, bc, ac, bo, ao = (m1[c].to_numpy() for c in ('bl', 'ah', 'bc', 'ac', 'bo', 'ao'))
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
t = is_part(pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/trades_base_full.pkl')).copy()
g = np.diff(ns) // 60_000_000_000
a_ny = idx[:-1].tz_convert(gl.NY); b_ny = idx[1:].tz_convert(gl.NY)
roll_a = a_ny.normalize() + pd.Timedelta(hours=17)
roll_a = roll_a.where(roll_a > a_ny, roll_a + pd.Timedelta(days=1))
expected = (roll_a <= b_ny + pd.Timedelta(minutes=1)) & (g > 1)
unexp = np.where((g >= 5) & ~expected)[0]
fi = o.loc[t.index, 'entry_i'].to_numpy()
xi = np.searchsorted(ns, pd.DatetimeIndex(t.exit_time).as_unit('ns').asi8)
rows = []
for k, (a, b) in enumerate(zip(fi, xi)):
    hs = unexp[(unexp >= a) & (unexp < b - 1)]
    r = t.iloc[k]
    for h in hs:
        # distance to stop (in R) from the worst quote of the bar before and the bar after the hole
        if r.side > 0:
            d_before = (min(bl[h], bc[h]) - r.stop) / r.risk; d_after = (bl[h + 1] - r.stop) / r.risk
        else:
            d_before = (r.stop - max(ah[h], ac[h])) / r.risk; d_after = (r.stop - ah[h + 1]) / r.risk
        rows.append({"trade": t.index[k], "date": r.date, "side": int(r.side), "R": round(r.R, 2), "reason": r.reason,
                     "gap_start_utc": idx[h], "gap_min": int(g[h]), "dist_stop_before_R": round(d_before, 2), "dist_stop_after_R": round(d_after, 2)})
H = pd.DataFrame(rows)
pd.set_option('display.width', 220)
print("holes inside IS holds:", len(H), "in", H.trade.nunique(), "trades")
print("gap minutes distribution:", H.gap_min.describe().round(1).to_dict())
close = H[(H[['dist_stop_before_R', 'dist_stop_after_R']].min(axis=1) < 0.25)]
print("holes where price was within 0.25R of the stop at either edge:", len(close))
print(close.to_string())
print("largest holes (>=30 min):\n", H[H.gap_min >= 30].to_string())
# control by hold: time-exit trades with vs without holes
t['has_hole'] = t.index.isin(H.trade)
for rs in ('time', 'stop'):
    a = t[(t.reason == rs) & t.has_hole]; b = t[(t.reason == rs) & ~t.has_hole]
    print(f"{rs}-exit trades: with hole n={len(a)} meanR={a.R.mean():.3f} | without n={len(b)} meanR={b.R.mean():.3f}")
print("share of time exits among trades with holes:", round((t[t.has_hole].reason == 'time').mean(), 3), " vs without:", round((t[~t.has_hole].reason == 'time').mean(), 3))
print("mean hold (h) with holes:", round(t[t.has_hole].hold_min.mean() / 60, 1), " without:", round(t[~t.has_hole].hold_min.mean() / 60, 1))
H.to_csv('audit/scratch/orb_asia_2d_buf10/lookahead/p7b_holes_in_holds.csv', index=False)
