"""Track idx_us (round 2): intraday momentum rules on US index CFDs (us100, us500, us30).

    make_orders(m1, rule=..., **params) -> orders DataFrame for goldlab.simulate
    FINALISTS = {name: {"syms": [...], "params": {...}}}        (bottom of this file)

Works on ANY M1 bid/ask frame of the market (UTC index, columns bo bh bl bc ao ah al ac).  All session times
are New York wall-clock times (DST handled by the tz database).  Only regular US cash sessions are traded
(weekdays, NYSE full holidays skipped, 13:00 early closes skipped: rule-based calendar in idxus_lib.py), from
2014-01-01 on (older index data is incomplete).  Every rule is flat before the cash close and holds at most one
position.

WARM-UP: give make_orders a frame that starts at least 2 months before the first trade you count (daily ATR(14),
20-session medians, 14-session noise bands).  Checked: orders built on a frame starting 2021-09-01 are identical
to the full-history orders from 2021-11-01 on (results/r2/idx_us/account_feasibility.json).  For the 2026 holdout:
load from 2025-10-01 and keep trades with entry >= 2026-01-01.

Rules (`rule=`):
  "ocm"    Opening-candle momentum (after Zarattini & Aziz 2023, "5-minute ORB"): at 09:30+n the direction of the
           first n-minute candle (close vs open) is traded at market; stop behind the candle (or k x ATR);
           optional size filter (|candle move| >= size_min x median of the previous size_win sessions); flat at
           `exit_min`.                                                        -> finalist "ocm4"
  "orb"    Classical opening-range breakout: OCO stop entries at the high / low of the first n minutes,
           first touch resolved on M1, stop on the other side of the range, flat at `exit_min`.   (rejected)
  "noise"  Noise-area intraday momentum (Zarattini, Aziz, Barbon 2024): at fixed clock times, enter when the
           price is outside a band around the open whose half-width is the average absolute move from the
           open to that time of day over the last `lookback` sessions; exit when back inside the band at a
           check, or at `exit_min`.                                           -> finalist "noise30"
  "last"   End-of-day momentum (Gao et al. 2018, Baltussen et al. 2021): at 15:30 trade the sign of the
           return since the previous cash close; flat at 15:59.               (rejected)

Causality: decisions at time T only use bars that STARTED before T (hence closed at or before T), daily ATR
of trading days that ended (17:00 New York) before T, and statistics of PREVIOUS sessions.  The truncation
tests (causality_test.py, causality_finalists.py) rebuild the orders on frames cut at random minutes and compare.

Notes for the MT5 port (both finalists use MID prices = (bid+ask)/2 for signals; "price at T" is the close of the
M1 bar that starts at T-1min; orders are sent on the first tick at/after T):
  noise30  O = open of the 09:30 M1 bar; PC = close of the previous regular session's 15:59 bar (ignored after an
           early close).  For T in 10:00, 10:30, ..., 15:30:  sigma(T) = mean over the previous 14 sessions (at
           least 9 with data) of |price_d(T) / O_d - 1|;  UB = max(O, PC) * (1 + sigma),  LB = min(O, PC) * (1 - sigma).
           State machine: (a) if the sleeve is long and price(T) < UB, or short and price(T) > LB: close, state flat;
           (b) if flat and price(T) > UB: buy, stop-loss at max(O, PC); if flat and price(T) < LB: sell, stop-loss at
           min(O, PC).  After a stop-loss the state stays "long"/"short" (no new entry) until a check passes test
           (a).  Everything closed at 15:55.  A check is skipped when the last quote is older than 10 minutes.
  ocm4     At 09:34: move = close of the 09:33 bar / open of the 09:30 bar - 1 (at least 3 of the 4 bars present).
           med = median of |move| over the previous 20 sessions (at least 10).  If |move| >= med: buy if move > 0,
           sell if move < 0, at market; stop-loss 0.3 x ATR14 from the fill (ATR14 = simple mean of the true range
           of the last 14 COMPLETED daily bars, days ending 17:00 New York, i.e. iATR(D1, 14) at shift 1 on an
           FP Markets server); close at 15:55.  One trade a day at most.
"""
import datetime as dt
import math
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
_LAB = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
if _LAB not in sys.path:
    sys.path.append(_LAB)        # goldlab lives in lab/
import goldlab as gl          # noqa: E402
import idxus_lib as cm        # noqa: E402

