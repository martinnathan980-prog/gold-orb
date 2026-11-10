"""leadlag track (round 2) - order generators.  Causal; work on ANY M1 frame of the traded market.

    make_orders(m1, rule=..., **params) -> orders DataFrame for goldlab.simulate / r2.evaluate

`m1` is the M1 bid/ask frame of the TRADED market (the "follower").  Cross-asset rules also need the M1
mid closes of one or two other markets (the "leaders").  By default they are read lazily from the lab's
research files (lab/data/fp/<sym>_m1.parquet, which stop on 2025-12-31).  For the 2026 holdout or live
parity, register the leader data FIRST:

    import strategy
    strategy.set_leader("us100", m1_us100_frame)      # an M1 bid/ask frame, or a Series of mid closes
    orders = strategy.make_orders(m1_btc, **strategy.FINALISTS[name]["params"])

WARM-UP: the volatility units use the previous 20 calendar days.  A short frame (the holdout) must start
>= 25 days BEFORE the first date on which trades are counted, for the follower AND the leader (checked:
on a frame starting 2025-06-01 the orders from 2025-07-01 on are identical to the full-history orders;
results/r2/leadlag/portability_nq_btc.json).  The leader must cover the same period as the follower frame.

Conventions: bars are labelled by their START (UTC) and known one minute later.  A decision made on the
bar labelled t uses only bars labelled <= t (leader AND follower) and is executed at the OPEN of the first
follower bar labelled >= t+1min (market order).  All statistics (sigma, beta) are trailing and lagged.

Rules
-----
rule="xlead"   cross-asset impulse rule (one leader):
    leader   symbol of the leader market
    pred     "lead"  : x = leader log-return over the last k minutes
             "resid" : x = beta * leader k-min return - follower k-min return (leader move NOT matched by
                       the follower; beta = trailing 20-day slope of follower 5-min returns on leader 5-min
                       returns, lagged)
             "own"   : x = - follower k-min return (ablation: plain reversal, no leader)
    k        look-back in minutes
    z        threshold: signal when |x| >= z * sigma_x, sigma_x = RMS of x over the bars of the last
             `sig_days` days (lagged one minute)
    sess     decision window (see SESSIONS); the planned exit must also fall before the window's `end`
             when the window says so
    hold     minutes in the trade (time exit at the open of the bar `hold` minutes after the entry bar)
    stop     stop distance = stop * sigma_F1 * sqrt(hold) * price, sigma_F1 = trailing RMS of the follower's
             1-minute log returns (same window)
    dirn     +1 trade in the direction of sign(x) (default), -1 against it
    delay    extra minutes between the decision and the entry (0 = next minute; > 0 only for timing probes)
rule="relstr"  relative strength between index CFDs (two peers):
    peers    the two other symbols
    T        decision minute of the New-York day (e.g. 600 = 10:00): uses bars labelled < T, enters at T
    ref      "open" (return since the 09:30 bar open) | "prevclose" (since the previous 15:59 bar close)
    disp     trade only if (max - min) of the three returns >= disp * trailing median of that dispersion
             over the last 60 sessions (0 = every day)
    xmin     exit minute of the New-York day (959 = 15:59)
    stop     stop distance = stop * sigma_F1 * sqrt(minutes to exit) * price
    Long the strongest, short the weakest: the frame's market gets +1 / -1 / no order.
"""
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402

NY = "America/New_York"
BERLIN = "Europe/Berlin"
MIN_NS = 60_000_000_000

# ----------------------------------------------------------------------------------------- leaders
_LEADERS = {}          # sym -> (tmin int64 [minutes since epoch, bar START], mid close float64, mid open float64)


def _tmin(index):
    return (pd.DatetimeIndex(index).tz_convert("UTC").as_unit("ns").asi8 // MIN_NS).astype(np.int64)


def set_leader(sym, obj):
    """Register leader data: an M1 bid/ask frame (cols bo bc ao ac ...) or a Series of mid closes
    indexed by UTC bar start.  Use it for the holdout / live parity, and for truncation tests."""
    if isinstance(obj, pd.Series):
        _LEADERS[sym] = (_tmin(obj.index), obj.to_numpy(np.float64), None)
    else:
        mo = ((obj["bo"] + obj["ao"]) / 2).to_numpy(np.float64) if "bo" in obj else None
        _LEADERS[sym] = (_tmin(obj.index), ((obj["bc"] + obj["ac"]) / 2).to_numpy(np.float64), mo)


def clear_leaders():
    _LEADERS.clear()


def _leader(sym):
    if sym not in _LEADERS:      # research default: FP research file (ends 2025-12-31), mid only
        df = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), columns=["bo", "ao", "bc", "ac"])
        df = df[df.index < pd.Timestamp("2026-01-01", tz="UTC")]
        set_leader(sym, df)
    return _LEADERS[sym]


