"""P7: data holes, holidays, ties, gap fills (IS trades only).
 (a) unexpected gaps (not containing a 17:00 NY daily/weekend/holiday close) inside each trade's holding period
 (b) traded sessions with incomplete Asian range
 (c) time exits that happened late (scheduled 16:00 NY falls in a closed market: holidays / early closes)
 (d) longest holds
 (e) both levels touched in the first-touch bar; touch-bar gap fills (open already beyond the level)"""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load(); idx = m1.index; ns = idx.as_unit('ns').asi8
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
T = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/trades_base_full.pkl')
t = is_part(T).copy()
# ---- gaps
g = np.diff(ns) // 60_000_000_000
a_ny = idx[:-1].tz_convert(gl.NY); b_ny = idx[1:].tz_convert(gl.NY)
# a gap "contains" a 17:00 NY close if the 17:00 NY of a's date (or the next) lies in (a, b]
roll_a = a_ny.normalize() + pd.Timedelta(hours=17)
roll_a = roll_a.where(roll_a > a_ny, roll_a + pd.Timedelta(days=1))
expected = (roll_a <= b_ny + pd.Timedelta(minutes=1)) & (g > 1)
unexp = (g >= 5) & ~expected
gpos = np.where(unexp)[0]  # gap between bar gpos and gpos+1
gmin = g[gpos]
print("unexpected gaps >=5 min in whole data:", len(gpos), " >=15:", int((gmin >= 15).sum()), " >=60:", int((gmin >= 60).sum()))
fi = o.loc[t.index, 'entry_i'].to_numpy()
xi = np.searchsorted(ns, pd.DatetimeIndex(t.exit_time).as_unit('ns').asi8)
hole_min = np.zeros(len(t)); hole_n = np.zeros(len(t), int)
cs = np.r_[0, np.cumsum(np.where(unexp, g - 1, 0))]
for k in range(len(t)):
    lo, hi = fi[k], max(xi[k] - 1, fi[k])
    hole_min[k] = cs[hi] - cs[lo]
t['hole_min'] = hole_min
for thr in (5, 15, 60):
    sub = t[t.hole_min >= thr]
    print(f"IS trades with >= {thr} unexpected missing minutes during the hold: {len(sub)}  sumR {sub.R.sum():.1f}  PF {pf(sub.R):.3f}")
clean = t[t.hole_min < 15]
print("IS PF excluding trades with >=15 hole-minutes:", summ(clean))
# ---- (b) incomplete ranges
PP = dict(S.DEFAULTS); PP.update(P)
s = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/sessions.pkl')
s['d'] = pd.to_datetime(s.date)
t['d'] = pd.to_datetime(t.date)
tt = t.merge(s[['d', 'nbars', 'nent']], on='d', how='left')
for thr in (400, 380):
    sub = tt[tt.nbars < thr]
    print(f"IS trades whose range had < {thr}/420 bars: {len(sub)} sumR {sub.R.sum():.1f}")
# ---- (c) late time exits
sched = pd.DatetimeIndex(s.set_index('d').loc[t.d, 't_x'])
t['sched_x'] = sched
late = t[(t.reason == 'time') & (t.exit_time > t.sched_x + pd.Timedelta(minutes=30))].copy()
late['late_h'] = (late.exit_time - late.sched_x).dt.total_seconds() / 3600
print(f"IS time exits later than scheduled (+30min): {len(late)}  sumR {late.R.sum():.2f}")
print(late[['date', 'side', 'sched_x', 'exit_time', 'late_h', 'R', 'swap']].round(2).to_string())
# what would 'exit at the last bar before the scheduled time' give for those?
bc, ac = m1.bc.to_numpy(), m1.ac.to_numpy()
alt = []
for k, r in late.iterrows():
    j = int(np.searchsorted(ns, pd.Timestamp(r.sched_x).as_unit('ns').value)) - 1
    px = bc[j] * (1 - 1.5e-4) if r.side > 0 else ac[j] * (1 + 1.5e-4)
    pnl = r.side * (px - r.entry) - 0.07 - r.swap * 0  # ignore swap diff (fewer nights) -> conservative upper bound below
    alt.append(pnl / r.risk)
if len(late):
    print("R if closed at the last quote before the scheduled time (pre-holiday close):", np.round(alt, 2), "sum", round(float(np.sum(alt)), 2))
# ---- (d) longest holds
print("longest holds (h):\n", t.nlargest(6, 'hold_min')[['date', 'side', 'entry_time', 'exit_time', 'reason', 'R']].assign(h=t.hold_min / 60).to_string())
# ---- (e) ties and gap fills
ah, bl, ao, bo = (m1[c].to_numpy() for c in ('ah', 'bl', 'ao', 'bo'))
oo = o.loc[t.index]
lv = oo.level.to_numpy(); st = oo.stop.to_numpy(); sd = oo.side.to_numpy()
buy = np.where(sd > 0, lv, st); sell = np.where(sd > 0, st, lv)
both = (ah[fi] >= buy) & (bl[fi] <= sell)
gapfill = np.where(sd > 0, ao[fi] > lv, bo[fi] < lv)
print("IS trades with both levels touched in the touch bar:", int(both.sum()), "| touch-bar gap fills (open beyond level):", int(gapfill.sum()))
first_bar = (fi == s.set_index('d').loc[t.d, 'i1'].to_numpy())
print("IS trades triggered in the very first bar (07:00 London):", int(first_bar.sum()), " sumR", round(t.R[first_bar].sum(), 1),
      "| of which gap fills", int((first_bar & gapfill).sum()))
print("reasons:", t.reason.value_counts().to_dict())