MIN_DATE = dt.date(2014, 1, 1)
NAN = float("nan")
_MIN = np.timedelta64(60, "s").astype("timedelta64[ns]")

DEFAULTS = {
    "ocm": {"n": 5, "stop": "candle", "k": 0.05, "exit_min": 955, "size_min": 0.0, "size_win": 20,
            "target_r": None, "atr_n": 14, "sides": "both"},
    "orb": {"n": 15, "win_end_min": 720, "exit_min": 955, "kmin": 0.05, "atr_n": 14},
    "noise": {"lookback": 14, "first_min": 600, "step": 30, "last_min": 930, "exit_min": 955, "vm": 1.0},
    "last": {"entry_min": 930, "exit_min": 959, "k": 3.0, "vol_win": 20, "sig": "rod"},
}


OPTIONAL = {"noise": {"hs_atr": None}, "ocm": {"delay": 0}}      # optional keys, listed in the resolved set only when used


def resolve(params):
    """Full parameter set (rule + defaults + overrides): what is logged and stored for finalists."""
    p = dict(params)
    rule = p.pop("rule", "ocm")
    full = dict(DEFAULTS[rule])
    opt = OPTIONAL.get(rule, {})
    unknown = set(p) - set(full) - set(opt)
    if unknown:
        raise ValueError(f"unknown parameters for rule {rule}: {sorted(unknown)}")
    full.update({k: v for k, v in p.items() if not (k in opt and v == opt[k])})
    return {"rule": rule, **full}


def _frame(rows):
    cols = ["entry_i", "side", "etype", "level", "expiry_i", "stop", "stop_dist", "target", "target_dist",
            "exit_i", "trail", "be"]
    if not len(rows.get("entry_i", [])):
        return pd.DataFrame({c: pd.Series(dtype="float64") for c in cols}).astype({"entry_i": "int64", "side": "int64",
                                                                                 "etype": "int64", "expiry_i": "int64", "exit_i": "int64"})
    n = len(rows["entry_i"])
    out = {}
    for c in cols:
        v = rows.get(c)
        if v is None:
            v = np.full(n, {"etype": 0, "expiry_i": -1, "exit_i": -1}.get(c, np.nan))
        out[c] = np.asarray(v)
    df = pd.DataFrame(out)
    for c in ("entry_i", "side", "etype", "expiry_i", "exit_i"):
        df[c] = df[c].astype("int64")
    return df.sort_values("entry_i", kind="stable").reset_index(drop=True)


def _session_ok(g):
    dates = g["dates"]
    return (~g["half"]) & np.array([d >= MIN_DATE for d in dates], bool)


def _exit_index(m1, g, exit_min):
    t = g["t0"] + (exit_min - 570) * _MIN
    return gl.exit_index(m1, pd.DatetimeIndex(t, tz="UTC"))