# ----------------------------------------------------------------------------------------- helpers
def _grid(m1):
    """Regular one-minute grid over the frame: t0, n, position of each follower bar."""
    tm = _tmin(m1.index)
    t0 = int(tm[0])
    n = int(tm[-1]) - t0 + 1
    return tm, t0, n


def _on_grid(tm, v, t0, n):
    out = np.full(n, np.nan)
    keep = (tm >= t0) & (tm < t0 + n)
    out[tm[keep] - t0] = v[keep]
    return out


def _ffill(c, limit=3):
    n = len(c)
    has = np.isfinite(c)
    last = np.where(has, np.arange(n), -1)
    np.maximum.accumulate(last, out=last)
    ok = (last >= 0) & (np.arange(n) - last <= limit)
    return np.where(ok, c[np.maximum(last, 0)], np.nan)


def _lret(c, k):
    out = np.full(len(c), np.nan)
    out[k:] = np.log(c[k:] / c[:-k])
    return out


def _trail_rms(x, win, minobs):
    """RMS of x over the last `win` grid minutes (NaN skipped), lagged one minute."""
    v = np.isfinite(x)
    s2 = pd.Series(np.where(v, x * x, 0.0)).rolling(win, min_periods=1).sum().to_numpy()
    cnt = pd.Series(v.astype(np.float64)).rolling(win, min_periods=1).sum().to_numpy()
    s = np.where(cnt >= minobs, np.sqrt(np.maximum(s2, 0.0) / np.maximum(cnt, 1.0)), np.nan)
    return np.r_[np.nan, s[:-1]]


def _trail_beta(cl, cf, t0, win_slots=5760, minobs=1000):
    """Trailing slope (through the origin) of follower 5-min returns on leader 5-min returns, sampled on
    non-overlapping 5-minute slots anchored on absolute time (bars labelled hh:m4 / hh:m9), over the last
    `win_slots` slots (20 days), lagged one slot, forward-filled to minutes."""
    n = len(cl)
    rl = _lret(cl, 5)
    rf = _lret(cf, 5)
    sl = slice(int((4 - t0) % 5), None, 5)
    x, y = rl[sl], rf[sl]
    v = np.isfinite(x) & np.isfinite(y)
    xx = np.where(v, x, 0.0)
    yy = np.where(v, y, 0.0)
    sxy = pd.Series(xx * yy).rolling(win_slots, min_periods=1).sum().to_numpy()
    sxx = pd.Series(xx * xx).rolling(win_slots, min_periods=1).sum().to_numpy()
    cnt = pd.Series(v.astype(np.float64)).rolling(win_slots, min_periods=1).sum().to_numpy()
    b = np.where((cnt >= minobs) & (sxx > 0), sxy / np.where(sxx > 0, sxx, 1.0), np.nan)
    b = np.r_[np.nan, b[:-1]]
    beta = np.full(n, np.nan)
    beta[sl] = b
    return pd.Series(beta).ffill(limit=5).to_numpy()


def _clock(t0, n):
    ts = pd.DatetimeIndex((np.arange(n, dtype=np.int64) + t0) * MIN_NS, tz="UTC")
    ny = ts.tz_convert(NY)
    be = ts.tz_convert(BERLIN)
    return (ny.hour * 60 + ny.minute).to_numpy(), (be.hour * 60 + be.minute).to_numpy(), ny.dayofweek.to_numpy()


# decision windows: (clock, first minute, last minute (exclusive), planned exit must be <= end?)
SESSIONS = {
    "uscash": ("ny", 570, 960, False),        # 09:30-16:00 New York
    "us_am": ("ny", 570, 720, False),         # 09:30-12:00 New York
    "us_pmh": ("ny", 720, 960, False),        # 12:00-16:00 New York
    "us_ext": ("ny", 480, 960, False),        # 08:00-16:00 New York
    "eu_am": ("be", 480, 540, False),         # 08:00-09:00 Berlin (Eurex open, before the Xetra open)
    "eurex_pm": ("be", 1050, 1320, True),     # 17:30-22:00 Berlin (after the Xetra close), exit <= 22:00
    "xetra": ("be", 540, 1050, True),         # 09:00-17:30 Berlin, exit <= 17:30
    "eu_day": ("be", 480, 1320, True),        # 08:00-22:00 Berlin
    "all": ("ny", 0, 1440, False),
}


