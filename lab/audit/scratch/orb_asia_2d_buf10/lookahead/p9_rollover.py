"""P9: rollover-window spread fidelity.  Retail MT5 gold spreads typically blow out around the 17:00 NY
rollover / 18:00 NY reopen (and at the Sunday open); Dukascopy's own quotes may not.  Every 2-day hold spans
>= 1 rollover.  (a) Dukascopy spread profile by NY clock; (b) sensitivity: spread x3 and +$1.0 (each side
+-$0.5) only in 16:55-18:30 NY (and the first 30 min after the Sunday open), stops/fills re-simulated.  IS only."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load(); idx = m1.index
ny = idx.tz_convert(gl.NY); hm = ny.hour * 60 + ny.minute
spr = (m1.ac - m1.bc).to_numpy()
yr = ny.year
for y in (2015, 2019, 2021, 2024):
    sel = yr == y
    prof = pd.Series(spr[sel]).groupby(pd.Series(hm[sel] // 15 * 15)).median()
    pick = {f"{h // 60:02d}:{h % 60:02d}": round(prof.get(h, np.nan), 3) for h in (2*60, 3*60, 8*60, 12*60, 16*60, 16*60+45, 18*60, 18*60+15, 18*60+30, 20*60)}
    print(y, "median spread by NY clock:", pick)
o = pd.read_pickle('audit/scratch/orb_asia_2d_buf10/lookahead/orders_base.pkl')
base = is_part(gl.simulate(m1, o))
print("base IS:", summ(base))
# rollover window mask (incl. the Sunday reopen, which is also 18:00 NY)
win = ((hm >= 16 * 60 + 55) | (hm < 0)) & (hm <= 18 * 60 + 30)
win = win.to_numpy() if hasattr(win, 'to_numpy') else win
for nm, mult, add in (("x3 in rollover window", 3.0, 0.0), ("+$1.0 in rollover window", 1.0, 1.0), ("+$2.0 in rollover window", 1.0, 2.0)):
    m2 = m1.copy()
    half = np.where(win, (spr * (mult - 1) + add) / 2, 0.0)
    for c in ('bo', 'bh', 'bl', 'bc'):
        m2[c] = m2[c].to_numpy() - half
    for c in ('ao', 'ah', 'al', 'ac'):
        m2[c] = m2[c].to_numpy() + half
    t2 = is_part(gl.simulate(m2, o))
    n_roll_stops = int(((t2.reason == 'stop') & pd.Series(win[np.searchsorted(idx.values, (t2.exit_time - pd.Timedelta(minutes=1)).values)], index=t2.index)).sum())
    print(nm, summ(t2), "| stop-outs inside the window:", n_roll_stops, flush=True)
    del m2
n_base_roll = int(((base.reason == 'stop') & pd.Series(win[np.searchsorted(idx.values, (base.exit_time - pd.Timedelta(minutes=1)).values)], index=base.index)).sum())
print("base stop-outs inside the window:", n_base_roll)
