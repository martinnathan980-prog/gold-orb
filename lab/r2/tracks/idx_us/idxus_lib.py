"""Track idx_us - shared helpers: US cash-session calendar, per-session price grid, daily ATR.

Everything here is causal by construction: `grid()` returns, for every regular US cash session and every
minute offset m from the 09:30 New York open, the mid price KNOWN at 09:30+m (close of the last M1 bar that
started before that instant) and the M1 index of the first bar on which a decision taken at that instant can
be executed.
"""
import datetime as dt

import numpy as np
import pandas as pd

NY = "America/New_York"


# ------------------------------------------------------------------------------------------------
# NYSE calendar (rule based, so that it works on any year; special one-off closures listed by hand)
# ------------------------------------------------------------------------------------------------
def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mo = (h + l - 7 * m + 114) // 31
    da = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(y, mo, da)


def _nth(y, mo, wd, n):
    """n-th weekday `wd` (Mon=0) of month; n=-1 -> last."""
    if n > 0:
        d = dt.date(y, mo, 1)
        d += dt.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))
        return d
    d = dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - wd) % 7)


def _observed(d):
    """NYSE rule: Saturday holiday -> Friday before, Sunday holiday -> Monday after."""
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


SPECIAL_CLOSURES = {dt.date(2018, 12, 5), dt.date(2025, 1, 9)}     # days of mourning (Bush, Carter)


def us_holidays(y):
    """(full_closures, early_closes_13h) of the US cash equity market for year y."""
    full = set()
    ny = dt.date(y, 1, 1)
    if ny.weekday() == 6:
        full.add(dt.date(y, 1, 2))
    elif ny.weekday() < 5:
        full.add(ny)                                   # Saturday New Year is NOT observed on Friday
    full.add(_nth(y, 1, 0, 3))                         # Martin Luther King
    full.add(_nth(y, 2, 0, 3))                         # Presidents' day
    full.add(_easter(y) - dt.timedelta(days=2))        # Good Friday
    full.add(_nth(y, 5, 0, -1))                        # Memorial day
    if y >= 2022:
        full.add(_observed(dt.date(y, 6, 19)))         # Juneteenth
    full.add(_observed(dt.date(y, 7, 4)))
    full.add(_nth(y, 9, 0, 1))                         # Labor day
    tg = _nth(y, 11, 3, 4)
    full.add(tg)                                       # Thanksgiving
    full.add(_observed(dt.date(y, 12, 25)))
    full |= {d for d in SPECIAL_CLOSURES if d.year == y}
    half = {tg + dt.timedelta(days=1)}                 # Friday after Thanksgiving
    j3, j4 = dt.date(y, 7, 3), dt.date(y, 7, 4)
    if j4.weekday() in (1, 2, 3, 4) and j3.weekday() < 5:
        half.add(j3)
    x = dt.date(y, 12, 24)
    if x.weekday() < 4:                                # Mon-Thu Christmas eve (Friday eve = full closure)
        half.add(x)
    half -= full
    return full, half


def calendar_flags(dates):
    """dates: sequence of datetime.date -> (is_full_holiday, is_half_day) boolean arrays."""
    cache = {}
    full = np.zeros(len(dates), bool)
    half = np.zeros(len(dates), bool)
    for i, d in enumerate(dates):
        if d.year not in cache:
            cache[d.year] = us_holidays(d.year)
        f, h = cache[d.year]
        full[i] = d in f
        half[i] = d in h
    return full, half


# ------------------------------------------------------------------------------------------------
# Session grid
# ------------------------------------------------------------------------------------------------
_grid_cache = {}
_atr_cache = {}


def frame_key(m1):
    """Cheap content key of an M1 frame (distinguishes base / stress / gross copies and truncations)."""
    return (len(m1), int(m1.index[0].value), int(m1.index[-1].value),
            float(m1["bc"].to_numpy().sum()), float(m1["ac"].to_numpy().sum()))