def _sess_mask(sess, nym, bem, wd, hold):
    clock, a, b, exit_inside = SESSIONS[sess]
    m = nym if clock == "ny" else bem
    last = b - hold - 1 if exit_inside else b
    return (m >= a) & (m < last) & (wd < 5)


# ----------------------------------------------------------------------------------------- xlead
def xlead_orders(m1, leader="us100", pred="lead", k=5, z=4.0, sess="uscash", hold=30, stop=1.5, dirn=1,
                 sig_days=20, delay=0, **_):
    tm, t0, n = _grid(m1)
    mid_c = ((m1["bc"] + m1["ac"]) / 2).to_numpy(np.float64)
    cF_raw = _on_grid(tm, mid_c, t0, n)
    hasF = np.isfinite(cF_raw)
    cF = _ffill(cF_raw)
    win = int(sig_days) * 1440
    minobs = win // 6
    rF1 = np.where(hasF, _lret(cF, 1), np.nan)
    sigF1 = _trail_rms(rF1, win, minobs)
    if pred == "own":
        hasL = hasF
        x = -_lret(cF, k)
    else:
        ltm, lc, _ = _leader(leader)
        cL_raw = _on_grid(ltm, lc, t0, n)
        hasL = np.isfinite(cL_raw)
        cL = _ffill(cL_raw)
        rL = _lret(cL, k)
        if pred == "lead":
            x = rL
        elif pred == "resid":
            x = _trail_beta(cL, cF, t0) * rL - _lret(cF, k)
        else:
            raise ValueError(pred)
    x = np.where(hasL, x, np.nan)                 # the leader must have printed in the decision minute
    sigX = _trail_rms(x, win, minobs)
    nym, bem, wd = _clock(t0, n)
    sig = _sess_mask(sess, nym, bem, wd, hold) & np.isfinite(x) & np.isfinite(sigX) & (np.abs(x) >= z * sigX) \
        & np.isfinite(sigF1) & hasF
    g = np.flatnonzero(sig)                       # decision bars (grid positions); known at g+1
    if len(g) == 0:
        return _empty()
    d = int(delay)                                # robustness probe: enter `delay` minutes late (default 0)
    ei = np.searchsorted(tm, t0 + g + 1 + d, side="left")
    ok = ei < len(tm)
    g, ei = g[ok], ei[ok]
    ok = (tm[ei] - (t0 + g + 1 + d)) <= 1         # the follower must trade within a minute of the decision
    g, ei = g[ok], ei[ok]
    entry_t = m1.index[ei]
    xi = gl.exit_index(m1, entry_t + pd.Timedelta(minutes=int(hold)))
    px = mid_c[ei - 1]                            # last follower close before the entry (known)
    o = pd.DataFrame({
        "entry_i": ei.astype(np.int64),
        "side": (np.sign(x[g]) * int(dirn)).astype(np.int64),
        "stop_dist": float(stop) * sigF1[g] * np.sqrt(float(hold)) * px,
        "exit_i": xi.astype(np.int64),
    })
    o = o[(o.exit_i > o.entry_i) & np.isfinite(o.stop_dist) & (o.stop_dist > 0) & (o.side != 0)]
    return o.drop_duplicates("entry_i").reset_index(drop=True)


