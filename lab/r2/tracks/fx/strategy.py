"""Track `fx` (round 3): rules on the eight FP Markets currency pairs.

`make_orders(m1, **params)` returns a causal orders frame for goldlab.simulate on ANY M1 bid/ask frame (UTC index,
columns bo bh bl bc ao ah al ac).  All signals use MID prices (bid+ask)/2 of the frame received.  Clock times are
London wall-clock times (Europe/London, DST-aware), weekdays only.

Common pieces
  decision time T   London clock time on a London weekday.  The price "at T" is the mid close of the last M1 bar
                    that STARTS before T (i.e. the bar that closes at T), and must be at most 5 minutes old.
  entry             market order at the open of the first M1 bar at/after T; dropped if that bar starts more than
                    5 minutes after T.
  ATR               mean true range of the last `atr_n` complete hourly mid bars (UTC hour grid, a bar counts only if
                    it ended at or before T) -- the MT5 iATR(H1, atr_n) definition.
  stop              stop_atr x ATR from the fill (fixed, no trailing, no target).
  time exit         market, at the open of the first M1 bar at/after the exit time (gl.exit_index: if the exit time
                    falls in a closure, the last bar before it).

Families
  family="fix"     London 16:00 fix reversal.  On the last `monthend_n` London weekdays of the calendar month (pure
                   calendar; monthend_n=0 = every weekday): run = mid at `dec` minus mid `look_min` minutes earlier;
                   trade AGAINST the run (short if the price rose into the fix, long if it fell), at market at `dec`,
                   exit at `exit`.  No trade when run == 0.
  family="tod"     time-of-day drift: at `start` take side `dir` and exit at `end`.  dir="usd_long": buy USD against the
                   other currency (short EURUSD/GBPUSD/AUDUSD/NZDUSD, long USDJPY/USDCAD/USDCHF); for a cross
                   (EURJPY) sell the base currency.  Needs `pair` (the symbol), passed identically to every pair by
                   the basket runner -- it only sets the sign of the USD leg.
  family="ldnbrk"  London-open break of the Asian range: range = mid high / low of the M1 bars in [range_start,
                   range_end) London (at least `min_bars` bars).  From range_end to entry_end, the FIRST minute whose
                   ask high reaches the range high (buy) or bid low reaches the range low (sell) gives a stop order at
                   that level on that minute; if both are touched in the same minute, the buy is emitted and its stop
                   (the range low) is inside the fill bar, so the engine books the adverse outcome.  Stop = the opposite
                   side of the range; exit at `exit` London the same day.
"""
import os
import sys

import numpy as np
import pandas as pd

_LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if _LAB not in sys.path:
    sys.path.insert(0, _LAB)
import goldlab as gl  # noqa: E402

LDN = "Europe/London"
M = np.timedelta64(1, "m")

DEFAULTS = dict(
    family="fix",
    # fix
    dec="16:00", look_min=60, exit="16:30", monthend_n=1,
    # tod
    start="07:00", end="12:00", dir="usd_long", pair=None,
    # ldnbrk
    range_start="00:00", range_end="07:00", entry_end="10:00", min_bars=300,
    # common
    stop_atr=1.5, atr_n=24, max_delay_min=5, sides="both",
)


def _p(params):
    unknown = set(params) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown params {unknown}")
    p = dict(DEFAULTS)
    p.update(params)
    return p


def _idx(m1):
    return m1.index.tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]")


def _days(m1):
    d = m1.index.tz_convert(LDN).tz_localize(None).normalize().unique()
    return d[d.dayofweek < 5]


def _at(days, hhmm):
    h, mm = (int(x) for x in hhmm.split(":"))
    loc = days + pd.Timedelta(hours=h, minutes=mm)
    return loc.tz_localize(LDN, nonexistent="shift_forward", ambiguous=False).tz_convert("UTC").tz_localize(None) \
        .values.astype("datetime64[ns]")


