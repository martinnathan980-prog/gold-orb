"""Check the Friday-afternoon drift (IS only): by NY hour, bid vs ask, end-time sensitivity, spreads."""
import numpy as np, pandas as pd
from common import IS_END, IS_START, RES, Px, gl, local_times, summarize, tstat

m1 = gl.load_m1("xauusd", "2012-12-30", "2022-01-03")
px = Px(m1)
d1 = gl.bars(m1, "D")
days = pd.DatetimeIndex(d1.index[(d1.index >= "2013-01-01") & (d1.index < "2022-01-01")])
ns = px.ns
def p_at(times, col, tol=5):
    t = pd.DatetimeIndex(times).tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)
    i = np.searchsorted(ns, t, "left"); ok = i < len(ns); ii = np.where(ok, i, 0)
    good = ok & ((ns[ii] - t) <= tol * 60e9)
    out = np.full(len(t), np.nan); out[good] = m1[col].to_numpy()[ii[good]]; return out
def p_before(times, col, tol=5):
    t = pd.DatetimeIndex(times).tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)
    j = np.searchsorted(ns, t, "left") - 1; ok = j >= 0; jj = np.where(ok, j, 0)
    good = ok & ((t - ns[jj]) <= (tol + 1) * 60e9)
    out = np.full(len(t), np.nan); out[good] = m1[col].to_numpy()[jj[good]]; return out

print("=== weekday x NY hour (12..16) mean bp (t), mid, hour = [h:00, h+1:00)")
for wd, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
    dd = days[days.dayofweek == wd]
    line = nm
    for h in range(8, 17):
        a = px.at(local_times(dd, f"{h:02d}:00", gl.NY), 3)
        b = px.before(local_times(dd, f"{h+1:02d}:00", gl.NY), 3) if h < 16 else px.before(local_times(dd, "17:00", gl.NY), 3)
        r = np.log(b / a) * 1e4
        line += f" | {h:02d}h {np.nanmean(r):+5.1f}({tstat(r):+4.1f})"
    print(line)

fr = days[days.dayofweek == 4]
print("\n=== Friday windows: mid / bid-only / ask-only")
for t0, t1 in [("13:30", "17:00"), ("13:30", "16:55"), ("13:30", "16:45"), ("13:30", "16:30"), ("13:30", "16:00"),
               ("12:00", "16:00"), ("14:00", "16:30"), ("15:00", "16:55"), ("16:00", "16:55"), ("16:30", "16:59"), ("16:50", "17:00")]:
    A, B = local_times(fr, t0, gl.NY), local_times(fr, t1, gl.NY)
    res = []
    for col_a, col_b in (("mid", "mid"), ("bo", "bc"), ("ao", "ac"), ("ao", "bc")):
        if col_a == "mid":
            a, b = px.at(A, 5), px.before(B, 5)
        else:
            a, b = p_at(A, col_a), p_before(B, col_b)
        r = np.log(b / a) * 1e4
        res.append(f"{col_a}->{col_b}: {np.nanmean(r):+5.2f} (t {tstat(r):+4.1f}, n {np.isfinite(r).sum()})")
    s = summarize(np.log(px.before(B, 5) / px.at(A, 5)) * 1e4, fr.year)
    print(f"Fri {t0}->{t1}  " + " | ".join(res) + f" | yrs {s['yrs_same_sign']} {s['by_year']}")

# spreads by minute near the Friday close vs other days
ny = gl.local(m1.index, gl.NY)
spr = (m1.ac - m1.bc).to_numpy()
mins = ny.hour * 60 + ny.minute
isf = (ny.dayofweek == 4)
ism = (m1.index >= IS_START) & (m1.index < IS_END)
print("\n=== median spread ($) by NY minute, Fri vs Mon-Thu (IS)")
for mm in [13*60+30, 15*60, 16*60, 16*60+30, 16*60+45, 16*60+50, 16*60+55, 16*60+57, 16*60+58, 16*60+59]:
    a = np.median(spr[ism & isf & (mins == mm)]); b = np.median(spr[ism & ~isf & (mins == mm)])
    print(f"{mm//60:02d}:{mm%60:02d}  Fri {a:.3f}  Mon-Thu {b:.3f}")
# last bar of the week: how late?
last = pd.Series(m1.index[ism & isf]).groupby(pd.Series(m1.index[ism & isf]).dt.tz_convert(gl.NY).dt.date).max()
lm = last.dt.tz_convert(gl.NY)
print("\nlast Friday bar NY time distribution:", (lm.dt.hour * 60 + lm.dt.minute).value_counts().head(8).to_dict())
