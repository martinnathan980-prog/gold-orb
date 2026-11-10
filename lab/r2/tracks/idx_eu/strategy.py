"""Track idx_eu (round 2): DAX CFD (ger40) intraday rules on Europe/Berlin wall-clock time.

`make_orders(m1, **params)` builds a causal orders frame for goldlab.simulate from ANY M1 bid/ask
frame of the market (columns bo bh bl bc ao ah al ac, UTC index).  Two families:

  family="mom"   Close-anchored intraday momentum.  At each decision time T of `times` (Berlin clock)
                 x_T = last M1 mid close before T / previous day's cash-close price (last M1 mid close
                 before `anchor`, default 17:30 Berlin) - 1.
                 vol_T = standard deviation of x_T over the previous `lb` trading days (today excluded).
                 Signal at the FIRST T of the day with |x_T| >= k * vol_T: market order at T in the
                 direction of x_T (direction=+1) or against it (direction=-1), stop at stop_k * vol_T
                 (as a fraction of price) from the fill, time exit at `exit` (Berlin clock, same day).
                 At most one trade per day.
  family="orb"   Opening-range breakout.  Range = M1 bars starting in [rs, re): H = max Ask high,
                 L = min Bid low, W = H - L.  Buy stop at H + buf*W / sell stop at L - buf*W, valid from
                 `re` until `entry_end`; only the level touched FIRST is traded (OCO resolved here on
                 M1; both touched in the same minute -> the adverse side).  Stop at `stop_frac` * W(+buffers)
                 from the entry level (1.0 = the opposite level), optional target (R multiple) and trailing
                 stop, time exit at `exit`.  One trade per day.

Clock strings are "HH:MM" in Europe/Berlin, or "HH:MM@NY" for New York wall clock (US cash open).
Causality: every quantity used at a decision time comes from M1 bars that are closed at that time; the
volatility scale uses previous days only.  Tested by truncation (see research files).

Warm-up: family "mom" needs `lb` + 1 trading days of history before its first signal.
"""
import numba as nb
import numpy as np
import pandas as pd

import goldlab as gl

BER = "Europe/Berlin"
_TZ = {"BER": BER, "NY": "America/New_York", "LDN": "Europe/London"}

DEFAULTS = {
    "family": "mom",
    # mom
    "times": ("16:00",), "anchor": "17:30", "lb": 20, "k": 1.5, "direction": 1, "stop_k": 0.5,
    # orb
    "rs": "09:00", "re": "09:30", "entry_end": "17:00", "buf": 0.0, "stop_frac": 1.0,
    "target_r": float("nan"), "trail_frac": float("nan"),
    # common
    "exit": "17:30", "sides": "both", "tol_min": 5,
}


def _p(params):
    unknown = set(params) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown parameters: {sorted(unknown)}")
    p = dict(DEFAULTS)
    p.update(params)
    if isinstance(p["times"], str):
        p["times"] = (p["times"],)
    return p


def _days(m1):
    """Calendar weekdays (naive dates, Berlin) spanned by the frame."""
    ber = m1.index[[0, -1]].tz_convert(BER).tz_localize(None).normalize()
    return pd.bdate_range(ber[0], ber[1])


def _clock(days, hhmm):
    """UTC timestamps (tz-aware DatetimeIndex) of a wall-clock time on each day."""
    tz = BER
    if "@" in hhmm:
        hhmm, z = hhmm.split("@")
        tz = _TZ[z]
    h, m = (int(x) for x in hhmm.split(":"))
    loc = (days + pd.Timedelta(hours=h, minutes=m)).tz_localize(tz, ambiguous="NaT", nonexistent="NaT")
    return loc.tz_convert("UTC")


def _ix(iv, t):
    """Index of the first M1 bar starting at/after each time (len(iv) = none)."""
    tv = t.tz_localize(None).values.astype(iv.dtype)
    i = np.searchsorted(iv, tv, side="left").astype(np.int64)
    i[np.isnat(tv)] = len(iv)
    return i, tv


def _decision(iv, mid_c, t, tol):
    """For decision times `t`: (entry bar index, ok flag, last mid close known at t).
    ok = a bar starts within `tol` minutes after t AND the previous bar started within `tol` minutes
    before t (so the 'last close' is fresh)."""
    n = len(iv)
    i, tv = _ix(iv, t)
    ic = np.clip(i, 1, n - 1)
    tolv = np.timedelta64(int(tol), "m")
    ok = (i >= 1) & (i < n) & ~np.isnat(tv)
    ok &= (iv[ic] - tv) <= tolv
    ok &= (tv - iv[ic - 1]) <= tolv
    px = np.where(ok, mid_c[ic - 1], np.nan)
    return i, ok, px