def _price_at(idx, mc, tv, max_age=5):
    k = np.searchsorted(idx, tv, side="left") - 1
    kc = np.clip(k, 0, len(idx) - 1)
    ok = (k >= 0) & ((tv - idx[kc]) <= max_age * M)
    return np.where(ok, mc[kc], np.nan)


def _atr_at(m1, idx, tv, n):
    """Mean true range of the last n complete H1 mid bars ending at or before each time."""
    mh = ((m1.bh + m1.ah) / 2).to_numpy()
    ml = ((m1.bl + m1.al) / 2).to_numpy()
    mc = ((m1.bc + m1.ac) / 2).to_numpy()
    hs = idx.astype("datetime64[h]")
    first = np.r_[0, np.flatnonzero(hs[1:] != hs[:-1]) + 1]
    last = np.r_[first[1:] - 1, len(idx) - 1]
    H = np.maximum.reduceat(mh, first)
    L = np.minimum.reduceat(ml, first)
    Cc = mc[last]
    pc = np.r_[np.nan, Cc[:-1]]
    tr = np.nanmax(np.vstack([H - L, np.abs(H - pc), np.abs(L - pc)]), axis=0)
    atr = pd.Series(tr).rolling(int(n)).mean().to_numpy()
    end = hs[first].astype("datetime64[ns]") + np.timedelta64(1, "h")
    # the last hour of the frame counts only if the frame reaches its end
    if len(end) and end[-1] > idx[-1] + M:
        end, atr = end[:-1], atr[:-1]
    k = np.searchsorted(end, tv, side="right") - 1
    return np.where(k >= 0, atr[np.clip(k, 0, max(len(atr) - 1, 0))], np.nan)


def _usd_side(pair):
    if pair is None:
        raise ValueError("family 'tod' needs pair=")
    base, quote = pair[:3].lower(), pair[3:6].lower()
    if quote == "usd":
        return -1
    if base == "usd":
        return 1
    return -1  # cross: sell the base currency


def _market(m1, p, idx, tdec, texit, side, atr, extra=None):
    ei = np.searchsorted(idx, tdec, side="left").astype(np.int64)
    eic = np.clip(ei, 0, len(idx) - 1)
    ok = (ei < len(idx)) & ((idx[eic] - tdec) <= int(p["max_delay_min"]) * M)
    xi = gl.exit_index(m1, pd.DatetimeIndex(texit).tz_localize("UTC"))
    ok &= np.isfinite(atr) & (atr > 0) & (xi > ei) & (side != 0)
    if p["sides"] == "long":
        ok &= side > 0
    elif p["sides"] == "short":
        ok &= side < 0
    o = pd.DataFrame({"entry_i": ei, "side": side.astype(np.int64), "etype": 0, "level": np.nan, "expiry_i": -1,
                      "stop": np.nan, "stop_dist": atr * float(p["stop_atr"]), "target": np.nan, "target_dist": np.nan,
                      "exit_i": xi, "trail": np.nan, "be": np.nan,
                      "dec_time": pd.DatetimeIndex(tdec).tz_localize("UTC"),
                      "sched_exit": pd.DatetimeIndex(texit).tz_localize("UTC")})
    if extra:
        for k, v in extra.items():
            o[k] = np.asarray(v)
    return o[ok].sort_values("entry_i", kind="stable").reset_index(drop=True)


def _monthend_mask(days, n):
    if n <= 0:
        return np.ones(len(days), bool)
    # pure calendar: the last n weekdays (Mon-Fri) of each calendar month, whatever the data contains
    out = np.zeros(len(days), bool)
    for k, d in enumerate(days):
        me = (d + pd.offsets.MonthEnd(0)).normalize()
        wd = pd.bdate_range(d, me)  # weekdays from d to the month's last day, inclusive
        out[k] = len(wd) <= n
    return out


