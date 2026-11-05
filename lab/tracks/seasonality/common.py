"""Shared helpers for the seasonality track (descriptive statistics + order building).

All prices are MID prices ((bid+ask)/2) for descriptive work.  Trading uses the engine
(goldlab.simulate) with real bid/ask + costs.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402

RES = os.path.join(LAB, "results", "seasonality")
os.makedirs(RES, exist_ok=True)

IS_START, IS_END = pd.Timestamp("2013-01-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC")


class Px:
    """Fast 'price at time T' lookups on an M1 frame (mid prices)."""

    def __init__(self, m1):
        self.m1 = m1
        self.ns = m1.index.values.astype("datetime64[ns]").astype(np.int64)
        self.mo = ((m1["bo"].to_numpy() + m1["ao"].to_numpy()) / 2)
        self.mc = ((m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2)

    def at(self, times, tol_min=5):
        """Mid OPEN of the first M1 bar starting at/after each time (NaN if none within tol)."""
        t = pd.DatetimeIndex(times).tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)
        i = np.searchsorted(self.ns, t, side="left")
        ok = i < len(self.ns)
        out = np.full(len(t), np.nan)
        ii = np.where(ok, i, 0)
        good = ok & ((self.ns[ii] - t) <= tol_min * 60_000_000_000)
        out[good] = self.mo[ii[good]]
        return out

    def before(self, times, tol_min=5):
        """Mid CLOSE of the last M1 bar starting before each time (NaN if none within tol)."""
        t = pd.DatetimeIndex(times).tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)
        j = np.searchsorted(self.ns, t, side="left") - 1
        ok = j >= 0
        out = np.full(len(t), np.nan)
        jj = np.where(ok, j, 0)
        good = ok & ((t - self.ns[jj]) <= (tol_min + 1) * 60_000_000_000)
        out[good] = self.mc[jj[good]]
        return out


def local_times(dates, hhmm, tz):
    """UTC timestamps of wall-clock time `hhmm` ('HH:MM') in `tz` on each calendar date."""
    d = pd.DatetimeIndex(pd.to_datetime(dates)).tz_localize(None).normalize()
    h, m = (int(x) for x in hhmm.split(":"))
    loc = (d + pd.Timedelta(hours=h, minutes=m)).tz_localize(tz, nonexistent="shift_forward",
                                                              ambiguous=True)
    return loc.tz_convert("UTC")


def tstat(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return np.nan
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))


def summarize(r, years, label=""):
    """r: returns in bp (array), years: array of years. Returns a dict of descriptive stats."""
    r = np.asarray(r, float)
    years = np.asarray(years)
    ok = np.isfinite(r)
    r, years = r[ok], years[ok]
    s = pd.Series(r).groupby(years).mean()
    m = r.mean()
    lo, hi = np.percentile(r, [1, 99]) if len(r) > 10 else (np.nan, np.nan)
    w = np.clip(r, lo, hi)
    return {
        "label": label, "n": len(r), "mean_bp": round(m, 2), "t": round(tstat(r), 2),
        "median_bp": round(float(np.median(r)), 2), "wins_mean_bp": round(w.mean(), 2),
        "t_wins": round(tstat(w), 2), "sd_bp": round(r.std(ddof=1), 1),
        "hit": round(float((r > 0).mean()), 3),
        "yrs_same_sign": f"{int((np.sign(s) == np.sign(m)).sum())}/{len(s)}",
        "by_year": {int(k): round(v, 1) for k, v in s.items()},
    }
