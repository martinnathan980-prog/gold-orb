"""Friday afternoon + weekend gap, deeper (IS only)."""
import numpy as np, pandas as pd
from common import IS_END, IS_START, RES, Px, gl, local_times, summarize, tstat

m1 = gl.load_m1("xauusd", "2012-12-30", "2022-01-03")
px = Px(m1)
d1 = gl.bars(m1, "D")
days = pd.DatetimeIndex(d1.index[(d1.index >= "2013-01-01") & (d1.index < "2022-01-01")])
fr = days[days.dayofweek == 4]
th = days[days.dayofweek == 3]

# cumulative mean path on Fridays vs other days from 08:00 NY in 15-min steps (mid)
print("=== mean cumulative mid return from 12:00 NY (bp), Fridays vs Mon-Thu")
steps = [f"{h:02d}:{m:02d}" for h in range(12, 17) for m in (0, 15, 30, 45)] + ["16:55"]
for nm, dd in (("Fri", fr), ("Mon-Thu", days[days.dayofweek < 4])):
    base = px.at(local_times(dd, "12:00", gl.NY), 3)
    row = []
    for s in steps:
        p = px.at(local_times(dd, s, gl.NY), 3) if s != "16:55" else px.before(local_times(dd, "16:56", gl.NY), 3)
        row.append(f"{s}:{np.nanmean(np.log(p / base) * 1e4):+.1f}")
    print(nm, " ".join(row))

# Friday 13:30-16:45 split: first Friday (NFP-ish) vs others, month, pre-holiday
r = np.log(px.at(local_times(fr, "16:45", gl.NY), 3) / px.at(local_times(fr, "13:30", gl.NY), 3)) * 1e4
first_fri = fr.day <= 7
print(f"\nFri 13:30->16:45: first Friday (day<=7) {np.nanmean(r[first_fri]):+.2f} (t {tstat(r[first_fri]):+.1f}, n {first_fri.sum()}) | "
      f"other Fridays {np.nanmean(r[~first_fri]):+.2f} (t {tstat(r[~first_fri]):+.1f}, n {(~first_fri).sum()})")
q = pd.Series(r, index=fr).groupby(fr.quarter).agg(['mean', 'count'])
print("by quarter:", q.round(2).to_dict())
# prior-week direction (Mon open -> Fri 13:30) conditioning: short-covering story
wk_open = []
for d in fr:
    mon = d - pd.Timedelta(days=4)
    wk_open.append(local_times([mon - pd.Timedelta(days=1)], "18:00", gl.NY)[0])
w = np.log(px.at(local_times(fr, "13:30", gl.NY), 3) / px.at(pd.DatetimeIndex(wk_open), 10)) * 1e4
for nm, c in (("week up to Fri 13:30", w > 0), ("week down", w < 0)):
    print(f"  {nm:22s} Fri pm drift {np.nanmean(r[c]):+.2f} (t {tstat(r[c]):+.1f}, n {c.sum()})")
# realized vol in the window vs other days' same window
oth = days[days.dayofweek < 4]
ro = np.log(px.at(local_times(oth, "16:45", gl.NY), 3) / px.at(local_times(oth, "13:30", gl.NY), 3)) * 1e4
print(f"  sd Fri window {np.nanstd(r):.1f} bp vs Mon-Thu same window {np.nanstd(ro):.1f} bp; Mon-Thu mean {np.nanmean(ro):+.2f} (t {tstat(ro):+.1f})")

# weekend gap, bid-only / ask-only / mid, different references
print("\n=== weekend gap with different reference prices (bp)")
td = gl.trading_day(m1.index)
ii = pd.Series(np.arange(len(m1)), index=m1.index)
mon_first = ii[td.dayofweek == 0].groupby(td[td.dayofweek == 0]).min()
mon_first = mon_first[(mon_first.index >= "2013-01-01") & (mon_first.index < "2022-01-01")]
i0 = mon_first.to_numpy()
mondays = pd.DatetimeIndex(mon_first.index)
fri_before = mondays - pd.Timedelta(days=3)
bo, bc, ao, ac = (m1[k].to_numpy() for k in ("bo", "bc", "ao", "ac"))
def at_idx(times, arr, tol=5):
    t = pd.DatetimeIndex(times).tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)
    i = np.searchsorted(px.ns, t, "left"); ok = (i < len(px.ns))
    i = np.where(ok, i, 0); good = ok & ((px.ns[i] - t) <= tol * 60e9)
    out = np.full(len(t), np.nan); out[good] = arr[i[good]]; return out
