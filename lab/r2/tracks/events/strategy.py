"""Track `events` (round 2): trades around scheduled US macro releases.

    make_orders(m1, **params) -> orders DataFrame for goldlab.simulate  (works on ANY M1 frame)

Release calendar (calendars.py, dates known in advance): FOMC statement 14:00 New York, NFP and CPI
08:30 New York.  T = release time.  All clocks are New York wall clock (DST handled).

rule="long" / "short"   calendar trade: market order at T - lead minutes (lead > 0 = BEFORE the release;
                        lead < 0 = after it, e.g. lead=-5 -> T+5m), fixed side.
rule="mom" / "fade"     reaction trade: at T + k minutes, side = sign(last mid close before T+k  minus
                        last mid close before T)  ("fade" = the opposite side).  Skipped when the move is
                        smaller than min_move x ATR_D.  k >= 2: nothing is ever entered in the first
                        minute after a release.
rule="brk"              breakout bracket: reference range = mid high / low of the `pre_win` minutes
                        before T; from T + k minutes until T + valid minutes a buy-stop at
                        range high + buf_atr x ATR_D and a sell-stop at range low - buf_atr x ATR_D;
                        the side touched FIRST on M1 is the trade (both in one bar -> the side against
                        that bar's net move); if the price is already beyond a level at T + k the stop
                        order fills at the open (= market entry).

Exit (always a time exit, plus the protective stop):
    exit="hold"  -> at T + hold minutes
    exit="hhmm"  -> at `exit_hhmm` New York on the release day + `exit_days` business days
    (if the market is closed at that time, on the last bar before the closure)
Stop: stop_atr x ATR_D below / above the fill.  ATR_D = simple mean of the true range of the last
    `atr_n` COMPLETED trading days (day = 17:00 New York to 17:00 New York, i.e. the MT5 D1 bar of a
    GMT+2/+3 server; iATR(D1, atr_n) shifted by one bar).  Days with < 600 minutes of data are ignored.
A release is skipped when the market is not quoting at the decision time (no M1 bar within `tol` minutes).

Causality: every input is a bar that is complete at the decision time; verified by a truncation test
(orders built on a frame cut at random minutes == orders built on the full frame up to those minutes).
Warm-up: needs atr_n + 1 completed days before the first release (for the 2026 holdout load from
2025-11-01 and keep trades with entry >= 2026-01-01).
"""
import os
import sys

import numba as nb
import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_LAB = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
for _p in (_LAB, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import goldlab as gl  # noqa: E402
from calendars import release_times  # noqa: E402

NY = gl.NY
MIN = 60_000_000_000
DEFAULTS = {
    "rule": "long", "kinds": "fomc+nfp+cpi",
    "lead": 5,                    # long / short: minutes before T (negative = after)
    "k": 5, "min_move": 0.0,      # mom / fade / brk: minutes after T ; minimum move in ATR_D
    "pre_win": 30, "buf_atr": 0.0, "valid": 30,   # brk
    "exit": "hold", "hold": 15, "exit_hhmm": "15:55", "exit_days": 0,
    "stop_atr": 1.0, "atr_n": 14, "tol": 3,
}
COLS = ["entry_i", "side", "etype", "level", "expiry_i", "stop_dist", "exit_i", "kind", "t_rel", "atr"]
_cache = {}


def resolve(params):
    p = dict(DEFAULTS)
    for k, v in params.items():
        if k not in DEFAULTS:
            raise KeyError(f"unknown parameter {k}")
        p[k] = v
    return p


def _ns(idx):
    return pd.DatetimeIndex(idx).tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)


def _daily_atr(m1, n, min_minutes=600):
    """(close time ns, ATR) of completed trading days (17:00 New York boundary), mid prices, SMA of TR."""
    key = (len(m1), m1.index[0].value, m1.index[-1].value, int(n))
    if key not in _cache:
        if len(_cache) > 8:
            _cache.clear()
        ny = m1.index.tz_convert(NY)
        day = (ny + pd.Timedelta(hours=7)).tz_localize(None).normalize().values.astype("datetime64[D]").astype(np.int64)
        mh = (m1["bh"].to_numpy() + m1["ah"].to_numpy()) / 2
        ml = (m1["bl"].to_numpy() + m1["al"].to_numpy()) / 2
        mc = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2
        start = np.r_[0, np.flatnonzero(np.diff(day) != 0) + 1]
        end = np.r_[start[1:], len(day)]                       # exclusive
        cnt = end - start
        hi = np.maximum.reduceat(mh, start)
        lo = np.minimum.reduceat(ml, start)
        cl = mc[end - 1]
        tclose = m1.index.values.astype("datetime64[ns]").astype(np.int64)[end - 1] + MIN
        ok = cnt >= min_minutes
        hi, lo, cl, tclose = hi[ok], lo[ok], cl[ok], tclose[ok]
        pc = np.r_[np.nan, cl[:-1]]
        tr = np.fmax(hi - lo, np.fmax(np.abs(hi - pc), np.abs(lo - pc)))
        tr[0] = hi[0] - lo[0]
        atr = pd.Series(tr).rolling(int(n)).mean().to_numpy()
        _cache[key] = (tclose, atr)
    return _cache[key]


