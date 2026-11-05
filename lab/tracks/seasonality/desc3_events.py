"""Descriptive (IS only): London fixes, US 08:30 data window, turn of month, Monday open gap,
Asian (Beijing clock) hours.  Mid prices, bp."""
import numpy as np
import pandas as pd

from common import IS_END, IS_START, RES, Px, gl, local_times, summarize, tstat

m1 = gl.load_m1("xauusd", "2012-12-30", "2022-01-03")
px = Px(m1)
d1 = gl.bars(m1, "D")
days = pd.DatetimeIndex(d1.index[(d1.index >= "2013-01-01") & (d1.index < "2022-01-01")])


def win(dd, tz, t0, t1, tol=3):
    a = px.at(local_times(dd, t0, tz), tol)
    b = px.at(local_times(dd, t1, tz), tol)
    return np.log(b / a) * 1e4


def line(label, r, yrs):
    s = summarize(r, yrs, label)
    return (f"{label:46s} n={s['n']:5d} mean={s['mean_bp']:+6.2f} t={s['t']:+5.2f} med={s['median_bp']:+6.2f} "
            f"tw={s['t_wins']:+5.2f} sd={s['sd_bp']:5.1f} yrs={s['yrs_same_sign']} {s['by_year']}")


def hm(t, dm):
    h, m = (int(x) for x in t.split(":"))
    tot = h * 60 + m + dm
    return f"{tot // 60:02d}:{tot % 60:02d}"


# ------------------------------------------------------------- London fixes (LBMA gold price)
print("=== London fix windows (London clock), all London weekdays; split old fix (<2015-03-20) / ICE auction")
auction = pd.Timestamp("2015-03-20")
for fix in ("10:30", "15:00"):
    for a, b in ((-120, 0), (-60, -30), (-30, 0), (-15, 0), (0, 15), (0, 5), (5, 15), (15, 60), (60, 120), (0, 60)):
        r = win(days, gl.LDN, hm(fix, a), hm(fix, b))
        old = days < auction
        s_all = summarize(r, days.year)
        print(line(f"fix {fix} [{a:+d},{b:+d}]m", r, days.year)
              + f" | old {np.nanmean(r[old]):+5.2f}({tstat(r[old]):+4.1f}) new {np.nanmean(r[~old]):+5.2f}({tstat(r[~old]):+4.1f})")

# ------------------------------------------------------------- US 08:30 NY data window
print("\n=== 08:30 NY data window, by weekday (Thu = jobless claims, 1st Fri ~ NFP)")
for a, b in (("08:00", "08:29"), ("08:25", "08:30"), ("08:30", "08:45"), ("08:30", "09:30"), ("08:45", "09:30"),
             ("08:30", "10:00"), ("09:30", "10:00"), ("10:00", "11:00")):
    r = win(days, gl.NY, a, b)
    parts = " | ".join(f"{nm} {np.nanmean(r[days.dayofweek == k]):+5.1f}({tstat(r[days.dayofweek == k]):+4.1f})"
                       for k, nm in enumerate(["Mo", "Tu", "We", "Th", "Fr"]))
    print(line(f"NY {a}->{b}", r, days.year) + " || " + parts)

# ------------------------------------------------------------- turn of month (trading days)
print("\n=== turn of month: close-to-close trading-day returns by position in month")
c = d1["c"]
ret = np.log(c / c.shift(1)) * 1e4
ret = ret[(ret.index >= "2013-01-01") & (ret.index < "2022-01-01")]
idx = pd.DatetimeIndex(ret.index)
ym = idx.year * 12 + idx.month
pos_f = pd.Series(1, index=idx).groupby(ym).cumsum().to_numpy()          # 1 = first trading day
pos_l = pd.Series(1, index=idx)[::-1].groupby(ym[::-1]).cumsum()[::-1].to_numpy()  # 1 = last
for k in (1, 2, 3, 4, 5):
    print(line(f"first+{k} (day {k} of month)", ret[pos_f == k].to_numpy(), idx[pos_f == k].year))
