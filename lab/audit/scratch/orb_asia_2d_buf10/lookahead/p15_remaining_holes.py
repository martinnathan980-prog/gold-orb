"""P15: remaining data holes in the current (patched) gold M1: short trading days and long intraday gaps
(not containing a 17:00 NY close), with whether they fall in the strategy's range / entry window."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'audit/scratch/orb_asia_2d_buf10/lookahead')
from common import *
m1 = load(); idx = m1.index; ns = idx.as_unit('ns').asi8
cnt = pd.Series(1, index=gl.trading_day(idx)).groupby(level=0).sum()
short = cnt[cnt < 0.5 * cnt.median()]
print("trading days with < 50% of median bars:", len(short), [str(d.date()) for d in short.index][:40])
g = np.diff(ns) // 60_000_000_000
a_ny = idx[:-1].tz_convert(gl.NY); b_ny = idx[1:].tz_convert(gl.NY)
roll_a = a_ny.normalize() + pd.Timedelta(hours=17)
roll_a = roll_a.where(roll_a > a_ny, roll_a + pd.Timedelta(days=1))
expected = (roll_a <= b_ny + pd.Timedelta(minutes=1)) & (g > 1)
big = np.where((g >= 15) & ~expected)[0]
ldn = idx[big].tz_convert(gl.LDN)
df = pd.DataFrame({"gap_start_utc": idx[big], "minutes": g[big], "ldn_clock": ldn.strftime('%a %H:%M'),
                   "in_range_or_entry_window": ((ldn.hour < 12) & (ldn.dayofweek < 5))})
print(df.to_string())
