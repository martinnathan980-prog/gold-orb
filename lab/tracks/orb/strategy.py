"""Opening-range breakout (ORB) on XAUUSD M1 bid/ask -- track `orb`.

make_orders(m1, **params) -> orders DataFrame for goldlab.simulate (one order per session/day).

Mechanics (all causal, implementable in an MT5 EA):
  * Range = M1 bars whose START lies in [range_start, range_end) local time (London or New York
    wall clock, DST handled per calendar date).  Range high = max ASK high, range low = min BID low
    (an EA tracks max Ask / min Bid on ticks).  The range is known when its last minute closes,
    i.e. at range_end; pending orders are active from the first M1 bar starting >= range_end.
  * entry="stop": OCO stop orders  buy-stop at high+buf (triggers on Ask), sell-stop at low-buf
    (triggers on Bid), active until entry_end.  The first level touched wins, the other is
    cancelled (one trade per session).  If both are touched inside the same M1 bar, the level
    closer to that bar's open is taken; the simulator then also checks the stop inside that bar
    (pessimistic).
  * entry="first_bar": direction of the opening range itself (close vs open, mid prices); market
    order at the open of the first bar after the range (Zarattini & Aziz style).
  * stop: "opp" opposite side of the range (+buf), "mid" range midpoint, "atr" k x daily ATR(14).
  * target: target_R x initial risk (None = no target); optional break-even at be_R x risk.
  * forced exit at exit_time (exit_tz wall clock) on the same date (+ hold_days business days).
  * filters: range width / daily ATR(14) of the last COMPLETED trading day (17:00 NY boundary),
    sides, weekdays.

Every row has a stop and an exit_i; the max hold is bounded by hold_days <= 4 (5 trading days).
"""
import os
import sys

import numba as nb
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import goldlab as gl  # noqa: E402

TZ = {"LDN": gl.LDN, "NY": gl.NY}

DEFAULTS = dict(
    tz="NY", range_start="08:20", range_end="08:35", entry_end="12:00",
    exit_time="16:00", exit_tz="NY", hold_days=0,
    entry="stop", buf_frac=0.0, buf_abs=0.0,
    stop_mode="opp", stop_atr=0.5, target_R=None, be_R=None,
    min_width_atr=None, max_width_atr=None, sides="both", skip_dow=(),
    min_bars_frac=0.5, atr_n=14,
)


def _hm(s):
    h, m = s.split(":")
    return pd.Timedelta(hours=int(h), minutes=int(m))


def _local_times(dates, hm, tz):
    """UTC timestamps of wall-clock `hm` in `tz` on each (naive) calendar date."""
    loc = (pd.DatetimeIndex(dates) + _hm(hm)).tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward")
    return loc.tz_convert("UTC")


@nb.njit(cache=True)
def _range_stats(ah, bl, i0, i1):
    n = len(i0)
    hi = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    for k in range(n):
        if i1[k] > i0[k]:
            h = -1e300
            l = 1e300
            for i in range(i0[k], i1[k]):
                if ah[i] > h:
                    h = ah[i]
                if bl[i] < l:
                    l = bl[i]
            hi[k] = h
            lo[k] = l
    return hi, lo


@nb.njit(cache=True)
def _first_touch(ah, bl, ao, bo, i_start, i_end, buy_lv, sell_lv, allow_long, allow_short):
    """Index and side of the first M1 bar in [i_start, i_end) touching either pending level."""
    n = len(i_start)
    out_i = np.full(n, -1, np.int64)
    out_s = np.zeros(n, np.int64)
    for k in range(n):
        if np.isnan(buy_lv[k]) or np.isnan(sell_lv[k]):
            continue
        for i in range(i_start[k], i_end[k]):
            up = allow_long[k] and ah[i] >= buy_lv[k]
            dn = allow_short[k] and bl[i] <= sell_lv[k]
            if up and dn:
                mo = 0.5 * (ao[i] + bo[i])
                s = 1 if abs(buy_lv[k] - mo) <= abs(mo - sell_lv[k]) else -1
            elif up:
                s = 1
            elif dn:
                s = -1
            else:
                continue
            out_i[k] = i
            out_s[k] = s
            break
    return out_i, out_s


_daily_cache = {}


def daily_atr(m1, n=14):
    """Daily (17:00 NY trading day) mid-price ATR(n), indexed by the bar's t_close (UTC)."""
    key = (id(m1), len(m1), m1.index[0], m1.index[-1], n)
    if key not in _daily_cache:
        d = gl.bars(m1, "D")
        a = gl.atr(d, n)
        _daily_cache.clear()
        _daily_cache[key] = pd.DataFrame({"t_close": pd.DatetimeIndex(d.t_close).as_unit("ns"),
                                          "atr": a.to_numpy(), "close": d.c.to_numpy()}
                                         ).sort_values("t_close").reset_index(drop=True)
    return _daily_cache[key]