for k in (1, 2, 3):
    print(line(f"last-{k - 1} (day {k} from end)", ret[pos_l == k].to_numpy(), idx[pos_l == k].year))
tom = (pos_l == 1) | (pos_f <= 3)
print(line("TOM (last + first 3)", ret[tom].to_numpy(), idx[tom].year))
print(line("non-TOM", ret[~tom].to_numpy(), idx[~tom].year))
mid = (pos_f >= 9) & (pos_l >= 6)
print(line("mid-month (day>=9 & >=6 from end)", ret[mid].to_numpy(), idx[mid].year))

# ------------------------------------------------------------- Monday open gap
print("\n=== Monday open gap (Fri last close -> Sun first open) and what follows")
ny = gl.local(m1.index, gl.NY)
td = gl.trading_day(m1.index)
first_of_week = pd.Series(np.arange(len(m1)), index=m1.index)[(td.dayofweek == 0)]
g = first_of_week.groupby(td[td.dayofweek == 0]).min()          # first bar of each Monday trading day
g = g[(g.index >= "2013-01-01") & (g.index < "2022-01-01")]
i0 = g.to_numpy()
mo = px.mo[i0]
mc_prev = px.mc[i0 - 1]
gap = np.log(mo / mc_prev) * 1e4
open_t = m1.index[i0]
mondays = pd.DatetimeIndex(g.index)
r_to_ldn = np.log(px.at(local_times(mondays, "08:00", gl.LDN), 5) / mo) * 1e4
r_to_ny = np.log(px.before(local_times(mondays, "17:00", gl.NY), 5) / mo) * 1e4
r_1h = np.log(px.at(open_t + pd.Timedelta(hours=1), 5) / mo) * 1e4
print(f"gap bp: n={len(gap)} mean={np.nanmean(gap):+.2f} t={tstat(gap):+.2f} median={np.nanmedian(gap):+.2f} "
      f"mean|gap|={np.nanmean(np.abs(gap)):.1f} p90|gap|={np.nanpercentile(np.abs(gap), 90):.1f}")
print(f"open spread median ${np.median((m1.ac - m1.bc).to_numpy()[i0]):.3f}; spread 1h later "
      f"${np.median((m1.ac - m1.bc).to_numpy()[np.minimum(i0 + 60, len(m1) - 1)]):.3f}")
for lab, rr in (("open->+1h", r_1h), ("open->08:00LDN", r_to_ldn), ("open->17:00NY Mon", r_to_ny)):
    for cond, nm in ((gap > 0, "gap up"), (gap < 0, "gap down"), (np.abs(gap) > np.nanpercentile(np.abs(gap), 70), "|gap| top30%")):
        sgn = np.sign(gap[cond])
        fill = -sgn * rr[cond]  # positive = moves to fill the gap
        print(f"  {lab:18s} {nm:12s} n={cond.sum():3d} mean ret={np.nanmean(rr[cond]):+6.2f} (t {tstat(rr[cond]):+4.1f}) "
              f"| fill-direction mean={np.nanmean(fill):+6.2f} (t {tstat(fill):+4.1f})")
corr = pd.Series(gap).corr(pd.Series(r_to_ny))
print(f"  corr(gap, open->Mon17:00NY) = {corr:+.3f}")

# ------------------------------------------------------------- Asian hours on Beijing clock (no DST)
print("\n=== hour of day on Beijing clock (Asian session), all weekdays")
marks = pd.date_range(IS_START, IS_END, freq="1h", inclusive="left")
r = np.log(px.at(marks + pd.Timedelta(hours=1), 3) / px.at(marks, 3)) * 1e4
bj = gl.local(marks, "Asia/Shanghai").hour
for h in list(range(6, 17)):
    sel = (bj == h)
    print(line(f"Beijing {h:02d}:00-{h + 1:02d}:00", r[sel], marks.year[sel]))
