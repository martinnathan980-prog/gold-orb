"""Descriptive helpers for the overnight track (IN-SAMPLE ONLY: every frame is cut at 2022-01-01).

Prices are MID prices; "price at time T" = mid OPEN of the first M1 bar starting at/after T, valid only
if that bar starts within `tol` minutes of T AND the market was really trading just before T (at least
`min_prev` bars in the previous 30 minutes) -- this removes the single filler bars that the Dukascopy
files contain at 00:00 UTC during the 2015-2017 period when the US indices had no evening session.
"""
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402

RES = os.path.join(LAB, "results", "r2", "overnight")
os.makedirs(RES, exist_ok=True)
IS_END = "2022-01-01"
NY = "America/New_York"
BER = "Europe/Berlin"


def load_is(sym):
    """IS-only FP-cost frame (never contains a bar from 2022 on)."""
    m1 = r2.load(sym, end=IS_END)
    assert m1.index[-1] < pd.Timestamp(IS_END, tz="UTC")
    return m1


class Px:
    def __init__(self, m1):
        self.ns = m1.index.values.astype("datetime64[ns]").astype(np.int64)
        self.mo = (m1["bo"].to_numpy() + m1["ao"].to_numpy()) / 2
        self.mc = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2
        self.spr = (m1["ao"].to_numpy() - m1["bo"].to_numpy())
        self.n = len(self.ns)

    def at(self, times, tol=5, min_prev=10, need_prev=True):
        """Mid open of the first bar at/after each time (NaN if market shut / stub bar)."""
        t = pd.DatetimeIndex(times).tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)
        i = np.searchsorted(self.ns, t, side="left")
        ok = i < self.n
        ii = np.where(ok, i, 0)
        good = ok & ((self.ns[ii] - t) <= tol * 60_000_000_000)
        if need_prev:
            j = np.searchsorted(self.ns, t - 30 * 60_000_000_000, side="left")
            good &= (ii - j) >= min_prev
        out = np.full(len(t), np.nan)
        out[good] = self.mo[ii[good]]
        return out

    def last(self, times, tol=10):
        """Mid close of the last bar that started before each time (NaN if older than tol minutes)."""
        t = pd.DatetimeIndex(times).tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)
        j = np.searchsorted(self.ns, t, side="left") - 1
        ok = j >= 0
        jj = np.where(ok, j, 0)
        good = ok & ((t - self.ns[jj]) <= (tol + 1) * 60_000_000_000)
        out = np.full(len(t), np.nan)
        out[good] = self.mc[jj[good]]
        return out


def local_times(dates, hhmm, tz):
    d = pd.DatetimeIndex(pd.to_datetime(dates)).tz_localize(None).normalize()
    if isinstance(hhmm, str):
        h, m = (int(x) for x in hhmm.split(":"))
        mins = h * 60 + m
    else:
        mins = int(hhmm)
    loc = (d + pd.Timedelta(minutes=mins)).tz_localize(tz, nonexistent="shift_forward", ambiguous=True)
    return loc.tz_convert("UTC")


def cal_dates(m1, tz):
    a = m1.index[0].tz_convert(tz).tz_localize(None).normalize()
    b = m1.index[-1].tz_convert(tz).tz_localize(None).normalize()
    return pd.date_range(a, b, freq="D")


def tstat(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3 or x.std(ddof=1) == 0:
        return np.nan
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))


def summ(r, years, label=""):
    """r in bp. mean, t, winsorised t, hit rate, years with the same sign as the overall mean."""
    r = np.asarray(r, float)
    years = np.asarray(years)
    ok = np.isfinite(r)
    r, years = r[ok], years[ok]
    if len(r) < 5:
        return {"label": label, "n": int(len(r))}
    s = pd.Series(r).groupby(years).mean()
    m = float(r.mean())
    lo, hi = np.percentile(r, [1, 99])
    w = np.clip(r, lo, hi)
    return {"label": label, "n": int(len(r)), "mean": round(m, 2), "t": round(tstat(r), 2), "tw": round(tstat(w), 2),
            "med": round(float(np.median(r)), 2), "sd": round(float(r.std(ddof=1)), 1), "hit": round(float((r > 0).mean()), 3),
            "yrs": f"{int((np.sign(s) == np.sign(m)).sum())}/{len(s)}",
            "by_year": {int(k): round(float(v), 1) for k, v in s.items()}}


def fmt(d, by_year=True):
    if "mean" not in d:
        return f"{d['label']:<34} n={d['n']}"
    s = (f"{d['label']:<34} n={d['n']:>5} mean={d['mean']:>7.2f}bp t={d['t']:>6.2f} tw={d['tw']:>6.2f} med={d['med']:>6.2f} "
         f"sd={d['sd']:>6.1f} hit={d['hit']:.3f} yrs={d['yrs']}")
    if by_year:
        s += "  | " + " ".join(f"{str(k)[2:]}:{v:+.1f}" for k, v in d["by_year"].items())
    return s


def window_ret(px, dates, t0, t1, tz, d1=0, **kw):
    """bp return from local time t0 on each date to local time t1 on date + d1 calendar days."""
    a = px.at(local_times(dates, t0, tz), **kw)
    b = px.at(local_times(pd.DatetimeIndex(dates) + pd.Timedelta(days=d1), t1, tz), **kw)
    return (b / a - 1) * 1e4


GRIDS = os.path.join(RES, "grids")


def save_grid(P, sym):
    """Price grid (IS only) written by desc1 and reused by desc2 / desc5 / desc6 / desc7."""
    os.makedirs(GRIDS, exist_ok=True)
    P.to_csv(os.path.join(GRIDS, f"P_{sym}.csv"), float_format="%.6f")


def load_grid(sym):
    P = pd.read_csv(os.path.join(GRIDS, f"P_{sym}.csv"), index_col=0, parse_dates=True)
    assert P.index[-1] < pd.Timestamp(IS_END)
    return P