def sessions(m1, p):
    """One row per weekday calendar date (in p['tz']): range bounds, levels, windows (no orders)."""
    tz = TZ[p["tz"]]
    idx = m1.index
    loc = idx[[0, -1]].tz_convert(tz)
    dates = pd.date_range(loc[0].tz_localize(None).normalize(), loc[1].tz_localize(None).normalize(), freq="D")
    dates = dates[dates.dayofweek < 5]
    rs = _local_times(dates, p["range_start"], tz)
    re = _local_times(dates, p["range_end"], tz)
    ee = _local_times(dates, p["entry_end"], tz)
    xdates = dates + pd.offsets.BDay(int(p["hold_days"])) if p["hold_days"] else dates
    xt = _local_times(xdates, p["exit_time"], TZ[p["exit_tz"]])
    if p["tz"] != p["exit_tz"]:
        # same wall-clock date in the exit zone; London and NY dates coincide during the day
        pass
    ok = ~(rs.isna() | re.isna() | ee.isna() | xt.isna())
    dates, rs, re, ee, xt = dates[ok], rs[ok], re[ok], ee[ok], xt[ok]
    v = idx.values
    i0 = np.searchsorted(v, rs.values)
    i1 = np.searchsorted(v, re.values)
    ie = np.searchsorted(v, ee.values)
    ix = np.searchsorted(v, xt.values)
    ah = m1["ah"].to_numpy(np.float64)
    bl = m1["bl"].to_numpy(np.float64)
    hi, lo = _range_stats(ah, bl, i0, i1)
    s = pd.DataFrame({"date": dates, "t_rs": rs.as_unit("ns"), "t_re": re.as_unit("ns"), "t_ee": ee, "t_x": xt,
                      "i0": i0, "i1": i1, "ie": ie, "ix": ix, "hi": hi, "lo": lo})
    exp_min = (s.t_re - s.t_rs).dt.total_seconds() / 60
    s["nbars"] = s.i1 - s.i0
    s = s[(s.nbars >= p["min_bars_frac"] * exp_min) & (s.i1 < len(m1)) & (s.ie > s.i1)].copy()
    s["width"] = s.hi - s.lo
    # daily ATR of the last trading day completed before the range end
    da = daily_atr(m1, p["atr_n"])
    s = pd.merge_asof(s.sort_values("t_re"), da.rename(columns={"t_close": "t_re"})[["t_re", "atr"]],
                      on="t_re", direction="backward", allow_exact_matches=True)
    s["w_atr"] = s.width / s.atr
    s["dow"] = s.date.dt.dayofweek
    return s.reset_index(drop=True)


def make_orders(m1, **params):
    p = dict(DEFAULTS)
    unknown = set(params) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown params {unknown}")
    p.update(params)
    s = sessions(m1, p)
    keep = np.ones(len(s), bool)
    if p["min_width_atr"] is not None:
        keep &= s.w_atr >= p["min_width_atr"]
    if p["max_width_atr"] is not None:
        keep &= s.w_atr <= p["max_width_atr"]
    if p["skip_dow"]:
        keep &= ~s.dow.isin(list(p["skip_dow"]))
    keep &= s.width > 0
    s = s[keep].reset_index(drop=True)
    buf = p["buf_frac"] * s.width.to_numpy() + p["buf_abs"]
    buy_lv = s.hi.to_numpy() + buf
    sell_lv = s.lo.to_numpy() - buf
    allow_l = np.full(len(s), p["sides"] in ("both", "long"))
    allow_s = np.full(len(s), p["sides"] in ("both", "short"))
    ah, bl, ao, bo = (m1[k].to_numpy(np.float64) for k in ("ah", "bl", "ao", "bo"))
    if p["entry"] == "stop":
        fi, side = _first_touch(ah, bl, ao, bo, s.i1.to_numpy(np.int64), s.ie.to_numpy(np.int64),
                                buy_lv, sell_lv, allow_l, allow_s)
        ok = fi >= 0
        level = np.where(side > 0, buy_lv, sell_lv)
        etype = 1
    elif p["entry"] == "first_bar":
        # direction of the opening range (mid close of last range bar vs mid open of first)
        mo = 0.5 * (m1["ao"].to_numpy() + m1["bo"].to_numpy())
        mc = 0.5 * (m1["ac"].to_numpy() + m1["bc"].to_numpy())
        i0, i1 = s.i0.to_numpy(), s.i1.to_numpy()
        d = mc[i1 - 1] - mo[i0]
        side = np.sign(d).astype(np.int64)
        side[(side > 0) & ~allow_l] = 0
        side[(side < 0) & ~allow_s] = 0
        ok = side != 0
        fi = i1.astype(np.int64)
        level = np.where(side > 0, buy_lv, sell_lv)  # reference entry level (for target calc only)
        level = np.where(side > 0, ao[np.minimum(fi, len(m1) - 1)], bo[np.minimum(fi, len(m1) - 1)])
        etype = 0
    else:
        raise ValueError(p["entry"])
    s = s[ok].reset_index(drop=True)
    fi, side, level = fi[ok], side[ok], level[ok]
    buy_lv, sell_lv = buy_lv[ok], sell_lv[ok]
    if p["stop_mode"] == "opp":
        stop = np.where(side > 0, sell_lv, buy_lv)
    elif p["stop_mode"] == "mid":
        stop = 0.5 * (s.hi.to_numpy() + s.lo.to_numpy())
    elif p["stop_mode"] == "atr":
        stop = level - side * p["stop_atr"] * s.atr.to_numpy()
    else:
        raise ValueError(p["stop_mode"])
    risk = np.abs(level - stop)
    tgt = level + side * p["target_R"] * risk if p["target_R"] else np.full(len(s), np.nan)
    be = p["be_R"] * risk if p["be_R"] else np.full(len(s), np.nan)
    o = pd.DataFrame({
        "entry_i": fi, "side": side, "etype": etype,
        "level": level if etype == 1 else np.nan,
        "expiry_i": fi if etype == 1 else -1,
        "stop": stop, "target": tgt, "exit_i": s.ix.to_numpy(np.int64), "be": be,
        "date": s.date.values, "w_atr": s.w_atr.values, "width": s.width.values,
    })
    # forced exit must come after the entry bar; drop sessions whose exit time precedes entry
    o = o[(o.exit_i > o.entry_i) & np.isfinite(o.stop) & (risk > 0)]
    return o.reset_index(drop=True)


FINALISTS = {}
