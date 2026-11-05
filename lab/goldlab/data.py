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


def load_m1(sym="xauusd", start=None, end=None):
    """Load M1 bid/ask bars for `sym` (xauusd, eurusd, gbpusd, usdjpy, deuidxeur, lightcmdusd)."""
    if sym not in _cache:
        _cache[sym] = pd.read_parquet(os.path.join(DATA, f"{sym}_m1.parquet"))
    df = _cache[sym]
    if start is not None:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        df = df[df.index < pd.Timestamp(end, tz="UTC")]
    return df


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
