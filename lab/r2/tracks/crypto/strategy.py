"""Track `crypto` (round 2): rules on btcusd / ethusd CFDs, built on H1 bars of MID prices (UTC hour grid).

`make_orders(m1, **params)` returns a causal orders frame for goldlab.simulate on ANY M1 bid/ask frame
(columns bo bh bl bc ao ah al ac, UTC index).  All decisions are taken at the scheduled END of an H1 bar
(bar start + 60 min) from bars that are complete at that time; the order is a MARKET order at the open of the
first M1 bar at/after the decision time (skipped if no M1 bar exists within `max_delay_min`: market closed or
data hole).  Only whole-hour bars are used so that the rule is identical on any MT5 server clock.

Building blocks (all on H1 mid bars, "bars" = consecutive EXISTING H1 bars; hours without any quote are skipped):
  ATR      simple mean of the true range of the last `atr_n` bars (same definition as MT5's iATR).
  family="brk"   close-channel breakout: long if the close of the bar just finished is ABOVE the highest
                 close of the previous `n` bars, short if BELOW the lowest close of the previous `n` bars.
                 Optional filters: `vc_max` (volatility compression: ATR(atr_n) / ATR(vc_long) <= vc_max),
                 `dow` ("all" | "weekday" | "weekend", UTC day of the decision), `h_from`/`h_to` (UTC hour of
                 the decision in [h_from, h_to)), `gap_bars` (no same-direction signal in the previous
                 `gap_bars` bars: keeps only the first breakout of a run).
  family="sess"  timed momentum: at UTC hour `dec_h` every day, side = sign(close now - close `look_h` hours
                 earlier); optional minimum move `thr_atr` (in ATR units).
  family="pull"  pullback in a trend: trend = sign(close - close `trend_n` bars earlier); enter WITH the trend
                 when the close just made a new `pb_n`-bar extreme AGAINST it (new low close in an up-trend,
                 new high close in a down-trend).
Exits (engine): initial stop `stop_atr` x ATR from the fill; optional trailing stop `trail_atr` x ATR from the
best price since entry (updated at each M1 close); optional target `target_atr` x ATR; time exit `hold_h`
hours after the decision (market, at the open of the first M1 bar at/after that time).

Only "brk" (with dow="weekday") and "sess" (with dow="weekday") became finalists; "pull", the trailing exit and
the filters vc_max / gap_bars / h_from / h_to / thr_atr / target_atr were exploratory or diagnostic.

Causality: every indicator uses complete bars only (the last bar of the frame is used only if the frame
reaches its scheduled end); rolling windows look back only; no whole-sample statistic.  Checked by the
truncation test in `causality_check.py`.
Warm-up: the first decision needs max(n, vc_long, trend_n, atr_n) + 1 complete bars (finite memory: the
orders do not depend on where the frame starts beyond that).
"""
import math

import numpy as np
import pandas as pd

H_MS = 3_600_000
M_MS = 60_000

DEFAULTS = {
    "family": "brk",
    # breakout
    "n": 72, "gap_bars": 0, "vc_max": float("nan"), "vc_long": 240,
    # timed momentum
    "dec_h": 8, "look_h": 8, "thr_atr": 0.0,
    # pullback
    "trend_n": 168, "pb_n": 12,
    # common
    "atr_n": 24, "stop_atr": 3.0, "trail_atr": float("nan"), "target_atr": float("nan"), "hold_h": 24,
    "sides": "both", "dow": "all", "h_from": 0, "h_to": 24, "max_delay_min": 5,
    # execution-delay probe only (0 for every rule): the market order is sent `delay_min` minutes after the decision
    "delay_min": 0,
}


def _nan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def _p(params):
    unknown = set(params) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown params {unknown}")
    p = dict(DEFAULTS)
    p.update(params)
    if float(p["hold_h"]) > 120:
        raise ValueError("max hold must be <= 5 days")
    return p


def ts_ms(m1):
    """M1 bar start times as int64 milliseconds since the epoch (UTC)."""
    idx = m1.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx.values.astype("datetime64[ms]").astype(np.int64)