def _fix(m1, p):
    idx = _idx(m1)
    mc = ((m1.bc + m1.ac) / 2).to_numpy()
    days = _days(m1)
    days = days[_monthend_mask(days, int(p["monthend_n"]))]
    tdec = _at(days, p["dec"])
    texit = _at(days, p["exit"])
    p1 = _price_at(idx, mc, tdec)
    p0 = _price_at(idx, mc, tdec - int(p["look_min"]) * M)
    run = p1 - p0
    side = np.where(np.isfinite(run), -np.sign(run), 0).astype(np.int64)
    atr = _atr_at(m1, idx, tdec, p["atr_n"])
    return _market(m1, p, idx, tdec, texit, side, atr, extra={"run_bp": run / p0 * 1e4})


def _tod(m1, p):
    idx = _idx(m1)
    days = _days(m1)
    tdec, texit = _at(days, p["start"]), _at(days, p["end"])
    if p["dir"] != "usd_long":
        raise ValueError(p["dir"])
    side = np.full(len(days), _usd_side(p["pair"]), np.int64)
    atr = _atr_at(m1, idx, tdec, p["atr_n"])
    return _market(m1, p, idx, tdec, texit, side, atr)


def _ldnbrk(m1, p):
    idx = _idx(m1)
    ah, bl = m1.ah.to_numpy(), m1.bl.to_numpy()
    mh = ((m1.bh + m1.ah) / 2).to_numpy()
    ml = ((m1.bl + m1.al) / 2).to_numpy()
    days = _days(m1)
    t0, t1, t2, tx = (_at(days, p[k]) for k in ("range_start", "range_end", "entry_end", "exit"))
    i0, i1, i2 = (np.searchsorted(idx, t) for t in (t0, t1, t2))
    xi = gl.exit_index(m1, pd.DatetimeIndex(tx).tz_localize("UTC"))
    rows = []
    for k in range(len(days)):
        if i1[k] - i0[k] < int(p["min_bars"]) or i2[k] <= i1[k]:
            continue
        # range complete only when the frame has reached range_end
        if i1[k] >= len(idx):
            continue
        hi, lo = mh[i0[k]:i1[k]].max(), ml[i0[k]:i1[k]].min()
        if not hi > lo:
            continue
        up = np.flatnonzero(ah[i1[k]:i2[k]] >= hi)
        dn = np.flatnonzero(bl[i1[k]:i2[k]] <= lo)
        fu = up[0] if len(up) else 1 << 40
        fd = dn[0] if len(dn) else 1 << 40
        if fu == fd == 1 << 40:
            continue
        if fu <= fd:
            side, lvl, st, j = 1, hi, lo, i1[k] + fu
        else:
            side, lvl, st, j = -1, lo, hi, i1[k] + fd
        if p["sides"] == "long" and side < 0 or p["sides"] == "short" and side > 0:
            continue
        if xi[k] <= j:
            continue
        rows.append((j, side, 1, lvl, j, st, np.nan, np.nan, np.nan, xi[k], np.nan, np.nan,
                     pd.Timestamp(tx[k]).tz_localize("UTC"), (hi - lo) / lvl * 1e4))
    cols = ["entry_i", "side", "etype", "level", "expiry_i", "stop", "stop_dist", "target", "target_dist", "exit_i",
            "trail", "be", "sched_exit", "width_bp"]
    o = pd.DataFrame(rows, columns=cols)
    if len(o):
        o[["entry_i", "side", "etype", "expiry_i", "exit_i"]] = o[["entry_i", "side", "etype", "expiry_i", "exit_i"]].astype(np.int64)
    return o


def make_orders(m1, **params):
    p = _p(params)
    f = p["family"]
    if f == "fix":
        return _fix(m1, p)
    if f == "tod":
        return _tod(m1, p)
    if f == "ldnbrk":
        return _ldnbrk(m1, p)
    raise ValueError(f)


FINALISTS = {}