# ------------------------------------------------------------------------------------------------
# Opening-candle momentum
# ------------------------------------------------------------------------------------------------
def _ocm(m1, n, stop, k, exit_min, size_min, size_win, target_r, atr_n, sides, delay=0):
    g = cm.grid(m1)
    POS, EI, P, O = g["POS"], g["EI"], g["P"], g["O"]
    D = len(g["dates"])
    bl, ah = m1["bl"].to_numpy(), m1["ah"].to_numpy()
    C = P[:, n]                                   # mid known at 09:30+n = close of the candle
    a, b = POS[:, 0], POS[:, n]                   # the candle = bars that started in [09:30, 09:30+n)
    cnt = b - a
    lo, hi = np.full(D, np.nan), np.full(D, np.nan)
    for d in np.flatnonzero(cnt > 0):
        lo[d] = bl[a[d]:b[d]].min()               # candle low on the BID (a long's stop triggers on bid)
        hi[d] = ah[a[d]:b[d]].max()               # candle high on the ASK (a short's stop triggers on ask)
    move = C / O - 1
    side = np.sign(move)
    amove = np.abs(move)
    med = pd.Series(amove).rolling(size_win, min_periods=max(size_win // 2, 1)).median().shift(1).to_numpy()
    atr = cm.atr_at(m1, g["t0"] + n * _MIN, atr_n)
    ne = n + delay                                # entry minute (delay > 0 only for the latency robustness test)
    ok = _session_ok(g) & np.isfinite(O) & np.isfinite(C) & (cnt >= math.ceil(0.6 * n)) & (EI[:, ne] >= 0) \
        & (side != 0) & np.isfinite(atr)
    if size_min > 0:
        ok &= np.isfinite(med) & (amove >= size_min * med)
    if sides == "long":
        ok &= side > 0
    elif sides == "short":
        ok &= side < 0
    xi = _exit_index(m1, g, exit_min)
    ok &= xi > EI[:, ne]
    w = np.flatnonzero(ok)
    s = side[w].astype(np.int64)
    rows = {"entry_i": EI[w, ne], "side": s, "exit_i": xi[w]}
    if stop == "candle":                          # behind the candle, but never closer than k x ATR
        floor = k * atr[w]
        rows["stop"] = np.where(s > 0, np.minimum(lo[w], C[w] - floor), np.maximum(hi[w], C[w] + floor))
    elif stop == "atr":
        rows["stop_dist"] = k * atr[w]
    else:
        raise ValueError(stop)
    if target_r is not None:
        ref = np.abs(C[w] - rows["stop"]) if stop == "candle" else rows["stop_dist"]
        rows["target_dist"] = target_r * ref
    return _frame(rows)


# ------------------------------------------------------------------------------------------------
# Classical opening-range breakout (OCO stop entries, first touch resolved on M1)
# ------------------------------------------------------------------------------------------------
def _orb(m1, n, win_end_min, exit_min, kmin, atr_n):
    g = cm.grid(m1)
    POS, EI, P, O = g["POS"], g["EI"], g["P"], g["O"]
    D = len(g["dates"])
    bl, ah = m1["bl"].to_numpy(), m1["ah"].to_numpy()
    a, b = POS[:, 0], POS[:, n]
    cnt = b - a
    we = win_end_min - 570
    last = POS[:, we] - 1                          # last bar that starts before the end of the entry window
    atr = cm.atr_at(m1, g["t0"] + n * _MIN, atr_n)
    xi = _exit_index(m1, g, exit_min)
    ok = _session_ok(g) & np.isfinite(O) & (cnt >= math.ceil(0.6 * n)) & (EI[:, n] >= 0) & np.isfinite(atr)
    e_i, e_side, e_lvl, e_stop, e_x = [], [], [], [], []
    for d in np.flatnonzero(ok):
        H = ah[a[d]:b[d]].max()
        L = bl[a[d]:b[d]].min()
        if H - L < kmin * atr[d]:                  # degenerate range: skip
            continue
        i0, i1 = EI[d, n], min(last[d], xi[d] - 1)
        if i1 < i0:
            continue
        up = ah[i0:i1 + 1] >= H
        dn = bl[i0:i1 + 1] <= L
        hit = np.flatnonzero(up | dn)
        if not len(hit):
            continue
        j = hit[0]
        sd = 1 if up[j] else -1                    # both sides in the same minute: the long is filled and the engine
        e_i.append(i0 + j)                         # stops it out in the same bar (adverse assumption)
        e_side.append(sd)
        e_lvl.append(H if sd > 0 else L)
        e_stop.append(L if sd > 0 else H)
        e_x.append(xi[d])
    rows = {"entry_i": np.array(e_i, np.int64), "side": np.array(e_side, np.int64), "etype": np.ones(len(e_i), np.int64),
            "level": np.array(e_lvl), "expiry_i": np.array(e_i, np.int64), "stop": np.array(e_stop),
            "exit_i": np.array(e_x, np.int64)}
    return _frame(rows)


# ------------------------------------------------------------------------------------------------
# Noise-area intraday momentum
# ------------------------------------------------------------------------------------------------
def _noise(m1, lookback, first_min, step, last_min, exit_min, vm, hs_atr=None):
    g = cm.grid(m1)
    EI, P, O = g["EI"], g["P"], g["O"]
    D = len(g["dates"])
    checks = np.arange(first_min - 570, last_min - 570 + 1, step)
    absmove = np.abs(P[:, checks] / O[:, None] - 1)
    sig = pd.DataFrame(absmove).rolling(lookback, min_periods=max(int(0.7 * lookback), 1)).mean().shift(1).to_numpy()
    cl = P[:, 390]
    pc = np.r_[np.nan, cl[:-1]]                    # previous session's 16:00 price (NaN after an early close)
    hi_ref = np.where(np.isfinite(pc), np.fmax(O, pc), O)
    lo_ref = np.where(np.isfinite(pc), np.fmin(O, pc), O)
    xi = _exit_index(m1, g, exit_min)
    ok = _session_ok(g) & np.isfinite(O)
    atr = cm.atr_at(m1, g["t0"], 14) if hs_atr is not None else None
    if atr is not None:
        ok &= np.isfinite(atr)
    e_i, e_side, e_stop, e_x = [], [], [], []
    for d in np.flatnonzero(ok):
        pos, open_k = 0, -1
        for j, m in enumerate(checks):
            p, s, ei = P[d, m], sig[d, j], EI[d, m]
            if not (np.isfinite(p) and np.isfinite(s)) or ei < 0 or ei >= xi[d]:
                continue
            ub, lb = hi_ref[d] * (1 + vm * s), lo_ref[d] * (1 - vm * s)
            if pos != 0 and ((pos > 0 and p < ub) or (pos < 0 and p > lb)):
                e_x[open_k] = ei                   # back inside the band: close at this check
                pos = 0
                ei += 1                            # a reversal at the same check goes one bar later
            if pos == 0 and ei < xi[d]:
                if p > ub or p < lb:
                    pos = 1 if p > ub else -1
                    e_i.append(ei)
                    e_side.append(pos)
                    if atr is None:
                        e_stop.append(hi_ref[d] if pos > 0 else lo_ref[d])   # hard stop: the centre of the noise area
                    else:
                        e_stop.append(p - pos * hs_atr * atr[d])             # robustness variant: k x ATR from the signal price
                    e_x.append(xi[d])
                    open_k = len(e_i) - 1
    rows = {"entry_i": np.array(e_i, np.int64), "side": np.array(e_side, np.int64), "stop": np.array(e_stop),
            "exit_i": np.array(e_x, np.int64)}
    return _frame(rows)


# ------------------------------------------------------------------------------------------------
# End-of-day momentum
# ------------------------------------------------------------------------------------------------
def _last(m1, entry_min, exit_min, k, vol_win, sig):
    g = cm.grid(m1)
    EI, P, O = g["EI"], g["P"], g["O"]
    me = entry_min - 570
    cl = P[:, 390]
    pc = np.r_[np.nan, cl[:-1]]
    ref = pc if sig == "rod" else O
    x = P[:, me] / ref - 1
    side = np.sign(x)
    v = np.abs(P[:, 389] / P[:, me] - 1)
    vol = pd.Series(v).rolling(vol_win, min_periods=max(vol_win // 2, 1)).mean().shift(1).to_numpy()
    xi = _exit_index(m1, g, exit_min)
    ok = _session_ok(g) & np.isfinite(x) & (side != 0) & np.isfinite(vol) & (EI[:, me] >= 0) & (xi > EI[:, me])
    w = np.flatnonzero(ok)
    rows = {"entry_i": EI[w, me], "side": side[w].astype(np.int64), "stop_dist": k * vol[w] * P[w, me], "exit_i": xi[w]}
    return _frame(rows)


_RULES = {"ocm": _ocm, "orb": _orb, "noise": _noise, "last": _last}


def make_orders(m1, **params):
    p = resolve(params)
    rule = p.pop("rule")
    return _RULES[rule](m1, **p)


# Finalists (decided on the in-sample period only, before any validation access; see
# lab/results/r2/idx_us/finalists_preval.json).  One sleeve each, on us100.
FINALISTS = {
    # Noise-area intraday momentum, parameters of Zarattini, Aziz & Barbon (2024): band = average absolute move from
    # the 09:30 open to that time of day over the last 14 sessions, around max/min(open, previous 16:00 price);
    # checks at 10:00, 10:30, ..., 15:30 New York; in when outside the band, out when back inside at a check or at
    # 15:55; hard stop at the centre of the band (the open / previous-close reference).
    "noise30": {"syms": ["us100"],
                "params": {"rule": "noise", "lookback": 14, "first_min": 600, "step": 30, "last_min": 930,
                           "exit_min": 955, "vm": 1.0}},
    # Opening-candle momentum: direction of the first 4 minutes (09:30-09:34) when that move is at least the median
    # absolute 4-minute opening move of the previous 20 sessions; market entry at 09:34, stop 0.3 x ATR(14, daily),
    # flat at 15:55.
    "ocm4": {"syms": ["us100"],
             "params": {"rule": "ocm", "n": 4, "stop": "atr", "k": 0.3, "exit_min": 955, "size_min": 1.0,
                        "size_win": 20, "target_r": None, "atr_n": 14, "sides": "both"}},
}