def h1_bars(m1):
    """Complete H1 bars (UTC hour grid, labelled by START) of mid prices.  Returns a DataFrame with columns
    start (ms), o, h, l, c, cnt (number of M1 rows).  The last hour of the frame is kept only if the frame
    contains its last minute (so a bar is never used before its scheduled end)."""
    ts = ts_ms(m1)
    hs = ts // H_MS
    first = np.r_[0, np.flatnonzero(np.diff(hs)) + 1]
    last = np.r_[first[1:] - 1, len(ts) - 1]
    mo = (m1["bo"].to_numpy(np.float64) + m1["ao"].to_numpy(np.float64)) / 2
    mh = (m1["bh"].to_numpy(np.float64) + m1["ah"].to_numpy(np.float64)) / 2
    ml = (m1["bl"].to_numpy(np.float64) + m1["al"].to_numpy(np.float64)) / 2
    mc = (m1["bc"].to_numpy(np.float64) + m1["ac"].to_numpy(np.float64)) / 2
    b = pd.DataFrame({"start": hs[first] * H_MS, "o": mo[first], "h": np.maximum.reduceat(mh, first),
                      "l": np.minimum.reduceat(ml, first), "c": mc[last], "cnt": last - first + 1})
    if len(b) and b["start"].iloc[-1] + H_MS > ts[-1] + M_MS:
        b = b.iloc[:-1]
    return b.reset_index(drop=True)


def sma_atr(b, n):
    """Mean true range of the last n bars (MT5 iATR definition), NaN until n bars exist."""
    pc = b["c"].shift(1)
    tr = np.maximum(b["h"] - b["l"], np.maximum((b["h"] - pc).abs(), (b["l"] - pc).abs()))
    tr.iloc[0] = b["h"].iloc[0] - b["l"].iloc[0] if len(b) else np.nan
    return tr.rolling(int(n)).mean()


def _finish(m1, p, dec_ms, side, atr, extra=None):
    """Market orders from decisions known at `dec_ms` (ms UTC)."""
    ts = ts_ms(m1)
    dec_ms = np.asarray(dec_ms, np.int64)
    side = np.asarray(side, np.int64)
    atr = np.asarray(atr, np.float64)
    send_ms = dec_ms + int(p["delay_min"]) * M_MS
    ei = np.searchsorted(ts, send_ms, side="left").astype(np.int64)
    inside = ei < len(ts)
    eic = np.clip(ei, 0, len(ts) - 1)
    ok = inside & (ts[eic] - send_ms <= int(p["max_delay_min"]) * M_MS)
    exit_ms = dec_ms + int(round(float(p["hold_h"]) * 60)) * M_MS
    # first M1 bar at/after the scheduled exit; == len(ts) when the frame ends before it (the engine then
    # closes the trade on the last bar of the frame): the order itself never depends on later data
    xi = np.searchsorted(ts, exit_ms, side="left").astype(np.int64)
    ok &= np.isfinite(atr) & (atr > 0) & (xi > ei)
    if p["sides"] == "long":
        ok &= side > 0
    elif p["sides"] == "short":
        ok &= side < 0
    ok &= side != 0
    dt = pd.to_datetime(dec_ms, unit="ms", utc=True)
    if p["dow"] == "weekday":
        ok &= np.asarray(dt.dayofweek < 5)
    elif p["dow"] == "weekend":
        ok &= np.asarray(dt.dayofweek >= 5)
    hr = np.asarray(dt.hour)
    ok &= (hr >= int(p["h_from"])) & (hr < int(p["h_to"]))
    o = pd.DataFrame({
        "entry_i": ei, "side": side, "etype": 0,
        "stop_dist": atr * float(p["stop_atr"]),
        "exit_i": xi,
        "trail": np.nan if _nan(p["trail_atr"]) else atr * float(p["trail_atr"]),
        "target_dist": np.nan if _nan(p["target_atr"]) else atr * float(p["target_atr"]),
        # NB: never name an extra column like an engine output (entry_time, exit_time, ...): extras are copied
        # into the trades frame and would overwrite it
        "dec_time": dt, "sched_exit": pd.to_datetime(exit_ms, unit="ms", utc=True), "atr": atr,
    })
    if extra:
        for k, v in extra.items():
            o[k] = np.asarray(v)
    return o[ok].sort_values("entry_i", kind="stable").reset_index(drop=True)


def _brk(m1, p):
    b = h1_bars(m1)
    n = int(p["n"])
    c = b["c"]
    hi = c.rolling(n).max().shift(1)
    lo = c.rolling(n).min().shift(1)
    side = np.where(c > hi, 1, np.where(c < lo, -1, 0))
    atr = sma_atr(b, int(p["atr_n"]))
    keep = side != 0
    s = pd.Series(side)
    g = int(p["gap_bars"])
    if g > 0:
        prev_same = np.zeros(len(s), bool)
        for k in range(1, g + 1):
            prev_same |= (s.shift(k) == s).to_numpy()
        keep &= ~prev_same
    vc = (atr / sma_atr(b, int(p["vc_long"]))).to_numpy()
    if not _nan(p["vc_max"]):
        keep &= vc <= float(p["vc_max"])
    # diagnostics carried to the trades frame (not used by the rule): compression ratio, whether the previous
    # bar already was a same-direction signal, size of the break in ATR
    prev1 = (s.shift(1) == s).to_numpy()
    over = np.where(side > 0, c - hi, lo - c) / atr
    extra = {"vc": vc[keep], "prev1": prev1[keep], "over_atr": over.to_numpy()[keep]}
    b, side, atr = b[keep], side[keep], atr[keep]
    return _finish(m1, p, b["start"].to_numpy() + H_MS, side, atr.to_numpy(), extra=extra)


