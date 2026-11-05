"""Mechanism check (IS only): Friday 13:30->16:45 NY drift in other instruments (bid-only data, mid = bid+fixed/2)."""
import numpy as np, pandas as pd
from common import Px, gl, local_times, summarize, tstat

for sym in ("xauusd", "eurusd", "usdjpy", "deuidxeur", "lightcmdusd"):
    m = gl.load_m1(sym, "2012-12-30", "2022-01-03")
    px = Px(m)
    d1 = gl.bars(m, "D")
    days = pd.DatetimeIndex(d1.index[(d1.index >= "2013-01-01") & (d1.index < "2022-01-01")])
    out = []
    for wd, nm in ((4, "Fri"), (None, "Mon-Thu")):
        dd = days[days.dayofweek == 4] if wd == 4 else days[days.dayofweek < 4]
        r = np.log(px.at(local_times(dd, "16:45", gl.NY), 5) / px.at(local_times(dd, "13:30", gl.NY), 5)) * 1e4
        s = summarize(r, dd.year)
        out.append(f"{nm} {s['mean_bp']:+5.2f} (t {s['t']:+4.1f}, n {s['n']}, yrs {s['yrs_same_sign']})")
    print(f"{sym:12s} 13:30->16:45 NY: " + " | ".join(out))
    del m, px, d1
    gl.data._cache.clear()