# ----------------------------------------------------------------------------------------- relstr
def relstr_orders(m1, peers=("us500", "us30"), T=600, ref="open", disp=1.0, xmin=959, stop=3.0,
                  sig_days=20, disp_days=60, **_):
    tm, t0, n = _grid(m1)
    mid_c = ((m1["bc"] + m1["ac"]) / 2).to_numpy(np.float64)
    mid_o = ((m1["bo"] + m1["ao"]) / 2).to_numpy(np.float64)
    C = [_on_grid(tm, mid_c, t0, n)]
    O = [_on_grid(tm, mid_o, t0, n)]
    for p in peers:
        ltm, lc, lo = _leader(p)
        C.append(_on_grid(ltm, lc, t0, n))
        O.append(_on_grid(ltm, lo if lo is not None else lc, t0, n))
    hasF = np.isfinite(C[0])
    Cf = [_ffill(c, 2) for c in C]
    win = int(sig_days) * 1440
    sigF1 = _trail_rms(np.where(hasF, _lret(Cf[0], 1), np.nan), win, win // 6)
    nym, bem, wd = _clock(t0, n)
    del bem
    T, xmin = int(T), int(xmin)
    gT = np.flatnonzero((nym == T) & (wd < 5))                  # grid position of the entry bar, one per day
    if len(gT) == 0:
        return _empty()
    go = gT - (T - 570)                                         # 09:30 bar of the same day (same DST regime)
    gx = gT + (xmin - T)                                        # exit bar
    okd = (go >= 0) & (gx < n) & (gT - 1 >= 0)
    gT, go, gx = gT[okd], go[okd], gx[okd]
    okd = (nym[go] == 570) & (nym[gx] == xmin)
    gT, go, gx = gT[okd], go[okd], gx[okd]
    R = []
    if ref == "open":
        for c, o in zip(Cf, O):
            R.append(np.log(c[gT - 1] / o[go]))
    elif ref == "prevclose":
        # previous session's 15:59 bar close: last grid position with nym == 959 before today's 09:30
        pc = np.flatnonzero((nym == 959) & (wd < 5))
        j = np.searchsorted(pc, go, side="left") - 1
        okp = j >= 0
        base = pc[np.maximum(j, 0)]
        for c in Cf:
            v = np.log(c[gT - 1] / c[base])
            v[~okp | ((go - base) > 5 * 1440)] = np.nan
            R.append(v)
    else:
        raise ValueError(ref)
    R = np.vstack(R).T                                          # days x 3, column 0 = this market
    okr = np.isfinite(R).all(axis=1)
    Rz = np.where(okr[:, None], R, 0.0)
    rmax, rmin = Rz.max(axis=1), Rz.min(axis=1)
    D = np.where(okr, rmax - rmin, np.nan)
    med = pd.Series(D).rolling(int(disp_days), min_periods=20).median().shift(1).to_numpy()
    rank_hi = okr & (Rz[:, 0] >= rmax) & (rmax > rmin)
    rank_lo = okr & (Rz[:, 0] <= rmin) & (rmax > rmin)
    side = np.where(rank_hi, 1, np.where(rank_lo, -1, 0))
    take = (side != 0) & np.isfinite(med) & (D >= float(disp) * med) & np.isfinite(sigF1[gT - 1]) & hasF[gT] & hasF[gT - 1]
    gT, gx, side = gT[take], gx[take], side[take]
    ei = np.searchsorted(tm, t0 + gT, side="left")              # the entry bar exists (hasF[gT])
    xi = gl.exit_index(m1, pd.DatetimeIndex((t0 + gx) * MIN_NS, tz="UTC"))
    o = pd.DataFrame({
        "entry_i": ei.astype(np.int64),
        "side": side.astype(np.int64),
        "stop_dist": float(stop) * sigF1[gT - 1] * np.sqrt(float(xmin - T)) * mid_c[ei - 1],
        "exit_i": xi.astype(np.int64),
    })
    o = o[(o.exit_i > o.entry_i) & np.isfinite(o.stop_dist) & (o.stop_dist > 0)]
    return o.reset_index(drop=True)


def _empty():
    return pd.DataFrame({"entry_i": np.array([], np.int64), "side": np.array([], np.int64),
                         "stop_dist": np.array([], float), "exit_i": np.array([], np.int64)})


RULES = {"xlead": xlead_orders, "relstr": relstr_orders}


def make_orders(m1, rule="xlead", **params):
    """Order generator of the leadlag track (see module docstring)."""
    return RULES[rule](m1, **params)


# Decided on in-sample data only, BEFORE any validation access (results/r2/leadlag/finalists_preval.json).
#
# nq_btc_follow  "bitcoin follows a Nasdaq impulse": during New-York cash hours (09:30-16:00 NY, Mon-Fri), when
#   the Nasdaq-100 CFD's last closed 1-minute bar moved by at least 6 sigma (sigma = RMS of its 1-minute
#   log returns over the M1 bars of the previous 20 calendar days), buy (impulse up) / sell (impulse down)
#   BTCUSD at market at the next minute; protective stop 2 * sigma_btc(1 min, same 20-day window) * sqrt(60)
#   from the fill (about 1.2-1.5 % of price); exit at market 60 minutes after the entry; one position at a time.
FINALISTS = {
    "nq_btc_follow": {
        "syms": ["btcusd"],
        "params": {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1,
                   "k": 1, "z": 6, "hold": 60, "stop": 2.0},
    },
}
