"""Data access helpers. All timestamps are UTC.

Columns of an M1 frame: bo bh bl bc (bid OHLC), ao ah al ac (ask OHLC).
Bars are labelled by their START time (Dukascopy convention); a bar is only known
at its CLOSE time.  Use `bars()` which adds `t_close`, and `entry_index()` to map a
decision time to the first M1 bar you can actually trade on.
"""
import os

import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
NY = "America/New_York"
LDN = "Europe/London"

_cache = {}
HOLDOUT_START = "2026-01-01"   # research never sees data from this date on (PROTOCOL / PROTOCOL_V2)


def load_m1(sym="xauusd", start=None, end=None, include_holdout=False):
    """Load M1 bid/ask bars for `sym`.
    Round 1: xauusd, eurusd, gbpusd, usdjpy, deuidxeur, lightcmdusd.
    Round 2 (real bid+ask): us100, us500, us30, ger40, xagusd, btcusd, ethusd.
    Data from 2026-01-01 on is the HOLDOUT: it is cut off unless include_holdout=True
    (reserved to the lead's final test and to live/parity tools)."""
    if sym not in _cache:
        _cache[sym] = pd.read_parquet(os.path.join(DATA, f"{sym}_m1.parquet"))
    df = _cache[sym]
    idx = df.index
    lo = 0 if start is None else int(idx.searchsorted(_utc(start), side="left"))
    cap = _utc(end) if end is not None else None
    if not include_holdout:
        h = _utc(HOLDOUT_START)
        cap = h if cap is None or cap > h else cap
    hi = len(df) if cap is None else int(idx.searchsorted(cap, side="left"))
    return df.iloc[lo:hi]


def _utc(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def trading_day(ts):
    """FX/metals trading day: a new day starts at 17:00 New York (broker 'server midnight').
    Returns a DatetimeIndex of normalized dates (tz-naive)."""
    ny = pd.DatetimeIndex(ts).tz_convert(NY)
    return (ny + pd.Timedelta(hours=7)).tz_localize(None).normalize()


def local(ts, tz):
    """Convert a UTC DatetimeIndex to local wall-clock time of `tz` (keeps tz info)."""
    return pd.DatetimeIndex(ts).tz_convert(tz)


_AGG = {"bo": "first", "bh": "max", "bl": "min", "bc": "last",
        "ao": "first", "ah": "max", "al": "min", "ac": "last"}


def bars(m1, rule):
    """Resample M1 to `rule` ('5min','15min','1h','4h', or 'D' = NY-17:00 trading day).
    Adds mid OHLC (o h l c) and `t_close` (UTC time at which the bar is complete and
    tradable).  Empty bars are dropped."""
    if rule == "D":
        td = trading_day(m1.index)
        g = m1.groupby(td)
        b = g.agg(_AGG)
        b["t_close"] = g.apply(lambda x: x.index[-1]) + pd.Timedelta(minutes=1)
        b.index.name = "day"
    else:
        b = m1.resample(rule, label="left", closed="left").agg(_AGG).dropna()
        last = m1.index.to_series().resample(rule, label="left", closed="left").last().reindex(b.index)
        b["t_close"] = last + pd.Timedelta(minutes=1)
    for k in "ohlc":
        b[k] = (b["b" + k] + b["a" + k]) / 2
    return b


def entry_index(m1, times):
    """Index of the first M1 bar whose start >= each time in `times` (i.e. the first bar
    you can trade at its open after a decision made at `times`). Returns int64 array;
    len(m1) means 'no bar' (beyond data)."""
    t = pd.DatetimeIndex(times)
    return np.searchsorted(m1.index.values, t.values, side="left").astype(np.int64)


def atr(b, n=14):
    """Wilder ATR on mid prices of a bar frame (uses only past/current bar)."""
    pc = b["c"].shift(1)
    tr = np.maximum(b["h"] - b["l"], np.maximum((b["h"] - pc).abs(), (b["l"] - pc).abs()))
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def exit_index(m1, times, max_gap_min=30):
    """M1 index at whose OPEN a time exit scheduled at `times` executes (use it for `exit_i`).
    If a time falls inside a market closure (weekend, daily break, holiday, data gap: next bar more
    than `max_gap_min` later), the exit is done on the LAST bar before the closure instead of after it."""
    idx = m1.index.values
    xv = pd.DatetimeIndex(times).tz_convert("UTC").tz_localize(None).values.astype(idx.dtype)
    xi = np.searchsorted(idx, xv, side="left").astype(np.int64)
    nxt = idx[np.clip(xi, 0, len(idx) - 1)]
    gap = (xi >= len(idx)) | ((nxt - xv) > np.timedelta64(max_gap_min, "m"))
    return np.where(gap & (xi > 0), xi - 1, xi).astype(np.int64)


def full_days(m1, min_minutes=600):
    """Daily bars ('D' = trading day ending 17:00 New York) keeping only days with enough data:
    drops holiday stubs and holes, whose tiny ranges would distort daily ATR / previous-day levels."""
    d = bars(m1, "D")
    cnt = m1.groupby(trading_day(m1.index)).size()
    return d[cnt.reindex(d.index).fillna(0).to_numpy() >= min_minutes]