def _sess(m1, p):
    b = h1_bars(m1)
    atr = sma_atr(b, int(p["atr_n"]))
    start = b["start"].to_numpy()
    hour = (start // H_MS) % 24
    # the bar ending at dec_h (starts at dec_h - 1) and the bar ending look_h hours earlier must both exist
    sel = np.flatnonzero(hour == (int(p["dec_h"]) - 1) % 24)
    ref_start = start[sel] - int(p["look_h"]) * H_MS
    pos = np.searchsorted(start, ref_start)
    okref = (pos < len(start)) & (start[np.clip(pos, 0, len(start) - 1)] == ref_start)
    sel, pos = sel[okref], pos[okref]
    c = b["c"].to_numpy()
    move = c[sel] - c[pos]
    a = atr.to_numpy()[sel]
    side = np.sign(move).astype(np.int64)
    side[np.abs(move) < float(p["thr_atr"]) * a] = 0
    return _finish(m1, p, start[sel] + H_MS, side, a, extra={"move_atr": move / a})


def _pull(m1, p):
    b = h1_bars(m1)
    c = b["c"]
    atr = sma_atr(b, int(p["atr_n"]))
    trend = np.sign(c - c.shift(int(p["trend_n"]))).to_numpy()
    m = int(p["pb_n"])
    new_lo = (c < c.rolling(m).min().shift(1)).to_numpy()
    new_hi = (c > c.rolling(m).max().shift(1)).to_numpy()
    side = np.where((trend > 0) & new_lo, 1, np.where((trend < 0) & new_hi, -1, 0))
    keep = side != 0
    b, side, atr = b[keep], side[keep], atr[keep]
    return _finish(m1, p, b["start"].to_numpy() + H_MS, side, atr.to_numpy())


def make_orders(m1, **params):
    p = _p(params)
    fam = p["family"]
    if fam == "brk":
        return _brk(m1, p)
    if fam == "sess":
        return _sess(m1, p)
    if fam == "pull":
        return _pull(m1, p)
    raise ValueError(fam)


# Finalists chosen on in-sample data only (entries before 2022-01-01), BEFORE any validation access
# (lab/results/r2/crypto/finalists_preval.json).  Parameters frozen since then.  Single-shot validation 2022-2025
# (lab/results/r2/crypto/val_results.json): brk72_24h_wd passes the pre-registered criteria on both instruments,
# weakly (PF 1.08 BTC / 1.13 ETH, t 0.8 / 1.2, 2025 negative); sess_8_8_13_wd FAILS (PF 1.03 / 1.05) and is kept
# here only as a record.  Regenerate on any M1 frame of the market with
#   make_orders(m1, **FINALISTS[name]["params"])  then  goldlab.simulate(m1, orders, sym, costs=r2.costs(sym))
# (one position per sleeve: no_overlap=True).  Warm-up: give the frame at least 5 days of M1 data before the first
# decision you care about (73 complete H1 bars for the breakout, 24 for the session rule).
FINALISTS = {
    # Close-channel breakout, weekdays only.  At the end of every H1 bar (UTC hour grid, mid prices) whose end time
    # is on Monday-Friday UTC, if this sleeve is flat: LONG at market when the close of the bar just finished is
    # above the highest close of the previous 72 H1 bars, SHORT when it is below their lowest close.
    # Stop 3 x ATR(24) from the fill (mean true range of the last 24 H1 bars, frozen at the decision); no target,
    # no trailing; market exit 24 h after the decision.  A signal arriving while a trade is open (including the
    # minute at which that trade is closed by its time exit) is ignored; a signal is dropped if there is no quote
    # within 5 minutes after the bar end.
    "brk72_24h_wd": {"syms": ["btcusd", "ethusd"],
                     "params": {"family": "brk", "n": 72, "stop_atr": 3.0, "hold_h": 24, "dow": "weekday"}},
    # Asia -> Europe/US session momentum, weekdays only.  Every Monday-Friday at 08:00 UTC: side = sign of
    # (close of the H1 bar ending 08:00 UTC - close of the H1 bar ending 00:00 UTC); market entry; stop
    # 3 x ATR(24) from the fill; market exit at 21:00 UTC the same day.
    "sess_8_8_13_wd": {"syms": ["btcusd", "ethusd"],
                       "params": {"family": "sess", "dec_h": 8, "look_h": 8, "stop_atr": 3.0, "hold_h": 13, "dow": "weekday"}},
}
