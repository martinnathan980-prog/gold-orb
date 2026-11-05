"""Descriptive (IS only): FOMC statement days (14:00 NY) and NFP days (08:30 NY). Mid, bp."""
import numpy as np, pandas as pd
from common import IS_END, IS_START, RES, Px, gl, local_times, summarize, tstat
from calendars import FOMC, NFP

m1 = gl.load_m1("xauusd", "2012-12-30", "2022-01-03")
px = Px(m1)

def line(label, r, yrs):
    s = summarize(r, yrs, label)
    return (f"{label:44s} n={s['n']:4d} mean={s['mean_bp']:+7.2f} t={s['t']:+5.2f} med={s['median_bp']:+7.2f} "
            f"sd={s['sd_bp']:6.1f} hit={s['hit']:.2f} yrs={s['yrs_same_sign']} {s['by_year']}")

def w(dd0, t0, dd1, t1, tz=gl.NY, tol=5):
    a = px.at(local_times(dd0, t0, tz), tol)
    b = px.at(local_times(dd1, t1, tz), tol)
    return np.log(b / a) * 1e4

fo = pd.DatetimeIndex(FOMC[(FOMC >= "2013-01-01") & (FOMC < "2022-01-01")])
prev = fo - pd.offsets.BDay(1)
nxt = fo + pd.offsets.BDay(1)
print(f"=== FOMC statement days (14:00 NY), n={len(fo)}")
for lab, r in (("D-1 14:00 -> D 13:55 (pre-FOMC 24h)", w(prev, "14:00", fo, "13:55")),
               ("D 08:00 -> D 13:55", w(fo, "08:00", fo, "13:55")),
               ("D 13:55 -> D 14:30", w(fo, "13:55", fo, "14:30")),
               ("D 14:30 -> D 16:45", w(fo, "14:30", fo, "16:45")),
               ("D 13:55 -> D 16:45", w(fo, "13:55", fo, "16:45")),
               ("D 16:45 -> D+1 16:45", w(fo, "16:45", nxt, "16:45")),
               ("D-1 16:45 -> D+1 16:45 (2 days)", w(prev, "16:45", nxt, "16:45"))):
    print(line(lab, r, fo.year))
# reversal / continuation of the initial reaction
r0 = w(fo, "13:55", fo, "14:30"); r1 = w(fo, "14:30", fo, "16:45"); r2 = w(fo, "14:30", nxt, "16:45")
print(f"  corr(initial 13:55-14:30, 14:30-16:45) = {pd.Series(r0).corr(pd.Series(r1)):+.3f}; "
      f"fade-direction mean 14:30->16:45 {np.nanmean(-np.sign(r0) * r1):+.2f} (t {tstat(-np.sign(r0) * r1):+.2f}); "
      f"to D+1 16:45 {np.nanmean(-np.sign(r0) * r2):+.2f} (t {tstat(-np.sign(r0) * r2):+.2f})")

nf = pd.DatetimeIndex(NFP[(NFP >= "2013-01-01") & (NFP < "2022-01-01")])
nprev = nf - pd.offsets.BDay(1)
print(f"\n=== NFP release days (08:30 NY), n={len(nf)}")
for lab, r in (("D-1 16:45 -> D 08:25 (pre)", w(nprev, "16:45", nf, "08:25")),
               ("D 07:00 -> D 08:25", w(nf, "07:00", nf, "08:25")),
               ("D 08:25 -> D 08:45 (reaction)", w(nf, "08:25", nf, "08:45")),
               ("D 08:45 -> D 10:00", w(nf, "08:45", nf, "10:00")),
               ("D 08:45 -> D 16:45", w(nf, "08:45", nf, "16:45")),
               ("D 10:00 -> D 16:45", w(nf, "10:00", nf, "16:45")),
               ("D 13:30 -> D 16:45", w(nf, "13:30", nf, "16:45"))):
    print(line(lab, r, nf.year))
r0 = w(nf, "08:25", nf, "08:45"); r1 = w(nf, "08:45", nf, "16:45"); r2 = w(nf, "08:45", nf, "10:00")
big = np.abs(r0) > np.nanpercentile(np.abs(r0), 50)
for nm, sel in (("all", np.isfinite(r0)), ("|reaction| top half", big)):
    f1 = -np.sign(r0[sel]) * r1[sel]; f2 = -np.sign(r0[sel]) * r2[sel]
    print(f"  {nm:20s} fade-direction 08:45->16:45 {np.nanmean(f1):+.2f} (t {tstat(f1):+.2f}) | 08:45->10:00 {np.nanmean(f2):+.2f} (t {tstat(f2):+.2f}) n={sel.sum()}")
print(f"  mean |reaction| 08:25->08:45 = {np.nanmean(np.abs(r0)):.1f} bp")

# Non-NFP Fridays vs NFP Fridays afternoon (link with the Friday effect)
d1 = gl.bars(m1, "D")
days = pd.DatetimeIndex(d1.index[(d1.index >= "2013-01-01") & (d1.index < "2022-01-01")])
fr = days[days.dayofweek == 4]
isn = fr.isin(nf)
r = w(fr, "13:30", fr, "16:45")
print(f"\nFriday 13:30->16:45: NFP Fridays {np.nanmean(r[isn]):+.2f} (t {tstat(r[isn]):+.2f}, n {isn.sum()}) | "
      f"non-NFP Fridays {np.nanmean(r[~isn]):+.2f} (t {tstat(r[~isn]):+.2f}, n {(~isn).sum()})")
