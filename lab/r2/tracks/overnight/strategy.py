"""Overnight / session / calendar track (round 2) -- timed trades on M1 frames.

    make_orders(m1, **params) -> orders DataFrame for goldlab.simulate (market entries only)

One generic rule, simple enough for an MT5 Expert Advisor:

  * every calendar day of the local clock `tz` whose weekday is in `weekdays`, at the wall-clock time
    `entry` (DST-aware):
      - the market must be open and really trading: a bar starts within `tol_min` minutes of the decision
        time and at least `min_prev` M1 bars exist in the 30 minutes before it (this removes holidays,
        weekends, data holes and the single filler bars of the 2015-2017 Dukascopy index files);
      - optional condition `cond` (all computed from prices BEFORE the decision time):
          None               always trade, direction = `side`
          "prev_sess_down"   trade only if the previous cash session (sess_open -> sess_close, local clock)
                             closed below its open           (direction = `side`)
          "prev_sess_up"     ... closed above its open
          "fade_prev_sess"   long after a down session, short after an up session (`side` ignored)
          "sess_up"/"sess_down"  today's session so far: last price before the decision vs today's
                             sess_open price (for entries made late in the cash session)
          "month_end"        calendar only: the next weekday after the entry date is in another month
        optional `min_move_bp`: the |session move| must be at least this many basis points;
      - enter at market on the first M1 bar at/after the decision time (entry_type="market"), or place a
        limit order at the last bid (long) / last ask (short), valid `limit_min` minutes (entry_type="limit");
  * protective stop: `stop_atr` x ATR(`atr_n`) of COMPLETED bars of timeframe `atr_tf` ("1h" or "D",
    D = trading day ending 17:00 New York = the MT5 server day), Wilder smoothing;
  * forced exit at the wall-clock time `exit`: on the entry date (exit_next=False; if the market shuts
    earlier: exit on the last bar before the closure, or -- skip_early_close=True -- no trade that day)
    or on the first later day (within `max_days`) on which the market is open at that time
    (exit_next=True: "next session").

No targets, no trailing: one entry (market, or one limit order with an expiry), one stop, one time exit.
Works on any M1 frame of the market (IS, VAL, 2026 holdout, live feed).  FINALISTS at the bottom.
"""
import numpy as np
import pandas as pd

try:
    import goldlab as gl
except ImportError:  # pragma: no cover
    import os
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
    import goldlab as gl

TZ = {"NY": "America/New_York", "BER": "Europe/Berlin", "LDN": "Europe/London", "UTC": "UTC"}
MIN = 60_000_000_000  # ns per minute


def _mins(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return h * 60 + m


def _local_ns(dates, minutes, tz):
    """UTC ns of wall-clock `minutes` after local midnight on each (naive) calendar date."""
    loc = (dates + pd.Timedelta(minutes=int(minutes))).tz_localize(TZ[tz], nonexistent="shift_forward", ambiguous=True)
    return loc.tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)


def _open_at(ns, t, tol_min, min_prev):
    """First bar at/after each time t (ns) and whether the market is really trading there."""
    i = np.searchsorted(ns, t, side="left")
    ok = i < len(ns)
    ii = np.where(ok, i, 0)
    ok &= (ns[ii] - t) <= tol_min * MIN
    j = np.searchsorted(ns, t - 30 * MIN, side="left")
    ok &= (ii - j) >= min_prev
    return ii, ok


def _atr(m1, ns, tf, n):
    """Wilder ATR on mid prices of completed bars. Returns (time at which each bar is complete [ns], atr)."""
    bh, ah, bl, al = (m1[k].to_numpy() for k in ("bh", "ah", "bl", "al"))
    mc = ((m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2)
    if tf == "1h":
        key = ns // (60 * MIN)
        start = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
        done = (key[start] + 1) * 60 * MIN                    # nominal end of the hour (never earlier)
        keep = np.ones(len(start), bool)
    elif tf == "D":
        td = gl.trading_day(m1.index).values.astype("datetime64[D]").astype(np.int64)
        start = np.r_[0, np.flatnonzero(np.diff(td)) + 1]
        end = np.r_[start[1:], len(ns)]
        done = ns[end - 1] + MIN                              # last bar of the trading day + 1 minute
        keep = (end - start) >= 600                           # full days only (no holiday stubs)
    else:
        raise ValueError(tf)
    # mid high / low of a bar = mean of the bid and ask extremes (same convention as goldlab.bars)
    h = ((np.maximum.reduceat(bh, start) + np.maximum.reduceat(ah, start)) / 2)[keep]
    l = ((np.minimum.reduceat(bl, start) + np.minimum.reduceat(al, start)) / 2)[keep]
    c = mc[np.r_[start[1:], len(ns)] - 1][keep]
    done = done[keep]
    pc = np.r_[np.nan, c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))   # same formula as goldlab.atr (first bar NaN)
    atr = pd.Series(tr).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy().copy()
    atr[:n] = np.nan                                          # warm-up
    return done, atr


