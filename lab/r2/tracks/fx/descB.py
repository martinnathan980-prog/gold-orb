"""Stage B (descriptive, in-sample 2013-2021, gross mid-price moves in basis points; NO engine, NO rule).
Cells counted and written to results/r2/fx/descB_*.csv / descB_summary.json.

B1 time-of-day drift : mean mid return of each London-clock hour (24 x 8 cells) and of 5 session windows
                       (5 x 8 cells): Asia 00-07, Europe AM 07-12, overlap 12-16, US PM 16-21, late 21-24 London.
B2 London 16:00 fix  : run-up 15:00->16:00 London then post-fix 16:00->16:30 and 16:00->17:00, signed by the run-up
                       (reversal < 0); all days and the last business day of the month (2 x 2 x 8 cells), plus
                       momentum into the fix: sign(14:00->15:30) x (15:30->16:00) (2 x 8 cells).
B3 London open       : first break of the Asian range (00-07 London, mid highs/lows) between 07:00 and 10:00
                       London; signed move from the broken level to 12:00 and 16:00 London (2 x 8 cells).
   NY open           : sign(08:00->09:30 NY) x (09:30 -> 12:00 NY) and (09:30 -> 16:00 NY) (2 x 8 cells).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

LDN, NY = "Europe/London", "America/New_York"
IS_END = pd.Timestamp("2022-01-01", tz="UTC")


def mid_close(m1):
    s = (m1["bc"] + m1["ac"]) / 2
    return s[s.index < IS_END]


def price_at(s, times, max_age_min=5):
    """mid close of the last M1 bar starting strictly before each UTC time (known at that time)."""
    idx = s.index.values
    tv = pd.DatetimeIndex(times).tz_convert("UTC").tz_localize(None).values.astype(idx.dtype)
    k = np.searchsorted(idx, tv, side="left") - 1
    ok = k >= 0
    kc = np.clip(k, 0, len(idx) - 1)
    ok &= (tv - idx[kc]) <= np.timedelta64(max_age_min, "m")
    return np.where(ok, s.to_numpy()[kc], np.nan)


def days_local(s, tz):
    d = pd.DatetimeIndex(s.index).tz_convert(tz).normalize().unique()
    return d[d.dayofweek < 5]


def at_local(days, hhmm, tz):
    h, m = (int(x) for x in hhmm.split(":"))
    loc = days.tz_localize(None) + pd.Timedelta(hours=h, minutes=m)
    return loc.tz_localize(tz, nonexistent="shift_forward", ambiguous=False).tz_convert("UTC")


def stats(x, years):
    x = pd.Series(np.asarray(x, float), index=years)
    x = x[np.isfinite(x.to_numpy())]
    if len(x) < 30:
        return {"n": int(len(x))}
    m = x.mean()
    by = x.groupby(level=0).mean()
    return {"n": int(len(x)), "mean_bp": round(m, 3), "t": round(m / (x.std(ddof=1) / np.sqrt(len(x))), 2),
            "years_same_sign": f"{int((np.sign(by) == np.sign(m)).sum())}/{len(by)}",
            "by_year_bp": {int(k): round(v, 2) for k, v in by.items()}}


def b1(sym, s):
    h = s.resample("1h", label="left", closed="left").last().dropna()
    r = np.log(h).diff() * 1e4
    # keep only consecutive hours
    gap = h.index.to_series().diff() == pd.Timedelta(hours=1)
    r = r[gap.to_numpy()]
    ldn = r.index.tz_convert(LDN)
    # return of the hour ENDING at label+1h is attributed to the hour that starts at label (bar label = start of the
    # last minute's hour) -> r at label L = close(L-hour) - close(previous hour) = move during hour starting L
    hour = ldn.hour
    rows = []
    for hh in range(24):
        sel = hour == hh
        st = stats(r[sel].to_numpy(), r.index[sel].year)
        rows.append({"sym": sym, "cell": f"hour_{hh:02d}", **{k: v for k, v in st.items() if k != "by_year_bp"}})
    wins = {"asia_00_07": (0, 7), "eu_am_07_12": (7, 12), "overlap_12_16": (12, 16), "us_pm_16_21": (16, 21), "late_21_24": (21, 24)}
    day = ldn.normalize()
    out_w = []
    for w, (a, b) in wins.items():
        sel = (hour >= a) & (hour < b)
        x = r[sel].groupby(day[sel]).sum()
        x = x[x.index.dayofweek < 5]
        st = stats(x.to_numpy(), x.index.year)
        out_w.append({"sym": sym, "cell": w, **st})
    return rows, out_w


def b2(sym, s):
    days = days_local(s, LDN)
    p = {t: price_at(s, at_local(days, t, LDN)) for t in ("14:00", "15:00", "15:30", "16:00", "16:30", "17:00")}
    bp = lambda a, b: (np.log(p[b]) - np.log(p[a])) * 1e4
    run = bp("15:00", "16:00")
    yrs = days.year
    # last business day of each month present in the data
    dd = pd.Series(days.tz_localize(None))
    me = dd.groupby(dd.dt.to_period("M")).transform("max").to_numpy() == dd.to_numpy()
    rows = []
    for lab, post in (("post_16_1630", bp("16:00", "16:30")), ("post_16_17", bp("16:00", "17:00"))):
        x = np.sign(run) * post
        rows.append({"sym": sym, "cell": f"fix_rev_{lab}_all", **stats(x, yrs)})
        rows.append({"sym": sym, "cell": f"fix_rev_{lab}_monthend", **stats(x[me], yrs[me])})
    mom = np.sign(bp("14:00", "15:30")) * bp("15:30", "16:00")
    rows.append({"sym": sym, "cell": "fix_mom_into_all", **stats(mom, yrs)})
    rows.append({"sym": sym, "cell": "fix_mom_into_monthend", **stats(mom[me], yrs[me])})
    return rows


def b3(sym, m1):
    m1 = m1[m1.index < IS_END]
    mh = ((m1.bh + m1.ah) / 2).to_numpy()
    ml = ((m1.bl + m1.al) / 2).to_numpy()
    mc = ((m1.bc + m1.ac) / 2)
    s = mc
    days = days_local(s, LDN)
    idx = m1.index.values
    t0 = at_local(days, "00:00", LDN).tz_localize(None).values.astype(idx.dtype)
    t7 = at_local(days, "07:00", LDN).tz_localize(None).values.astype(idx.dtype)
    t10 = at_local(days, "10:00", LDN).tz_localize(None).values.astype(idx.dtype)
    i0, i7, i10 = (np.searchsorted(idx, t) for t in (t0, t7, t10))
    p12 = price_at(s, at_local(days, "12:00", LDN))
    p16 = price_at(s, at_local(days, "16:00", LDN))
    f12, f16 = np.full(len(days), np.nan), np.full(len(days), np.nan)
    for k in range(len(days)):
        if i7[k] - i0[k] < 300 or i10[k] - i7[k] < 120:
            continue
        hi, lo = mh[i0[k]:i7[k]].max(), ml[i0[k]:i7[k]].min()
        seg_h, seg_l = mh[i7[k]:i10[k]], ml[i7[k]:i10[k]]
        up = np.flatnonzero(seg_h > hi)
        dn = np.flatnonzero(seg_l < lo)
        fu = up[0] if len(up) else 10 ** 9
        fd = dn[0] if len(dn) else 10 ** 9
        if fu == fd == 10 ** 9 or fu == fd:
            continue
        side, lvl = (1, hi) if fu < fd else (-1, lo)
        f12[k] = side * np.log(p12[k] / lvl) * 1e4
        f16[k] = side * np.log(p16[k] / lvl) * 1e4
    rows = [{"sym": sym, "cell": "ldn_open_break_to_12", **stats(f12, days.year)},
            {"sym": sym, "cell": "ldn_open_break_to_16", **stats(f16, days.year)}]
    dny = days_local(s, NY)
    q = {t: price_at(s, at_local(dny, t, NY)) for t in ("08:00", "09:30", "12:00", "16:00")}
    pre = np.log(q["09:30"] / q["08:00"])
    for lab in ("12:00", "16:00"):
        x = np.sign(pre) * np.log(q[lab] / q["09:30"]) * 1e4
        rows.append({"sym": sym, "cell": f"ny_open_mom_0930_{lab[:2]}", **stats(x, dny.year)})
    return rows


if __name__ == "__main__":
    hourly, windows, other = [], [], []
    for sym in C.PAIRS:
        m1 = C.load_is(sym)
        s = mid_close(m1)
        h, w = b1(sym, s)
        hourly += h
        windows += w
        other += b2(sym, s)
        other += b3(sym, m1)
        print(sym, "done", flush=True)
    pd.DataFrame(hourly).to_csv(os.path.join(C.OUT, "descB1_hourly.csv"), index=False)
    pd.DataFrame(windows).to_csv(os.path.join(C.OUT, "descB1_windows.csv"), index=False)
    pd.DataFrame(other).to_csv(os.path.join(C.OUT, "descB2B3.csv"), index=False)
    C.save({"hourly": hourly, "windows": windows, "other": other,
            "cells_counted": {"B1_hourly": len(hourly), "B1_windows": len(windows), "B2B3": len(other)}},
           "descB_summary.json")
