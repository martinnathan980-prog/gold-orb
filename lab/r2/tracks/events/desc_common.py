"""Descriptive helpers for the events track (IS ONLY: frames are loaded with end='2022-01-01')."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from calendars import release_times  # noqa: E402

RES = os.path.join(LAB, "results", "r2", "events")
os.makedirs(RES, exist_ok=True)
IS_END = "2022-01-01"
NY = gl.NY
MIN = 60_000_000_000


def load_is(sym):
    r2.free()
    return r2.load(sym, end=IS_END)


class Px:
    def __init__(self, m1):
        self.ns = m1.index.values.astype("datetime64[ns]").astype(np.int64)
        self.mo = (m1["bo"].to_numpy() + m1["ao"].to_numpy()) / 2
        self.mc = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2
        self.mh = (m1["bh"].to_numpy() + m1["ah"].to_numpy()) / 2
        self.ml = (m1["bl"].to_numpy() + m1["al"].to_numpy()) / 2
        self.spr = (m1["ac"].to_numpy() - m1["bc"].to_numpy())
        self.spo = (m1["ao"].to_numpy() - m1["bo"].to_numpy())

    def _ns(self, times):
        return pd.DatetimeIndex(times).tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)

    def at(self, times, tol_min=3):
        """Mid OPEN of the first bar starting at/after each time (NaN if none within tol)."""
        t = self._ns(times)
        i = np.searchsorted(self.ns, t, side="left")
        ok = i < len(self.ns)
        ii = np.where(ok, i, 0)
        good = ok & ((self.ns[ii] - t) <= tol_min * MIN)
        out = np.full(len(t), np.nan)
        out[good] = self.mo[ii[good]]
        return out

    def before(self, times, tol_min=3):
        """Mid CLOSE of the last bar that started before each time (NaN if older than tol)."""
        t = self._ns(times)
        j = np.searchsorted(self.ns, t, side="left") - 1
        ok = j >= 0
        jj = np.where(ok, j, 0)
        good = ok & ((t - self.ns[jj]) <= (tol_min + 1) * MIN)
        out = np.full(len(t), np.nan)
        out[good] = self.mc[jj[good]]
        return out

    def spread_at(self, times, tol_min=0):
        """Spread (close) of the bar starting exactly at each time (NaN if absent)."""
        t = self._ns(times)
        i = np.searchsorted(self.ns, t, side="left")
        ok = i < len(self.ns)
        ii = np.where(ok, i, 0)
        good = ok & ((self.ns[ii] - t) <= tol_min * MIN)
        out = np.full(len(t), np.nan)
        out[good] = self.spr[ii[good]]
        return out

    def hilo(self, t0, t1):
        """Mid high / low over bars starting in [t0, t1)."""
        a = np.searchsorted(self.ns, self._ns(t0), side="left")
        b = np.searchsorted(self.ns, self._ns(t1), side="left")
        hi = np.full(len(a), np.nan)
        lo = np.full(len(a), np.nan)
        for k in range(len(a)):
            if b[k] > a[k]:
                hi[k] = self.mh[a[k]:b[k]].max()
                lo[k] = self.ml[a[k]:b[k]].min()
        return hi, lo


def ny_time(t_utc, hhmm, day_shift=0):
    """UTC timestamps of wall-clock `hhmm` New York on the NY calendar date of each `t_utc` (+ business-day shift)."""
    d = pd.DatetimeIndex(t_utc).tz_convert(NY).tz_localize(None).normalize()
    if day_shift:
        d = d + pd.offsets.BDay(day_shift)
    h, m = (int(x) for x in hhmm.split(":"))
    return (d + pd.Timedelta(hours=h, minutes=m)).tz_localize(NY).tz_convert("UTC")


def tstat(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) < 3:
        return np.nan
    s = x.std(ddof=1)
    return float(x.mean() / (s / np.sqrt(len(x)))) if s > 0 else np.nan


def line(label, r, years):
    r = np.asarray(r, float)
    ok = np.isfinite(r)
    r, y = r[ok], np.asarray(years)[ok]
    if len(r) < 3:
        return f"{label:40s} n={len(r)}"
    by = pd.Series(r).groupby(y).mean()
    m = r.mean()
    lo, hi = np.percentile(r, [2.5, 97.5])
    w = np.clip(r, lo, hi)
    return (f"{label:40s} n={len(r):4d} mean={m:+7.2f} t={tstat(r):+5.2f} med={np.median(r):+7.2f} wins_t={tstat(w):+5.2f} "
            f"sd={r.std(ddof=1):6.1f} hit={np.mean(r > 0):.2f} yrs={int((np.sign(by) == np.sign(m)).sum())}/{len(by)}")
