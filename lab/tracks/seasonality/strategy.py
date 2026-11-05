"""Seasonality track: timed trades on XAUUSD M1 (calendar / time-of-day / weekday effects).

make_orders(m1, **params) -> orders DataFrame for goldlab.simulate.  Works on ANY M1 frame
(IS, VAL, 2026 holdout, live) because it only uses wall-clock times, the M1 bars themselves
and past-only indicators (ATR of completed 1h bars).

Timed trade on chosen weekday(s):
  * decision at `entry_time` (local `entry_tz` clock, DST-aware), entry at the first M1 bar
    starting at/after it (market) or a buy/sell LIMIT placed then (etype 2) valid
    `limit_min` minutes at  last_bid - limit_off*ATR (long) / last_ask + limit_off*ATR (short);
  * forced exit at `exit_time` on the entry date + `exit_days` calendar days (local `exit_tz`);
  * protective stop  stop_atr * ATR(atr_n) of completed 1h bars (known at decision time).
  * a trade is skipped if the market is not open at the decision time (holiday, or one of the
    ~60 data-hole days of the Dukascopy files) or, for same-day exits, if the market closes
    before the exit time (known early-close days; live: use the broker's session calendar).

FINALISTS at the bottom (chosen on IS 2013-2021 only).
"""
import numpy as np
import pandas as pd

try:
    import goldlab as gl
except ImportError:  # pragma: no cover
    import os
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    import goldlab as gl

TZ = {"NY": "America/New_York", "LDN": "Europe/London", "UTC": "UTC"}
_cache = {}


def _h1_atr(m1, n):
    key = (id(m1), len(m1), m1.index[0], m1.index[-1], n)
    if key not in _cache:
        _cache.clear()
        h1 = gl.bars(m1, "1h")
        a = gl.atr(h1, n)
        _cache[key] = (h1["t_close"].values.astype("datetime64[ns]").astype(np.int64), a.to_numpy())
    return _cache[key]


def _local_ts(dates, hhmm, tz):
    h, m = (int(x) for x in hhmm.split(":"))
    d = pd.DatetimeIndex(dates).tz_localize(None).normalize()
    loc = (d + pd.Timedelta(hours=h, minutes=m)).tz_localize(TZ[tz], nonexistent="shift_forward", ambiguous=True)
    return loc.tz_convert("UTC")