def _sides(side, sides):
    if sides == "long":
        return side > 0
    if sides == "short":
        return side < 0
    return np.ones(len(side), bool)


# ------------------------------------------------------------------------------------------ mom
def _mom(m1, p):
    iv = m1.index.values
    mid_c = ((m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2.0)
    days = _days(m1)
    tol = p["tol_min"]
    # previous cash close: last mid close before `anchor` on the latest earlier day that has one
    _, a_ok, a_px = _decision(iv, mid_c, _clock(days, p["anchor"]), tol)
    anchor = pd.Series(np.where(a_ok, a_px, np.nan), index=days).ffill().shift(1).to_numpy()
    lb = int(p["lb"])
    n = len(days)
    ent_i = np.full(n, -1, np.int64)
    side = np.zeros(n, np.int64)
    sdist = np.full(n, np.nan)
    zval = np.full(n, np.nan)
    tsel = np.full(n, -1, np.int64)
    for j, T in enumerate(p["times"]):
        i, ok, px = _decision(iv, mid_c, _clock(days, T), tol)
        x = pd.Series(np.where(ok, px / anchor - 1.0, np.nan), index=days)
        xv = x.dropna()
        vol = xv.rolling(lb, min_periods=lb).std().shift(1).reindex(days).to_numpy()
        xa = x.to_numpy()
        z = xa / vol
        sig = np.isfinite(z) & (np.abs(z) >= float(p["k"])) & (xa != 0) & (ent_i < 0)
        ent_i[sig] = i[sig]
        side[sig] = (np.sign(xa[sig]) * int(p["direction"])).astype(np.int64)
        sdist[sig] = float(p["stop_k"]) * vol[sig] * px[sig]
        zval[sig] = z[sig]
        tsel[sig] = j
    xi = gl.exit_index(m1, _clock(days, p["exit"]))
    keep = (ent_i >= 0) & (xi > ent_i) & np.isfinite(sdist) & (sdist > 0) & _sides(side, p["sides"])
    o = pd.DataFrame({"entry_i": ent_i[keep], "side": side[keep], "etype": 0, "stop_dist": sdist[keep],
                      "exit_i": xi[keep], "z": zval[keep], "t_idx": tsel[keep]})
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------------------------------ orb
@nb.njit(cache=True)
def _range_touch(ah, bl, bo, bc, i_rs, i_re, i_end, min_bars, buf):
    """Per day: range levels on bars [i_rs, i_re) and the first bar in [i_re, i_end] touching one of
    them.  Both touched in the same bar -> the side AGAINST the bar's net move (adverse assumption)."""
    n = len(i_rs)
    up = np.full(n, np.nan)
    dn = np.full(n, np.nan)
    hit_i = np.full(n, -1, np.int64)
    hit_s = np.zeros(n, np.int64)
    N = len(ah)
    for k in range(n):
        a, b, e = i_rs[k], i_re[k], i_end[k]
        if a < 0 or b > N or b - a < min_bars[k] or e < b:
            continue
        h = -np.inf
        l = np.inf
        for i in range(a, b):
            if ah[i] > h:
                h = ah[i]
            if bl[i] < l:
                l = bl[i]
        w = h - l
        if not (w > 0):
            continue
        u = h + buf * w
        d = l - buf * w
        up[k] = u
        dn[k] = d
        for i in range(b, min(e, N - 1) + 1):
            hu = ah[i] >= u
            hd = bl[i] <= d
            if hu and hd:
                hit_i[k] = i
                hit_s[k] = -1 if bc[i] >= bo[i] else 1
                break
            if hu:
                hit_i[k] = i
                hit_s[k] = 1
                break
            if hd:
                hit_i[k] = i
                hit_s[k] = -1
                break
    return up, dn, hit_i, hit_s


def _orb(m1, p):
    iv = m1.index.values
    days = _days(m1)
    n = len(iv)
    t_rs, t_re, t_end = _clock(days, p["rs"]), _clock(days, p["re"]), _clock(days, p["entry_end"])
    i_rs, v_rs = _ix(iv, t_rs)
    i_re, v_re = _ix(iv, t_re)
    i_end, v_end = _ix(iv, t_end)
    i_end = i_end - 1                                    # last bar starting before entry_end
    rng_min = ((v_re - v_rs) / np.timedelta64(1, "m")).astype(float)
    ok = ~(np.isnat(v_rs) | np.isnat(v_re) | np.isnat(v_end)) & (i_re < n)
    tolv = np.timedelta64(int(p["tol_min"]), "m")
    ok &= (iv[np.clip(i_re, 0, n - 1)] - v_re) <= tolv   # market open right after the range
    min_bars = np.where(ok, np.ceil(0.5 * np.nan_to_num(rng_min, nan=1e9)), 10 ** 9).astype(np.int64)
    up, dn, hit_i, hit_s = _range_touch(m1["ah"].to_numpy(), m1["bl"].to_numpy(), m1["bo"].to_numpy(),
                                        m1["bc"].to_numpy(), i_rs, i_re, i_end, min_bars, float(p["buf"]))
    xi = gl.exit_index(m1, _clock(days, p["exit"]))
    keep = (hit_i >= 0) & (xi > hit_i) & _sides(hit_s, p["sides"])
    side = hit_s[keep]
    level = np.where(side > 0, up[keep], dn[keep])
    width = (up - dn)[keep]
    sd = float(p["stop_frac"]) * width
    o = pd.DataFrame({"entry_i": hit_i[keep], "side": side, "etype": 1, "level": level,
                      "expiry_i": hit_i[keep], "stop": level - side * sd, "exit_i": xi[keep], "width": width})
    if not np.isnan(p["target_r"]):
        o["target"] = level + side * sd * float(p["target_r"])
    if not np.isnan(p["trail_frac"]):
        o["trail"] = float(p["trail_frac"]) * width
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


def make_orders(m1, **params):
    p = _p(params)
    if p["family"] == "mom":
        return _mom(m1, p)
    if p["family"] == "orb":
        return _orb(m1, p)
    raise ValueError(p["family"])


# Finalists chosen on the in-sample period only (results/r2/idx_eu/finalists_preval.json), one fixed
# parameter set each, instrument ger40.  Both are family "mom" (momentum into the Xetra cash close):
#   late_mom_1600   at 16:00 Berlin, if the move since yesterday's 17:30 close is >= 1.5 x its 20-day
#                   standard deviation, trade in its direction; stop 0.5 x that deviation; exit 17:30.
#   close_run_1725  at 17:25 Berlin, same test with threshold 0.5; stop 0.25 x deviation; exit 17:30.
#
# EA port (both): all clock times are Europe/Berlin wall clock (convert from the MT5 server clock, DST
# included).  P(t) = mid (bid+ask)/2 at the close of the last M1 bar started before t (no bar within
# `tol_min` minutes -> no trade).  A = P(17:30) of the latest earlier day quoted at 17:30.
# x = P(T)/A - 1;  vol = sample standard deviation (n-1) of x over the 20 latest earlier days;
# if |x| >= k*vol: market order at T in the direction of x, stop-loss at stop_k*vol*P(T) from the fill,
# market exit at 17:30:00 (not later: one minute late costs about half the close_run edge), one trade a day.
#
# Single-shot validation 2022-2025 (results/r2/idx_eu/val_results.json), no re-tuning afterwards:
VAL_STATUS = {
    "late_mom_1600": "FAILED (PF 0.977, -0.008 R/trade, t -0.12, n 151)",
    "close_run_1725": "passes the letter (PF 1.105, +0.0105 R/trade, t 0.93, n 618) but negative with costs x1.5 "
                      "(PF 0.894) and in 2 of 4 years: not confirmed",
}
FINALISTS = {
    "late_mom_1600": {
        "syms": ["ger40"],
        "params": {"family": "mom", "times": ["16:00"], "anchor": "17:30", "lb": 20, "k": 1.5, "direction": 1,
                   "stop_k": 0.5, "exit": "17:30", "sides": "both", "tol_min": 5},
    },
    "close_run_1725": {
        "syms": ["ger40"],
        "params": {"family": "mom", "times": ["17:25"], "anchor": "17:30", "lb": 20, "k": 0.5, "direction": 1,
                   "stop_k": 0.25, "exit": "17:30", "sides": "both", "tol_min": 5},
    },
}
