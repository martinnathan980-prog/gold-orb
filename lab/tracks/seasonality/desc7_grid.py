"""Full weekday x hour grid (London clock and NY clock), IS: multiple-testing view."""
import numpy as np, pandas as pd
from common import IS_END, IS_START, Px, gl, tstat

m1 = gl.load_m1("xauusd", "2012-12-30", "2022-01-03")
px = Px(m1)
marks = pd.date_range(IS_START, IS_END, freq="1h", inclusive="left")
r = np.log(px.at(marks + pd.Timedelta(hours=1), 3) / px.at(marks, 3)) * 1e4
for tzn, tz in (("London", gl.LDN), ("NY", gl.NY)):
    loc = gl.local(marks, tz)
    # weekday of the TRADING day (17:00 NY boundary) so Sunday evening counts as Monday
    tdw = gl.trading_day(marks).dayofweek
    df = pd.DataFrame({"r": r, "h": loc.hour, "d": tdw, "y": marks.year}).dropna()
    df = df[df.d < 5]
    g = df.groupby(["h", "d"])["r"]
    mean = g.mean().unstack(); t = g.apply(tstat).unstack()
    yrs = df.groupby(["h", "d", "y"])["r"].mean().unstack()
    same = (np.sign(yrs).eq(np.sign(df.groupby(["h", "d"])["r"].mean()), axis=0)).sum(axis=1).unstack()
    print(f"=== {tzn} clock: mean bp (t) [years same sign] by hour x trading-weekday; * = |t|>3")
    for h in mean.index:
        cells = []
        for d in range(5):
            if d in mean.columns and np.isfinite(mean.loc[h, d]):
                star = "*" if abs(t.loc[h, d]) > 3 else " "
                cells.append(f"{mean.loc[h, d]:+5.1f}({t.loc[h, d]:+4.1f})[{int(same.loc[h, d])}]{star}")
            else:
                cells.append(" " * 20)
        print(f"{h:02d}h " + " ".join(cells))
    tt = t.to_numpy().ravel(); tt = tt[np.isfinite(tt)]
    print(f"cells={len(tt)}  |t|>2: {(np.abs(tt) > 2).sum()} (exp. {0.0455 * len(tt):.1f} under null)  |t|>3: {(np.abs(tt) > 3).sum()} (exp. {0.0027 * len(tt):.2f})\n")