def grid(m1, n_min=391, stale_min=10, late_min=5):
    """Per-session price grid.

    Returns a dict:
      dates   (D,) python dates of regular US cash sessions found in the frame (weekdays, not full holidays)
      half    (D,) True on 13:00 early closes
      t0      (D,) UTC datetime64[ns] of 09:30 New York
      P       (D, n_min) mid price known at 09:30 + m minutes (NaN if the last bar is older than `stale_min`)
      POS     (D, n_min) raw position of the first bar starting at/after 09:30 + m (may be len(m1))
      EI      (D, n_min) same, but -1 when that bar starts more than `late_min` minutes late (or does not exist)
      O       (D,) mid OPEN of the first bar starting in [09:30, 09:32)  (NaN if none)
      idx     (N,) bar start times as datetime64[ns]
    Column 390 is 16:00 (the cash close).  Only past data enter P[d, m]: it is the close of the last bar that
    STARTED before 09:30+m, so it is known at that instant.
    """
    key = frame_key(m1) + (n_min, stale_min, late_min)
    if key in _grid_cache:
        return _grid_cache[key]
    if len(_grid_cache) > 3:
        _grid_cache.clear()
    idx = m1.index
    iv = idx.values.astype("datetime64[ns]")
    ny = idx.tz_convert(NY)
    days = pd.DatetimeIndex(np.unique(ny.tz_localize(None).normalize().values))
    days = days[days.dayofweek < 5]
    dlist = [d.date() for d in days]
    full, half = calendar_flags(dlist)
    days = days[~full]
    half = half[~full]
    dlist = [d.date() for d in days]
    t0 = (days + pd.Timedelta(minutes=570)).tz_localize(NY).tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]")
    T = t0[:, None] + (np.arange(n_min)[None, :] * np.timedelta64(60, "s")).astype("timedelta64[ns]")
    pos = np.searchsorted(iv, T.ravel(), side="left").reshape(T.shape)
    mid_c = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2
    mid_o = (m1["bo"].to_numpy() + m1["ao"].to_numpy()) / 2
    n = len(iv)
    prev = np.clip(pos - 1, 0, n - 1)
    age = (T - iv[prev]) / np.timedelta64(60, "s")            # minutes since the START of the last bar before T
    P = np.where((pos > 0) & (age <= stale_min + 1), mid_c[prev], np.nan)
    nxt = np.clip(pos, 0, n - 1)
    late = (iv[nxt] - T) / np.timedelta64(60, "s")
    EI = np.where((pos < n) & (late <= late_min) & (late >= 0), pos, -1).astype(np.int64)
    O = np.where((pos[:, 0] < n) & (late[:, 0] < 2) & (late[:, 0] >= 0), mid_o[nxt[:, 0]], np.nan)
    out = {"dates": np.array(dlist), "half": half, "t0": t0, "P": P, "POS": pos.astype(np.int64), "EI": EI, "O": O, "idx": iv}
    _grid_cache[key] = out
    return out


def daily_atr(m1, n=14, min_minutes=600):
    """Simple-average ATR(n) of NY-17:00 trading days (mid prices), holiday stubs (< min_minutes of data) dropped.

    Returns (t_known, atr): the value atr[j] is usable from t_known[j] = 17:00 New York of trading day j
    (the nominal end of the day, never earlier), as datetime64[ns] UTC.  Same definition as MT5 iATR(D1, n)
    on a server whose midnight is 17:00 New York (FP Markets), read on the last COMPLETED daily bar.
    """
    key = frame_key(m1) + (n, min_minutes)
    if key in _atr_cache:
        return _atr_cache[key]
    if len(_atr_cache) > 3:
        _atr_cache.clear()
    ny = m1.index.tz_convert(NY)
    td = (ny + pd.Timedelta(hours=7)).tz_localize(None).normalize().values      # trading day (17:00 NY roll)
    st = np.flatnonzero(np.r_[True, td[1:] != td[:-1]])
    cnt = np.diff(np.r_[st, len(td)])
    h = np.maximum.reduceat(((m1["bh"].to_numpy() + m1["ah"].to_numpy()) / 2), st)
    l = np.minimum.reduceat(((m1["bl"].to_numpy() + m1["al"].to_numpy()) / 2), st)
    c = ((m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2)[np.r_[st[1:] - 1, len(td) - 1]]
    days = pd.DatetimeIndex(td[st])
    keep = cnt >= min_minutes
    h, l, c, days = h[keep], l[keep], c[keep], days[keep]
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    atr = pd.Series(tr).rolling(n, min_periods=n).mean().to_numpy()
    # trading day X ends at 17:00 New York on calendar day X
    t_known = (days + pd.Timedelta(hours=17)).tz_localize(NY).tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]")
    _atr_cache[key] = (t_known, atr)
    return _atr_cache[key]


def atr_at(m1, times, n=14):
    """ATR(n) known at each UTC datetime64[ns] in `times` (last trading day completed at/before that time)."""
    tk, a = daily_atr(m1, n)
    if len(a) == 0:                                   # frame shorter than one full trading day
        return np.full(len(times), np.nan)
    j = np.searchsorted(tk, times, side="right") - 1
    return np.where(j >= 0, a[np.clip(j, 0, len(a) - 1)], np.nan)
