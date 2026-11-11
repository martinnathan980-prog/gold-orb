"""Daily-scale mean reversion on index CFDs (round 3, track `dip`).

    make_orders(m1, **params) -> orders DataFrame for goldlab.simulate (market entries only)

The rule, written so it can be coded as an MT5 Expert Advisor:

  * "cash session" of day D (local clock, DST-aware): sess="us" -> 09:30-16:00 New York (us500, us100, us30);
    sess="eu" -> 09:00-17:30 Berlin (ger40, Xetra hours).  Its open/high/low/close are taken from the mid
    prices of the M1 bars that START inside the session (the last one is the 15:59 bar, complete at 16:00).
    A session enters the indicator series if it has >= 120 M1 bars and its first bar starts within 10 min
    of the open (half-days are kept; holidays / data holes are not).
  * decision at the session close C (16:00 NY / 17:30 Berlin) using only bars that have closed; the day is
    TRADABLE if the session has >= 75 % of its minutes, its last bar starts >= C-10 min and the CFD has a
    bar starting in [C, C+10 min) on the same local date: that bar is the entry/exit bar (market, at its open).
  * signal (long; the mirror rule `side=-1` uses the symmetric condition and sells):
        "ibs"   IBS = (close-low)/(high-low) of today's session  <  thr          (short: > 1-thr)
        "rsi2"  Wilder RSI(2) of session closes  <  thr                          (short: > 100-thr)
        "down3" `thr` consecutive lower session closes (default 3)              (short: higher closes)
        "bb"    close < SMA20 - 2*SD20 of session closes                         (short: > SMA20 + 2*SD20)
    optional trend filter `trend=True`: close > SMA200 of session closes (short: close < SMA200).
  * entry: market at the open of the entry bar (entry="close"), or -- swap-free form, US only --
    entry="1830": at the first bar at/after 18:30 New York the same evening (after the 17:00 NY rollover,
    away from the wide reopen spread); that form always exits at the next tradable session close
    (16:00 NY next business day, before the 17:00 rollover: no swap).
  * protective stop: `stop_atr` x ATR(14) of the session series (Wilder, true range with the previous session
    close, today's session included), fixed distance from the fill.
  * exit at the open of the entry bar of the first LATER tradable session whose close satisfies `exit`:
        "hi"    close > previous session's high      (short: close < previous session's low)
        "up"    close > previous session's close     (short: lower close)
        "sma5"  close > SMA5 of session closes        (short: below)
        "time"  no rule exit
    or, at the latest (time stop, hold <= 5), at the open of the first bar at/after the close time C of the
    day `hold` business days after the entry date (if the market is shut then: the last bar before the
    closure).
  * orders only for entry dates >= `start` (index data before 2014 is incomplete).

Built only from the frame received; strictly causal (see causality.py).  FINALISTS at the bottom.
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

SESS = {"us": ("America/New_York", 570, 960), "eu": ("Europe/Berlin", 540, 1050)}


def sessions(m1, sess="us"):
    """Cash-session bars (one row per local date) with the entry-bar index of the close decision."""
    tz, o, c = SESS[sess]
    loc = gl.local(m1.index, tz)
    mod = (loc.hour * 60 + loc.minute).to_numpy()
    day = loc.tz_localize(None).normalize().to_numpy()
    ins = (mod >= o) & (mod < c)
    pos = np.flatnonzero(ins)
    mid = {k: (m1["b" + k].to_numpy()[pos] + m1["a" + k].to_numpy()[pos]) / 2 for k in "ohlc"}
    g = pd.DataFrame({"day": day[pos], "pos": pos, "mod": mod[pos], **mid}).groupby("day", sort=True)
    s = pd.DataFrame({"first_pos": g["pos"].first(), "last_pos": g["pos"].last(), "nmin": g["pos"].size(),
                      "first_mod": g["mod"].first(), "last_mod": g["mod"].last(),
                      "o": g["o"].first(), "h": g["h"].max(), "l": g["l"].min(), "c": g["c"].last()})
    s = s[(s.nmin >= 120) & (s.first_mod <= o + 10)].copy()
    n = len(m1)
    nxt = s.last_pos.to_numpy() + 1
    ok_n = nxt < n
    nxt_c = np.minimum(nxt, n - 1)
    same_day = day[nxt_c] == s.index.to_numpy()
    in_win = (mod[nxt_c] >= c) & (mod[nxt_c] < c + 10)
    s["entry_i"] = np.where(ok_n & same_day & in_win, nxt, -1)
    s["tradable"] = (s.entry_i >= 0) & (s.nmin >= 0.75 * (c - o)) & (s.last_mod >= c - 10)
    pc = s.c.shift(1)
    tr = np.maximum(s.h, pc) - np.minimum(s.l, pc)
    tr = tr.fillna(s.h - s.l)
    s["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    return s


def _rsi(c, n=2):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def signals(s, signal="ibs", thr=0.2, side=1, trend=False):
    c = s.c
    if signal == "ibs":
        ibs = (c - s.l) / (s.h - s.l).replace(0, np.nan)
        sig = ibs < thr if side > 0 else ibs > 1 - thr
    elif signal == "rsi2":
        r = _rsi(c, 2)
        sig = r < thr if side > 0 else r > 100 - thr
    elif signal == "down3":
        k = int(thr)
        d = np.sign(c.diff())
        run = (d == -side).astype(int).rolling(k).sum()
        sig = run >= k
    elif signal == "bb":
        m, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
        sig = c < m - 2 * sd if side > 0 else c > m + 2 * sd
    else:
        raise ValueError(signal)
    if trend:
        sma = c.rolling(200).mean()
        sig &= (c > sma) if side > 0 else (c < sma)
    return sig.fillna(False).to_numpy(bool)


def exit_cond(s, exit="hi", side=1):
    c = s.c
    if exit == "hi":
        e = c > s.h.shift(1) if side > 0 else c < s.l.shift(1)
    elif exit == "up":
        e = c > c.shift(1) if side > 0 else c < c.shift(1)
    elif exit == "sma5":
        m = c.rolling(5).mean()
        e = c > m if side > 0 else c < m
    elif exit == "time":
        e = pd.Series(False, index=s.index)
    else:
        raise ValueError(exit)
    return e.fillna(False).to_numpy(bool)


def make_orders(m1, sess="us", signal="ibs", thr=0.2, side=1, trend=False, exit="hi", hold=5,
                stop_atr=2.5, entry="close", start="2014-01-01"):
    assert 1 <= hold <= 5
    s = sessions(m1, sess)
    cols = ["entry_i", "side", "stop_dist", "exit_i"]
    if len(s) < 30:
        return pd.DataFrame(columns=cols)
    sig = signals(s, signal, thr, side, trend)
    ex = exit_cond(s, exit, side)
    trad = s.tradable.to_numpy()
    ent = s.entry_i.to_numpy()
    days = s.index.to_numpy().astype("datetime64[D]")
    atr = s.atr.to_numpy()
    n = len(m1)
    ok_start = days >= np.datetime64(start, "D")
    rows = []
    tz, _, cmin = SESS[sess]
    if entry == "1830":
        assert sess == "us"
        t1830 = (pd.DatetimeIndex(s.index) + pd.Timedelta(minutes=18 * 60 + 30)).tz_localize(tz, ambiguous=True,
                                                                                               nonexistent="shift_forward")
        e1830 = gl.entry_index(m1, t1830)
        loc_day = gl.local(m1.index, tz).tz_localize(None).normalize().to_numpy()
    for j in np.flatnonzero(sig & trad & ok_start):
        if entry == "close":
            ei = ent[j]
            # time stop: the close C of the day `hold` business days after the entry date
            # (inside a closure -> the last bar before it)
            ts = pd.Timestamp(np.busday_offset(days[j], hold, roll="forward"))
            xi = int(gl.exit_index(m1, pd.DatetimeIndex([ts + pd.Timedelta(minutes=cmin)]).tz_localize(tz))[0])
            xi = min(max(xi, ei + 1), n - 1)
            for k in range(j + 1, len(s)):
                if days[k] >= np.datetime64(ts, "D"):
                    break
                if trad[k] and ex[k]:
                    xi = min(xi, ent[k])
                    break
        else:
            # swap-free form: no entry on Friday evening (the next session is after a weekend)
            if pd.Timestamp(days[j]).weekday() == 4:
                continue
            ei = int(e1830[j])
            if ei >= n:
                continue
            lt = m1.index[ei].tz_convert(tz)
            if loc_day[ei] != s.index[j] or (lt.hour * 60 + lt.minute) > 19 * 60:
                continue
            nd = pd.Timestamp(np.busday_offset(days[j], 1, roll="forward"))
            t16 = pd.DatetimeIndex([nd + pd.Timedelta(minutes=16 * 60)]).tz_localize(tz)
            xi = int(gl.exit_index(m1, t16)[0])   # 16:00 NY next business day (closure -> last bar before it)
            if xi <= ei:
                xi = ei + 1
        rows.append((ei, side, stop_atr * atr[j], xi))
    o = pd.DataFrame(rows, columns=cols)
    o = o[(o.entry_i < n)].astype({"entry_i": np.int64, "side": np.int64, "exit_i": np.int64})
    return o.reset_index(drop=True)


# No finalist: every candidate failed the random-entry null and did not replicate (results/r2/dip/finalists_preval.json).
FINALISTS = {}