def make_orders(m1, tz="NY", entry="17:05", exit="19:00", exit_next=False, weekdays=(0, 1, 2, 3, 4, 5, 6), side=1,
                stop_atr=2.0, atr_n=14, atr_tf="1h", cond=None, sess_open="09:30", sess_close="16:00",
                min_move_bp=0.0, tol_min=5, min_prev=10, max_days=4, entry_type="market", limit_min=30,
                skip_early_close=False):
    cols = ["entry_i", "side", "stop_dist", "exit_i"]
    if len(m1) < 3000:
        return pd.DataFrame({c: pd.Series(dtype="int64" if c != "stop_dist" else "float64") for c in cols})
    ns = m1.index.values.astype("datetime64[ns]").astype(np.int64)
    n_bars = len(ns)
    mo = (m1["bo"].to_numpy() + m1["ao"].to_numpy()) / 2
    mc = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2
    d0 = m1.index[0].tz_convert(TZ[tz]).tz_localize(None).normalize()
    d1 = m1.index[-1].tz_convert(TZ[tz]).tz_localize(None).normalize()
    dates = pd.date_range(d0, d1, freq="D")
    nd = len(dates)
    dow = dates.dayofweek.to_numpy()
    e_min, x_min = _mins(entry), _mins(exit)

    # ---- entry
    t0 = _local_ns(dates, e_min, tz)
    ei, ok = _open_at(ns, t0, tol_min, min_prev)
    ok &= np.isin(dow, list(weekdays)) & (ei > 0)

    # ---- exit (if the exit time lies beyond the end of the frame -- live edge -- the order is kept, exit unknown)
    if not exit_next:
        if x_min <= e_min:
            raise ValueError("same-day exit must be later than the entry (use exit_next=True)")
        t1 = _local_ns(dates, x_min, tz)
        beyond = t1 > ns[-1]
        if skip_early_close:
            # round-1 gold definition: no trade on days when the market is shut at the exit time. Early closes are
            # scheduled (in this data: the Friday after US Thanksgiving) -- an EA uses the calendar; here the day is
            # recognised by the absence of quotes at the exit time.
            xi = np.searchsorted(ns, t1, side="left")
            known = xi < n_bars
            shut = np.zeros(nd, bool)
            shut[known] = (ns[xi[known]] - t1[known]) > 10 * MIN
            ok &= ~shut
        else:                     # otherwise: exit on the last bar before the closure
            xi = gl.exit_index(m1, pd.DatetimeIndex(t1.astype("datetime64[ns]"), tz="UTC"))
    else:
        xi = np.full(nd, -1, np.int64)
        for k in range(1, max_days + 1):
            tk = _local_ns(dates + pd.Timedelta(days=k), x_min, tz)
            ik, okk = _open_at(ns, tk, tol_min, min_prev)
            take = (xi < 0) & okk
            xi[take] = ik[take]
        miss = xi < 0                                         # market never open at that time: last resort
        tl = _local_ns(dates + pd.Timedelta(days=max_days), x_min, tz)
        beyond = miss & (tl > ns[-1])
        if miss.any():
            xi[miss] = gl.exit_index(m1, pd.DatetimeIndex(tl.astype("datetime64[ns]"), tz="UTC"))[miss]
    xi = np.where(beyond, n_bars - 1, np.minimum(xi, n_bars - 1))
    ok &= (xi > ei) | beyond

    # ---- stop distance: ATR of completed bars known at the decision time
    done, atr = _atr(m1, ns, atr_tf, atr_n)
    j = np.searchsorted(done, t0, side="right") - 1
    a = np.where(j >= 0, atr[np.maximum(j, 0)], np.nan)
    ok &= np.isfinite(a) & (a > 0)

    # ---- condition
    sd = np.full(nd, int(side), np.int64)
    if cond is not None:
        so, sc = _mins(sess_open), _mins(sess_close)
        io, oko = _open_at(ns, _local_ns(dates, so, tz), tol_min, min_prev)
        p_open = np.where(oko, mo[io], np.nan)                               # session open price of each date
        if cond in ("prev_sess_down", "prev_sess_up", "fade_prev_sess"):
            tc = _local_ns(dates, sc, tz)
            jc = np.searchsorted(ns, tc, side="left") - 1                    # last bar that started before the close
            okc = (jc >= 0) & ((tc - ns[np.maximum(jc, 0)]) <= (tol_min + 1) * MIN)
            p_close = np.where(okc, mc[np.maximum(jc, 0)], np.nan)
            ret = p_close / p_open - 1.0                                     # NaN if the session is incomplete
            valid = np.isfinite(ret)
            last = np.maximum.accumulate(np.where(valid, np.arange(nd), -1))
            prev = np.r_[-1, last[:-1]]                                      # most recent complete session BEFORE date d
            pr = np.where(prev >= 0, ret[np.maximum(prev, 0)], np.nan)
            pr = np.where((np.arange(nd) - prev) <= 5, pr, np.nan)           # not older than 5 calendar days
            sig = pr
        elif cond in ("sess_up", "sess_down"):
            if not (so < e_min):
                raise ValueError("sess_up/sess_down need sess_open before the entry time")
            p_now = mc[np.maximum(ei - 1, 0)]                                # last close before the decision
            sig = p_now / p_open - 1.0
        elif cond == "month_end":
            # calendar only: the next weekday (Mon-Fri) after this date falls in another month
            nxt = dates + pd.to_timedelta(np.where(dow == 4, 3, np.where(dow == 5, 2, 1)), unit="D")
            sig = np.where(nxt.month.to_numpy() != dates.month.to_numpy(), 1.0, np.nan)
        else:
            raise ValueError(f"unknown cond {cond}")
        ok &= np.isfinite(sig) & (np.abs(sig) * 1e4 >= float(min_move_bp)) & (sig != 0)
        if cond in ("prev_sess_down", "sess_down"):
            ok &= sig < 0
        elif cond in ("prev_sess_up", "sess_up"):
            ok &= sig > 0
        elif cond == "fade_prev_sess":
            sd = np.where(sig < 0, 1, -1).astype(np.int64)

    o = pd.DataFrame({"entry_i": ei[ok].astype(np.int64), "side": sd[ok], "stop_dist": stop_atr * a[ok],
                      "exit_i": xi[ok].astype(np.int64)})
    if entry_type == "limit":
        # passive entry: limit at the last bid (long) / last ask (short) seen before the decision time,
        # valid `limit_min` minutes; not filled -> no trade that day
        e = o["entry_i"].to_numpy()
        o["etype"] = 2
        o["level"] = np.where(o["side"].to_numpy() > 0, m1["bc"].to_numpy()[e - 1], m1["ac"].to_numpy()[e - 1])
        last = np.searchsorted(ns, t0[ok] + int(limit_min) * MIN, side="left") - 1
        o["expiry_i"] = np.where(beyond[ok], last, np.minimum(last, o["exit_i"].to_numpy() - 1)).astype(np.int64)
        o = o[o["expiry_i"] >= o["entry_i"]]
    elif entry_type != "market":
        raise ValueError(entry_type)
    return o.reset_index(drop=True)


