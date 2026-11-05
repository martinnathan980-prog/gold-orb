"""Descriptive statistics (IS 2013-2021 only): hour of day (London / NY local), sessions,
weekday, 'overnight vs US hours'.  Mid prices, log returns in basis points.  No costs here:
these are gross drifts to be compared with a round-trip cost of ~6 bp (spread+slippage+comm.)."""
import json

import numpy as np
import pandas as pd

from common import IS_END, IS_START, RES, Px, gl, local_times, summarize, tstat

m1 = gl.load_m1("xauusd", "2012-12-30", "2022-01-03")
px = Px(m1)
out = {}

# ---------------------------------------------------------------- hour of day
marks = pd.date_range(IS_START, IS_END, freq="1h", inclusive="left")
p0, p1 = px.at(marks, 3), px.at(marks + pd.Timedelta(hours=1), 3)
r = np.log(p1 / p0) * 1e4
yr = marks.year
rows = []
for tzname, tz in (("LDN", gl.LDN), ("NY", gl.NY)):
    hh = gl.local(marks, tz).hour
    for h in range(24):
        sel = (hh == h) & np.isfinite(r)
        if sel.sum() < 100:
            continue
        s = summarize(r[sel], yr[sel], f"{tzname} {h:02d}:00")
        s.pop("by_year")
        rows.append(s)
hours = pd.DataFrame(rows)
print("=== hour of day (gross mid log-return of the hour, bp), IS 2013-2021")
print(hours.to_string(index=False))
out["hours"] = rows

# hour-of-day by year (London clock) for stability
hh = gl.local(marks, gl.LDN).hour
tab = pd.DataFrame({"r": r, "h": hh, "y": yr}).dropna().pivot_table(index="h", columns="y", values="r", aggfunc="mean")
print("\n=== mean bp by London hour x year")
print(tab.round(1).to_string())

# ---------------------------------------------------------------- sessions
d1 = gl.bars(m1, "D")
days = d1.index[(d1.index >= "2013-01-01") & (d1.index < "2022-01-01")]
days = pd.DatetimeIndex(days)
prev = days - pd.Timedelta(days=1)  # previous CALENDAR day (Sunday for Monday): evening open 18:00 NY
def seg(t0, t1, name, tol=10):
    a, b = px.at(t0, tol), px.before(t1, tol)
    rr = np.log(b / a) * 1e4
    return rr

bounds = {
    "asia (18:00NY-1 -> 08:00LDN)": (local_times(prev, "18:00", gl.NY), local_times(days, "08:00", gl.LDN)),
    "london (08:00LDN -> 08:20NY)": (local_times(days, "08:00", gl.LDN), local_times(days, "08:20", gl.NY)),
    "us comex (08:20NY -> 13:30NY)": (local_times(days, "08:20", gl.NY), local_times(days, "13:30", gl.NY)),
    "ny late (13:30NY -> 17:00NY)": (local_times(days, "13:30", gl.NY), local_times(days, "17:00", gl.NY)),
    "full day (18:00NY-1 -> 17:00NY)": (local_times(prev, "18:00", gl.NY), local_times(days, "17:00", gl.NY)),
    "nyse hours (09:30NY -> 16:00NY)": (local_times(days, "09:30", gl.NY), local_times(days, "16:00", gl.NY)),
    "non-nyse (16:00NY-1 -> 09:30NY)": (local_times(prev, "16:00", gl.NY), local_times(days, "09:30", gl.NY)),
    "london am fix window (08:00LDN->10:30LDN)": (local_times(days, "08:00", gl.LDN), local_times(days, "10:30", gl.LDN)),
}
rows = []
sess = {}
for name, (a, b) in bounds.items():
    rr = seg(a, b, name)
    sess[name] = rr
    s = summarize(rr, days.year, name)
    rows.append(s)
print("\n=== sessions (gross bp per day), IS")
for s in rows:
    print(f"{s['label']:44s} n={s['n']:5d} mean={s['mean_bp']:+6.2f} t={s['t']:+5.2f} med={s['median_bp']:+6.2f} "
          f"wmean={s['wins_mean_bp']:+6.2f} tw={s['t_wins']:+5.2f} sd={s['sd_bp']:6.1f} hit={s['hit']:.3f} "
          f"yrs={s['yrs_same_sign']} {s['by_year']}")
out["sessions"] = rows

# ---------------------------------------------------------------- weekday (trading day close-to-close)
dc = d1["c"]
ret = np.log(dc / dc.shift(1)) * 1e4
ret = ret[(ret.index >= "2013-01-01") & (ret.index < "2022-01-01")]
rows = []
print("\n=== weekday (trading day ending 17:00 NY; close-to-close incl. weekend gap for Monday)")
for wd, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
    sel = ret.index.dayofweek == wd
    s = summarize(ret[sel].to_numpy(), ret.index[sel].year, nm)
    rows.append(s)
    print(f"{nm} n={s['n']} mean={s['mean_bp']:+6.2f} t={s['t']:+5.2f} med={s['median_bp']:+6.2f} hit={s['hit']:.3f} "
          f"yrs={s['yrs_same_sign']} {s['by_year']}")
s = summarize(ret.to_numpy(), ret.index.year, "all days")
print(f"ALL n={s['n']} mean={s['mean_bp']:+6.2f} t={s['t']:+5.2f} yrs={s['yrs_same_sign']} {s['by_year']}")
out["weekday"] = rows + [s]

# session x weekday
print("\n=== session x weekday mean bp (t)")
for name, rr in sess.items():
    line = f"{name:44s}"
    for wd, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        sel = (days.dayofweek == wd) & np.isfinite(rr)
        line += f" {nm} {np.nanmean(rr[sel]):+5.1f}({tstat(rr[sel]):+4.1f})"
    print(line)

with open(f"{RES}/desc1_hours_sessions.json", "w") as f:
    json.dump(out, f, indent=1, default=str)