for ref_f, ref_m in (("16:45", "first"), ("16:45", "+15m"), ("16:00", "+60m"), ("16:58", "first")):
    tf = local_times(fri_before, ref_f, gl.NY)
    if ref_m == "first":
        mb, ma = bo[i0], ao[i0]
    else:
        mins = int(ref_m[1:-1])
        tm = m1.index[i0] + pd.Timedelta(minutes=mins)
        mb, ma = at_idx(tm, bo), at_idx(tm, ao)
    fb, fa = at_idx(tf, bo), at_idx(tf, ao)
    gb, ga, gm = (np.log(mb / fb) * 1e4, np.log(ma / fa) * 1e4, np.log((mb + ma) / (fb + fa)) * 1e4)
    s = summarize(gm, mondays.year)
    print(f"Fri {ref_f} -> Sun open {ref_m}: mid {np.nanmean(gm):+.2f} (t {tstat(gm):+.1f}) bid {np.nanmean(gb):+.2f} (t {tstat(gb):+.1f}) "
          f"ask {np.nanmean(ga):+.2f} (t {tstat(ga):+.1f}) n={np.isfinite(gm).sum()} yrs {s['yrs_same_sign']} {s['by_year']}")

# Friday 13:30 -> Monday various exits (mid), the 'weekend hedge' trade
print("\n=== Friday 13:30 NY entry -> exit Monday at ... (mid, gross)")
a = px.at(local_times(fri_before, "13:30", gl.NY), 3)
for ex_tz, ex_t in ((gl.NY, "16:45F"), (gl.NY, "19:00"), (gl.NY, "22:00"), (gl.LDN, "07:00"), (gl.LDN, "08:00"), (gl.NY, "08:00"), (gl.NY, "12:00")):
    if ex_t.endswith("F"):
        b = px.at(local_times(fri_before, ex_t[:-1], gl.NY), 3)
    elif ex_t in ("19:00", "22:00"):
        b = px.at(local_times(mondays - pd.Timedelta(days=1), ex_t, gl.NY), 5)
    else:
        b = px.at(local_times(mondays, ex_t, ex_tz), 5)
    rr = np.log(b / a) * 1e4
    s = summarize(rr, mondays.year)
    print(f"  exit {ex_t:7s} {ex_tz:16s} mean {s['mean_bp']:+6.2f} t {s['t']:+5.2f} sd {s['sd_bp']:5.1f} med {s['median_bp']:+6.2f} yrs {s['yrs_same_sign']} {s['by_year']}")

# Pre-holiday analogue: last trading day before a weekday market holiday (NY trading day gap > 1 business day)
print("\n=== day before a weekday holiday (next trading day is > 1 business day later), 13:30->16:45 NY or last bar")
alld = pd.DatetimeIndex(d1.index)
nxt = pd.Series(alld[1:].tolist() + [pd.NaT], index=alld)
gapd = np.busday_count(alld.values.astype('datetime64[D]'), nxt.fillna(alld[-1]).values.astype('datetime64[D]'))
pre_hol = alld[(gapd > 1) & (alld.dayofweek < 4) & (alld >= "2013-01-01") & (alld < "2022-01-01")]
rh = np.log(px.before(local_times(pre_hol, "16:45", gl.NY), 30) / px.at(local_times(pre_hol, "13:30", gl.NY), 5)) * 1e4
print(f"n={np.isfinite(rh).sum()} mean {np.nanmean(rh):+.2f} (t {tstat(rh):+.1f}) dates: {[str(d.date()) for d in pre_hol][:12]} ...")