# ----------------------------------------------------------------------------------------------------------
# FINALISTS -- chosen on the in-sample period only (entries before 2022-01-01), BEFORE any validation access
# (decision recorded in results/r2/overnight/finalists_preval.json, 2026-11-10).
#
# GOLD_FRI_PM      the round-1 gold "Friday afternoon" rule (seasonality track, FRI_PM_LIM), parameters
#                  untouched, re-checked under FP costs as the ONE pre-declared trial of this track.
#                  Fridays: buy-limit at the last bid seen before 13:30 New York, valid 60 minutes;
#                  stop 3 x ATR(14) of completed 1h bars; exit 16:45 New York; no trade on early-close days.
#                  (make_orders reproduces the round-1 orders exactly.)  Timing effect, not beta.
# MONTH_END_NIGHT  on the last weekday of the month, 5 minutes before the cash close of the index's own
#                  exchange, buy at market; stop 1 x ATR(14) of completed daily bars; exit at the next cash
#                  open.  One rule, one parameter set; the session clock is the exchange's own:
#                  us500 / us100: 15:55 -> next 09:30 New York;  ger40: 17:25 -> next 09:00 Frankfurt.
#                  Judged as a basket (PROTOCOL_V2 section 4).  A long index position held one night a
#                  month: in a crash it behaves like a leveraged long (stop at 1 daily ATR).
# ----------------------------------------------------------------------------------------------------------
_WD = (0, 1, 2, 3, 4)
_ME_COMMON = dict(exit_next=True, weekdays=_WD, side=1, stop_atr=1.0, atr_n=14, atr_tf="D", cond="month_end")
_ME_US = dict(tz="NY", entry="15:55", exit="09:30", **_ME_COMMON)
_ME_DE = dict(tz="BER", entry="17:25", exit="09:00", sess_open="09:00", sess_close="17:30", **_ME_COMMON)

FINALISTS = {
    "GOLD_FRI_PM": {
        "syms": ["xauusd"],
        "params": dict(tz="NY", entry="13:30", exit="16:45", weekdays=(4,), side=1, stop_atr=3.0, atr_n=14, atr_tf="1h",
                       entry_type="limit", limit_min=60, min_prev=0, skip_early_close=True),
    },
    "MONTH_END_NIGHT": {
        "syms": ["us500", "us100", "ger40"],
        "params": _ME_US,                          # us500, us100 (New-York session clock)
        "params_by_sym": {"ger40": _ME_DE},        # same rule on the Frankfurt session clock
    },
}


def finalist_params(name, sym):
    """Parameters of finalist `name` for instrument `sym` (the session clock depends on the exchange)."""
    f = FINALISTS[name]
    return dict(f.get("params_by_sym", {}).get(sym, f["params"]))


def finalist_orders(name, sym, m1):
    return make_orders(m1, **finalist_params(name, sym))
