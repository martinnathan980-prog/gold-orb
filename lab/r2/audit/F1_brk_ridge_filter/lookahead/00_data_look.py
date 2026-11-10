import sys, os
sys.path.insert(0, '/home/user/gold-orb/lab')
import numpy as np, pandas as pd
import goldlab as gl
from goldlab import r2
for sym in ["btcusd", "ethusd"]:
    m1 = r2.load(sym)
    print(sym, len(m1), m1.index[0], m1.index[-1], m1.index.dtype, m1.index.unit, m1.index.is_monotonic_increasing, m1.index.is_unique)
    print(m1.dtypes.to_dict())
    print(m1.head(3)); print(m1.tail(3))
    # bars per year
    print("bars/year", m1.groupby(m1.index.year).size().to_dict())
    # spread
    spr = (m1.ac - m1.bc); mid = (m1.ac + m1.bc)/2
    print("spread bp by year", (spr/mid*1e4).groupby(m1.index.year).median().round(2).to_dict())
    print("spread bp quantiles", (spr/mid*1e4).quantile([0.01,0.25,0.5,0.75,0.99,0.999]).round(2).to_dict())
    # weekday distribution
    ny = m1.index.tz_convert("America/New_York")
    print("bars by NY dow", pd.Series(ny.dayofweek).value_counts().sort_index().to_dict())
    # gaps
    d = np.diff(m1.index.asi8) / (60 * 10**9 if m1.index.unit == 'ns' else 60 * {'us':10**6,'ms':10**3,'s':1}[m1.index.unit])
    print("gap minutes quantiles", np.quantile(d, [0.5, 0.9, 0.99, 0.999, 1.0]))
    big = np.flatnonzero(d > 30)
    print("gaps > 30 min:", len(big), " > 240:", int((d > 240).sum()), " > 1440:", int((d>1440).sum()))
    yrs = m1.index.year.to_numpy()[big]
    print("gaps>30 by year", pd.Series(yrs).value_counts().sort_index().to_dict())
    # anomalies: bh<bl, bo outside, ask<bid
    print("bh<bl", int((m1.bh < m1.bl).sum()), "ask<bid close", int((m1.ac < m1.bc).sum()), "ao<bo", int((m1.ao < m1.bo).sum()),
          "bo>bh", int((m1.bo > m1.bh + 1e-9).sum()), "bo<bl", int((m1.bo < m1.bl - 1e-9).sum()),
          "ah<bh", int((m1.ah < m1.bh).sum()), "al<bl", int((m1.al < m1.bl).sum()))
    r2.free()