@nb.njit(cache=True)
def _first_touch(ah, bl, bo, bc, i0, i1, up, dn):
    """First M1 bar in [i0, i1] where ask-high >= up (buy stop) or bid-low <= dn (sell stop).
    Both inside the same bar -> the side AGAINST that bar's net move (adverse assumption)."""
    n = len(i0)
    N = len(ah)
    out_i = np.full(n, -1, np.int64)
    out_s = np.zeros(n, np.int64)
    for k in range(n):
        j1 = min(i1[k], N - 1)
        for j in range(i0[k], j1 + 1):
            b = ah[j] >= up[k]
            s = bl[j] <= dn[k]
            if b and s:
                out_i[k] = j
                out_s[k] = -1 if bc[j] >= bo[j] else 1
                break
            if b:
                out_i[k] = j
                out_s[k] = 1
                break
            if s:
                out_i[k] = j
                out_s[k] = -1
                break
    return out_i, out_s


def _empty():
    return pd.DataFrame({c: pd.Series(dtype="float64") for c in COLS}).astype({"entry_i": "int64", "side": "int64", "etype": "int64",
                                                                               "expiry_i": "int64", "exit_i": "int64"})


def make_orders(m1, **params):
    p = resolve(params)
    if len(m1) < 2:
        return _empty()
    ns = m1.index.values.astype("datetime64[ns]").astype(np.int64)
    N = len(ns)
    ev = release_times(p["kinds"])
    tn = _ns(ev.t)
    keep_ev = (tn > ns[0]) & (tn <= ns[-1])
    ev, tn = ev[keep_ev].reset_index(drop=True), tn[keep_ev]
    if len(ev) == 0:
        return _empty()
    T = pd.DatetimeIndex(ev.t)
    rule = p["rule"]
    tol = int(p["tol"]) * MIN
    mc = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2

    # ---- decision / entry bar -------------------------------------------------------------------
    if rule in ("long", "short"):
        tdec = tn - int(p["lead"]) * MIN
    elif rule in ("mom", "fade", "brk"):
        if int(p["k"]) < 2:
            raise ValueError("k >= 2: no entry in the first minute after a release")
        tdec = tn + int(p["k"]) * MIN
    else:
        raise ValueError(rule)
    ei = np.searchsorted(ns, tdec, side="left")
    ok = ei < N
    eic = np.minimum(ei, N - 1)
    ok &= (ns[eic] - tdec) <= tol                       # market is quoting at the decision time
    if rule in ("long", "short") and int(p["lead"]) > 0:
        ok &= ns[eic] < tn                              # entry strictly before the release minute
    ok &= ei > 0

    # ---- volatility unit: ATR of completed days at the decision time ----------------------------
    tcl, atr_d = _daily_atr(m1, p["atr_n"])
    j = np.searchsorted(tcl, tdec, side="right") - 1
    atr = np.where(j >= 0, atr_d[np.maximum(j, 0)], np.nan)
    ok &= np.isfinite(atr) & (atr > 0)

    # ---- time exit ------------------------------------------------------------------------------
    if p["exit"] == "hold":
        tx = T + pd.Timedelta(minutes=int(p["hold"]))
    elif p["exit"] == "hhmm":
        d = T.tz_convert(NY).tz_localize(None).normalize()
        if int(p["exit_days"]):
            d = d + pd.offsets.BDay(int(p["exit_days"]))
        h, m = (int(x) for x in str(p["exit_hhmm"]).split(":"))
        tx = (d + pd.Timedelta(hours=h, minutes=m)).tz_localize(NY).tz_convert("UTC")
    else:
        raise ValueError(p["exit"])
    xi = gl.exit_index(m1, tx)

    side = np.zeros(len(ev), np.int64)
    etype = np.zeros(len(ev), np.int64)
    level = np.full(len(ev), np.nan)
    expiry = np.full(len(ev), -1, np.int64)
    entry_i = eic.copy()

    if rule == "long":
        side[:] = 1
    elif rule == "short":
        side[:] = -1
    else:
        # last mid close strictly before the release minute (must be recent: within tol + 1 minutes)
        ip = np.searchsorted(ns, tn, side="left") - 1
        okp = ip >= 0
        ipc = np.maximum(ip, 0)
        okp &= (tn - ns[ipc]) <= tol + MIN
        ok &= okp
        if rule in ("mom", "fade"):
            il = eic - 1                                   # last completed bar before the decision
            okl = (il >= 0) & (ns[np.maximum(il, 0)] >= tn)   # ... and it must be a post-release bar
            ok &= okl
            move = mc[np.maximum(il, 0)] - mc[ipc]
            ok &= np.abs(move) >= float(p["min_move"]) * atr
            ok &= move != 0
            side = np.sign(move).astype(np.int64) * (1 if rule == "mom" else -1)
        else:  # brk
            a = np.searchsorted(ns, tn - int(p["pre_win"]) * MIN, side="left")
            b = np.searchsorted(ns, tn, side="left")       # bars in [T - pre_win, T)
            mh = (m1["bh"].to_numpy() + m1["ah"].to_numpy()) / 2
            ml = (m1["bl"].to_numpy() + m1["al"].to_numpy()) / 2
            hi = np.full(len(ev), np.nan)
            lo = np.full(len(ev), np.nan)
            for q in range(len(ev)):
                if b[q] - a[q] >= max(3, int(p["pre_win"]) // 3):
                    hi[q] = mh[a[q]:b[q]].max()
                    lo[q] = ml[a[q]:b[q]].min()
            ok &= np.isfinite(hi)
            up = hi + float(p["buf_atr"]) * atr
            dn = lo - float(p["buf_atr"]) * atr
            tend = tn + int(p["valid"]) * MIN
            i1 = np.searchsorted(ns, tend, side="right") - 1
            ok &= i1 >= eic
            hit_i, hit_s = _first_touch(m1["ah"].to_numpy(), m1["bl"].to_numpy(), m1["bo"].to_numpy(), m1["bc"].to_numpy(),
                                        eic.astype(np.int64), np.where(ok, i1, -1).astype(np.int64),
                                        np.where(ok, up, np.inf), np.where(ok, dn, -np.inf))
            ok &= hit_i >= 0
            side = hit_s
            etype[:] = 1
            level = np.where(side > 0, up, dn)
            expiry = hit_i.copy()

    ok &= xi > entry_i
    if rule == "brk":
        ok &= xi > expiry
    o = pd.DataFrame({
        "entry_i": entry_i[ok].astype(np.int64), "side": side[ok].astype(np.int64), "etype": etype[ok],
        "level": level[ok], "expiry_i": expiry[ok],
        "stop_dist": float(p["stop_atr"]) * atr[ok], "exit_i": xi[ok].astype(np.int64),
        "kind": ev.kind.to_numpy()[ok], "t_rel": T[ok], "atr": atr[ok],
    })
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


# Finalist (fixed on in-sample data 2013-2021 only, BEFORE any validation access; see
# results/r2/events/finalists_preval.json).  One rule, one parameter set, two index sleeves:
#   EV_PREM_LONG  "announcement premium": buy the index 5 minutes BEFORE every scheduled FOMC statement
#                 (14:00 NY), NFP and CPI release (08:30 NY), protective stop 1.0 x ATR_D(14) below the
#                 fill, close the position 15 minutes AFTER the release.  No entry and no planned exit in
#                 the first minute after a release.  us500 and us100 are the SAME bet (R correlation 0.94
#                 in sample): count them as one sleeve when sizing.
# OUTCOME (single-shot validation 2022-2025, results/r2/events/validation.json): passed every in-sample
# criterion (PF 1.60 / 1.64, t 2.65 / 2.75) and FAILED validation on both sleeves (PF 0.91 / 0.89).
# It does NOT enter the portfolio.  The entry is kept unchanged for the record and for the holdout re-run.
FINALISTS = {
    "EV_PREM_LONG": {
        "syms": ["us500", "us100"],
        "params": {"rule": "long", "kinds": "fomc+nfp+cpi", "lead": 5, "exit": "hold", "hold": 15,
                   "stop_atr": 1.0, "atr_n": 14},
    },
}