def make_orders(m1, entry_time="13:30", entry_tz="NY", weekdays=(4,), exit_time="16:45", exit_tz="NY",
                exit_days=0, side=1, stop_atr=3.0, atr_n=14, entry="market", limit_off=0.0, limit_min=60,
                cond=None, tol_min=5):
    """Build timed-trade orders. Returns a DataFrame accepted by goldlab.simulate."""
    if len(m1) == 0:
        return pd.DataFrame(columns=["entry_i", "side", "stop_dist", "exit_i"])
    ns = m1.index.values.astype("datetime64[ns]").astype(np.int64)
    # candidate calendar dates (local entry clock) between first and last bar
    loc0 = m1.index[0].tz_convert(TZ[entry_tz]).tz_localize(None).normalize()
    loc1 = m1.index[-1].tz_convert(TZ[entry_tz]).tz_localize(None).normalize()
    dates = pd.date_range(loc0, loc1, freq="D")
    dates = dates[np.isin(dates.dayofweek, list(weekdays))]
    t0 = _local_ts(dates, entry_time, entry_tz)
    t0n = t0.values.astype("datetime64[ns]").astype(np.int64)
    ei = np.searchsorted(ns, t0n, side="left")
    ok = ei < len(ns)
    ok[ok] &= (ns[ei[ok]] - t0n[ok]) <= tol_min * 60_000_000_000  # market open at decision time
    ok &= ei > 0
    # forced exit
    t1 = _local_ts(dates + pd.Timedelta(days=exit_days), exit_time, exit_tz)
    t1n = t1.values.astype("datetime64[ns]").astype(np.int64)
    xi = np.searchsorted(ns, t1n, side="left")
    if exit_days == 0:  # same-day exit: skip known early-close days (no bar near the exit time)
        okx = xi < len(ns)
        okx[okx] &= (ns[xi[okx]] - t1n[okx]) <= 10 * 60_000_000_000
        ok &= okx
    ok &= xi > ei
    # ATR of completed 1h bars at decision time
    tc, a = _h1_atr(m1, atr_n)
    j = np.searchsorted(tc, t0n, side="right") - 1
    ok &= j >= atr_n
    atr = np.where(j >= 0, a[np.maximum(j, 0)], np.nan)
    ok &= np.isfinite(atr) & (atr > 0)
    if cond is not None:
        ok &= _condition(m1, ns, cond, t0n, ei, dates, entry_tz)
    ei, xi, atr, t0n = ei[ok], xi[ok], atr[ok], t0n[ok]
    o = pd.DataFrame({"entry_i": ei.astype(np.int64), "side": int(side), "stop_dist": stop_atr * atr,
                      "exit_i": np.minimum(xi, len(ns) - 1).astype(np.int64)})
    o["tag"] = f"{entry_tz}{entry_time}->{exit_tz}{exit_time}+{exit_days}d"
    o["atr"] = atr
    if entry == "limit":
        last_bid = m1["bc"].to_numpy()[ei - 1]
        last_ask = m1["ac"].to_numpy()[ei - 1]
        o["etype"] = 2
        o["level"] = np.where(side > 0, last_bid - limit_off * atr, last_ask + limit_off * atr)
        exp_t = t0n + int(limit_min) * 60_000_000_000
        o["expiry_i"] = np.minimum(np.searchsorted(ns, exp_t, side="left") - 1, o["exit_i"].to_numpy() - 1)
        o = o[o["expiry_i"] >= o["entry_i"]]
    return o.reset_index(drop=True)


def _condition(m1, ns, cond, t0n, ei, dates, entry_tz):
    """Optional causal filters (only info before the decision time)."""
    mid_c = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2
    px0 = mid_c[np.maximum(ei - 1, 0)]
    if cond in ("week_down", "week_up"):
        # week open = first bar at/after Sunday 18:00 NY of the same week
        sun = pd.DatetimeIndex(dates) - pd.to_timedelta((pd.DatetimeIndex(dates).dayofweek + 1) % 7, unit="D")
        tw = _local_ts(sun, "18:00", "NY").values.astype("datetime64[ns]").astype(np.int64)
        iw = np.minimum(np.searchsorted(ns, tw, side="left"), len(ns) - 1)
        pw = (m1["bo"].to_numpy()[iw] + m1["ao"].to_numpy()[iw]) / 2
        valid = iw < ei
        return valid & ((px0 < pw) if cond == "week_down" else (px0 > pw))
    raise ValueError(f"unknown cond {cond}")


# Chosen on IS (2013-2021) only, BEFORE any validation access (2026-11-05).
# NOTE: neither passes the pre-registered IS criteria (PF in R 1.04 / 0.95 < 1.20, t < 2, years 4/9);
# they are the best-supported seasonal effect of the track (gold-specific Friday-afternoon / weekend
# drift, t~5 gross) and are carried to VAL for information only.  Not deployable as such.
FINALISTS = {
    # buy-limit at last bid, Friday 13:30 NY (valid 60 min) -> exit Sunday 22:00 NY (Mon 03:00 London)
    "WKND_LIM": dict(entry_time="13:30", entry_tz="NY", weekdays=(4,), exit_time="22:00", exit_tz="NY",
                     exit_days=2, side=1, stop_atr=3.0, atr_n=14, entry="limit", limit_off=0.0, limit_min=60),
    # same entry, exit Friday 16:45 NY (before the weekly close; no weekend gap, no swap)
    "FRI_PM_LIM": dict(entry_time="13:30", entry_tz="NY", weekdays=(4,), exit_time="16:45", exit_tz="NY",
                       exit_days=0, side=1, stop_atr=3.0, atr_n=14, entry="limit", limit_off=0.0, limit_min=60),
}
