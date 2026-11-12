"""Causal descriptors at a decision time t (lens `context`). Everything here takes a frame and decision times and
uses only bars whose START is < t (closed at t), so the same call on a frame cut at t gives the same values
(checked by causality.py)."""
import os
import sys

import numpy as np
import pandas as pd

import common as C  # noqa: F401  (sets paths)

sys.path.insert(0, os.path.join(C.LAB, "r2", "tracks", "idx_us"))
import idxus_lib as cm  # noqa: E402

H_NS = 3_600 * 10 ** 9
M_NS = 60 * 10 ** 9
D_NS = 86_400 * 10 ** 9


def ns_of(ts):
    """UTC timestamps (DatetimeIndex / Series / array) -> int64 ns."""
    x = pd.DatetimeIndex(ts)
    if x.tz is not None:
        x = x.tz_convert("UTC").tz_localize(None)
    return x.values.astype("datetime64[ns]").astype(np.int64)


def to_ts(ns):
    return pd.DatetimeIndex(np.asarray(ns, np.int64).astype("datetime64[ns]")).tz_localize("UTC")


class Market:
    """Arrays of one market needed by the descriptors (mid closes, spreads, hourly highs / lows, daily ATR)."""

    def __init__(self, m1, hourly=True):
        self.ns = ns_of(m1.index)
        self.mc = ((m1["bc"].to_numpy(np.float64) + m1["ac"].to_numpy(np.float64)) / 2)
        self.spr = (m1["ac"].to_numpy(np.float64) - m1["bc"].to_numpy(np.float64))
        tk, a = cm.daily_atr(m1, 14)
        self.atr_tk = np.asarray(tk).astype("datetime64[ns]").astype(np.int64)
        self.atr_v = np.asarray(a, np.float64)
        if hourly:
            mh = (m1["bh"].to_numpy(np.float64) + m1["ah"].to_numpy(np.float64)) / 2
            ml = (m1["bl"].to_numpy(np.float64) + m1["al"].to_numpy(np.float64)) / 2
            hid = self.ns // H_NS
            st = np.flatnonzero(np.r_[True, hid[1:] != hid[:-1]])
            self.h_start = hid[st] * H_NS
            hh = np.maximum.reduceat(mh, st)
            hl = np.minimum.reduceat(ml, st)
            idx = pd.DatetimeIndex(self.h_start.astype("datetime64[ns]"))
            # max / min over the hourly bars whose start lies in (start - 28 days, start]
            self.h_max28 = pd.Series(hh, index=idx).rolling("28D").max().to_numpy()
            self.h_min28 = pd.Series(hl, index=idx).rolling("28D").min().to_numpy()

    def last_bar(self, t):
        """index of the last bar whose start is < t (-1 if none)"""
        return np.searchsorted(self.ns, np.asarray(t, np.int64), side="left") - 1

    def P(self, t):
        j = self.last_bar(t)
        return np.where(j >= 0, self.mc[np.maximum(j, 0)], np.nan)

    def spread(self, t):
        j = self.last_bar(t)
        return np.where(j >= 0, self.spr[np.maximum(j, 0)], np.nan)

    def atrd(self, t):
        j = np.searchsorted(self.atr_tk, np.asarray(t, np.int64), side="right") - 1
        return np.where(j >= 0, self.atr_v[np.maximum(j, 0)], np.nan)

    def hl20(self, t):
        """(H20, L20): extremes of the complete hourly bars that start in the 28 days before t"""
        t = np.asarray(t, np.int64)
        j = np.searchsorted(self.h_start, t - H_NS, side="right") - 1      # last bar with start + 1h <= t
        ok = j >= 0
        jj = np.maximum(j, 0)
        return np.where(ok, self.h_max28[jj], np.nan), np.where(ok, self.h_min28[jj], np.nan)


def series_ratio(tk, val, t, days=60):
    """value of a series (t_known sorted, val) at its last point known at t, divided by the median of the series
    over the `days` calendar days ending at that point."""
    tk = np.asarray(tk, np.int64)
    val = np.asarray(val, np.float64)
    ok = np.isfinite(val)
    tk, val = tk[ok], val[ok]
    if len(tk) == 0:
        n = len(np.atleast_1d(t))
        return np.full(n, np.nan), np.full(n, np.nan)
    order = np.argsort(tk, kind="stable")
    tk, val = tk[order], val[order]
    s = pd.Series(val, index=pd.DatetimeIndex(tk.astype("datetime64[ns]")))
    med = s.rolling(f"{days}D").median().to_numpy()
    j = np.searchsorted(tk, np.asarray(t, np.int64), side="right") - 1
    good = j >= 0
    jj = np.maximum(j, 0)
    cur = np.where(good, val[jj], np.nan)
    return cur, np.where(good, cur / med[jj], np.nan)


def generic(own, t, side, risk, rel=None, rel2=None):
    """Descriptors common to every sleeve. own / rel / rel2: Market objects; t: int64 ns decision times."""
    t = np.asarray(t, np.int64)
    side = np.asarray(side, np.float64)
    p = own.P(t)
    a = own.atrd(t)
    out = {"P": p, "atrd": a}
    for name, lag in (("al1", D_NS), ("al5", 7 * D_NS), ("al20", 28 * D_NS)):
        out[name] = side * (p - own.P(t - lag)) / a
    h20, l20 = own.hl20(t)
    dhi = (h20 - p) / a
    dlo = (p - l20) / a
    out["room"] = np.where(side > 0, dhi, dlo)
    out["cushion"] = np.where(side > 0, dlo, dhi)
    out["sprR"] = own.spread(t) / np.asarray(risk, np.float64)
    for nm, mk in (("rel", rel), ("rel2", rel2)):
        if mk is None:
            out[nm] = np.full(len(t), np.nan)
        else:
            out[nm] = side * (mk.P(t) - mk.P(t - D_NS)) / mk.atrd(t)
    return out


def clock(t_ns):
    ny = to_ts(t_ns).tz_convert(C.NY)
    return (ny.hour + ny.minute / 60.0).to_numpy(np.float64), ny.dayofweek.to_numpy()


def chain_context(t, chain_self, chains_other):
    """prev: R of the sleeve's last baseline trade with exit_time <= t; oth24 / oth24_n: sum and number of R of
    the other sleeves' baseline trades with exit_time in (t - 24h, t]."""
    t = np.asarray(t, np.int64)
    xs = ns_of(chain_self.exit_time)
    o = np.argsort(xs, kind="stable")
    xs, rs = xs[o], chain_self.R.to_numpy(np.float64)[o]
    j = np.searchsorted(xs, t, side="right") - 1
    prev = np.where(j >= 0, rs[np.maximum(j, 0)], np.nan)
    if len(chains_other):
        xo = np.concatenate([ns_of(c.exit_time) for c in chains_other])
        ro = np.concatenate([c.R.to_numpy(np.float64) for c in chains_other])
        o = np.argsort(xo, kind="stable")
        xo, ro = xo[o], ro[o]
        cs = np.r_[0.0, np.cumsum(ro)]
        hi = np.searchsorted(xo, t, side="right")
        lo = np.searchsorted(xo, t - D_NS, side="right")
        oth = cs[hi] - cs[lo]
        othn = (hi - lo).astype(np.float64)
    else:
        oth = np.zeros(len(t))
        othn = np.zeros(len(t))
    return {"prev": prev, "oth24": oth, "oth24_n": othn}
