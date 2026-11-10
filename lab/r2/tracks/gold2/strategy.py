"""Track `gold2` (round 2): xauusd / xagusd sleeves under FP Markets Standard costs.

    make_orders(m1, **params) -> orders DataFrame for goldlab.sim.simulate   (works on ANY M1 frame)
    FINALISTS = {name: {"syms": [...], "params": {...}}}

`params["family"]` selects the rule (every other key has a default in DEFAULTS[family]):

  "orb"    session opening-range breakout.  Range = M1 bars whose START is in [range_start, range_end) of
           the session clock (London or New York wall clock, DST per date); high = max ASK, low = min BID.
           From range_end to entry_end an OCO pair is live: buy-stop at high + buf, sell-stop at low - buf
           (buf = buf_frac x width).  First touch wins (resolved here on M1; both in the same minute ->
           the adverse side).  Stop = the opposite level.  Forced exit at exit_min (exit_tz wall clock) of
           the same date + hold_days business days.          [round-1 `orb` rules]
  "rn"     first touch of a round number.  At the start of the trading day (17:00 New York) take the
           nearest multiple of `grid` above and below the price; between win_start (London clock) and
           win_end (New York clock) a buy-stop rests at the upper one and a sell-stop at the lower one,
           each valid only if that level has not been touched since the day started.  Stop stop_atr x
           ATR14(daily, previous full days) back through the level, target tgt_r x risk, forced exit
           exit_ny.                                           [round-1 `pivots` finalist]
  "donch"  channel breakout with stop entries on `tf`-minute bars (UTC grid).  After each bar close an
           OCO pair is live until the next bar close: buy-stop at the highest mid high, sell-stop at the
           lowest mid low of the last n bars (the bar just closed included).  Initial stop stop_atr x
           ATR(atr_n) of the tf bars, trailing stop trail_atr x ATR, time stop max_days trading days.
           Optional: `sess` (London-clock window in which a bracket may be placed), `trend_n` (only the
           side of the slower n-bar channel state), `squeeze` (only if the channel is narrow).
                                                               [round-1 legacy rule, generalised]
  "pullback" pullback inside a trend: trend = side of the last touched extreme of the slow channel
           (trend_n bars); after a bar closes at a new pb_n-bar low (uptrend) a buy-stop rests at that
           bar's high until the next bar close (mirror for downtrends); stop under the pullback low.

Causality: every indicator uses completed bars only (a bar [t, t+tf) is used from the first M1 bar that
starts at or after its end), rolling windows look back only, daily values come from completed trading
days.  Truncation test: see results/r2/gold2/causality.json.

Warm-up: ATR is a Wilder EWM started on the first bar of the frame and the channels need n bars, so
give make_orders a frame that starts >= 2 months before the first trade of interest.
"""
import os
import sys

import numba as nb
import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

_LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if _LAB not in sys.path:
    sys.path.insert(0, _LAB)
import goldlab as gl  # noqa: E402

NY, LDN = gl.NY, gl.LDN
TZ = {"NY": NY, "LDN": LDN}
NAN = float("nan")

DEFAULTS = {
    "orb": dict(tz="LDN", range_start=480, range_end=510, entry_end=720, exit_min=960, exit_tz="NY",
                hold_days=0, buf_frac=0.0, min_bars_frac=0.5, sides="both"),
    "rn": dict(grid=100.0, win_start_ldn=480, win_end_ny=720, exit_ny=960, stop_atr=0.4, tgt_r=1.0,
               atr_n=14, min_bars=600),
    "donch": dict(tf=60, n=120, atr_n=14, stop_atr=2.0, trail_atr=2.0, max_days=5, sides="both",
                  sess_start=-1, sess_end=-1, trend_n=0, squeeze=0.0, squeeze_ref=0),
    "pullback": dict(tf=60, trend_n=240, pb_n=24, atr_n=14, stop_buf=0.25, trail_atr=2.0, max_days=5,
                     sides="both"),
}

# optional parameters, listed in the resolved set only when they differ from their neutral value
OPTIONAL = {
    "donch": {"delay_min": 0},      # timing probe: the bracket becomes active this many minutes late
}

_CTX = {}


# ----------------------------------------------------------------------------------------------
# context (per M1 frame): raw arrays, clocks, bars
# ----------------------------------------------------------------------------------------------
def _fingerprint(m1):
    n = len(m1)
    step = max(1, n // 1009)
    bc = m1["bc"].to_numpy()
    ac = m1["ac"].to_numpy()
    return (n, int(m1.index[0].value), int(m1.index[-1].value), float(bc[::step].sum()), float(ac[::step].sum()))


def context(m1):
    """Arrays and derived tables for one M1 frame, cached on a content fingerprint (the cost-stress and
    gross runs pass re-quoted copies of the frame: each gets its own context)."""
    key = _fingerprint(m1)
    c = _CTX.get(key)
    if c is not None:
        return c
    while len(_CTX) >= 2:
        _CTX.pop(next(iter(_CTX)))
    c = {"N": len(m1), "idx": m1.index}
    for col in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"):
        c[col] = np.ascontiguousarray(m1[col].to_numpy(np.float64))
    c["t"] = m1.index.values.astype("datetime64[m]").astype(np.int64)      # UTC minutes since epoch
    _CTX[key] = c
    return c


def _wall(c, tz):
    """Wall-clock minutes since epoch (naive) of every M1 bar in time zone `tz` ('NY' / 'LDN')."""
    k = "wall_" + tz
    if k not in c:
        c[k] = c["idx"].tz_convert(TZ[tz]).tz_localize(None).values.astype("datetime64[m]").astype(np.int64)
    return c[k]


def _clock(dates, minutes, tz):
    """UTC minutes since epoch of wall-clock `minutes` after local midnight on each naive date (-1 if the
    local time does not exist / is ambiguous)."""
    loc = (pd.DatetimeIndex(dates) + pd.to_timedelta(int(minutes), unit="min")).tz_localize(
        TZ[tz], ambiguous="NaT", nonexistent="shift_forward")
    u = loc.tz_convert("UTC").tz_localize(None)
    out = u.values.astype("datetime64[m]").astype(np.int64)
    out[np.asarray(u.isna())] = -1
    return out


def _exit_idx(c, tmin):
    """M1 index at whose OPEN a time exit scheduled at UTC minute `tmin` executes; inside a closure
    (next bar > 30 min later, or beyond the data) -> the last bar BEFORE it (same as gl.exit_index)."""
    t = c["t"]
    tmin = np.asarray(tmin, np.int64)
    xi = np.searchsorted(t, tmin, side="left").astype(np.int64)
    nxt = t[np.clip(xi, 0, len(t) - 1)]
    gap = (xi >= len(t)) | ((nxt - tmin) > 30)
    return np.where(gap & (xi > 0), xi - 1, xi).astype(np.int64)


def _add_trading_days(tmin, n):
    """Shift UTC minutes by n New-York trading days (17:00 NY boundary), keeping the NY wall clock."""
    ts = pd.DatetimeIndex(np.asarray(tmin, np.int64).astype("datetime64[m]").astype("datetime64[ns]"), tz="UTC")
    ny = ts.tz_convert(NY).tz_localize(None)
    sh = (ny + pd.Timedelta(hours=7)) + BDay(int(n)) - pd.Timedelta(hours=7)
    u = pd.DatetimeIndex(sh).tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC").tz_localize(None)
    out = u.values.astype("datetime64[m]").astype(np.int64)
    out[np.asarray(u.isna())] = -1
    return out


def bars(c, tf):
    """Mid-price bars of `tf` minutes on the UTC grid.  st/en = first / one-past-last M1 index of each bar;
    a bar is usable from M1 index `en` on (first M1 bar after it); t_close = last minute + 1 (UTC minutes)."""
    k = ("bars", int(tf))
    if k not in c:
        t = c["t"]
        g = t // int(tf)
        st = np.flatnonzero(np.r_[True, g[1:] != g[:-1]]).astype(np.int64)
        en = np.r_[st[1:], len(t)].astype(np.int64)
        b = {
            "st": st, "en": en, "t_close": t[en - 1] + 1, "t_start": g[st] * int(tf),
            "o": (c["bo"][st] + c["ao"][st]) / 2,
            "h": (np.maximum.reduceat(c["bh"], st) + np.maximum.reduceat(c["ah"], st)) / 2,
            "l": (np.minimum.reduceat(c["bl"], st) + np.minimum.reduceat(c["al"], st)) / 2,
            "c": (c["bc"][en - 1] + c["ac"][en - 1]) / 2,
        }
        c[k] = b
    return c[k]


def atr(b, n):
    """Wilder ATR on mid bars (same recursion as gl.atr: EWM alpha = 1/n from the first bar)."""
    k = ("atr", int(n))
    if k not in b:
        h, l, cl = b["h"], b["l"], b["c"]
        pc = np.r_[np.nan, cl[:-1]]
        tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
        b[k] = pd.Series(tr).ewm(alpha=1.0 / int(n), adjust=False).mean().to_numpy()
    return b[k]


def days(c, min_bars=600):
    """Trading days (17:00 New York boundary) with BID OHLC, like an MT5 D1 bar.  `full` = at least
    min_bars M1 bars (holiday stubs and data holes are not used for levels and not traded)."""
    k = ("days", int(min_bars))
    if k not in c:
        ny = _wall(c, "NY")
        td = (ny + 420) // 1440
        s = np.flatnonzero(np.r_[True, td[1:] != td[:-1]]).astype(np.int64)
        e = np.r_[s[1:], len(td)].astype(np.int64)
        d = {"s": s, "e": e, "td": td[s], "full": (e - s) >= int(min_bars),
             "O": c["bo"][s], "H": np.maximum.reduceat(c["bh"], s), "L": np.minimum.reduceat(c["bl"], s),
             "C": c["bc"][e - 1]}
        c[k] = d
    return c[k]


# ----------------------------------------------------------------------------------------------
# numba kernels (cache=False on purpose: numba's on-disk cache breaks when the same file is imported
# under two module names, which the lab's loaders do -- see the engine notes of the gold2 report)
# ----------------------------------------------------------------------------------------------
@nb.njit(cache=False)
def _first_touch(ah, bl, bo, bc, i0, i1, up, dn):
    """First M1 bar in [i0, i1] where ask-high >= up (buy-stop) or bid-low <= dn (sell-stop).
    Returns (bar index or -1, side).  Both levels inside the same bar -> the adverse side, i.e. the one
    AGAINST that bar's net move (it filled first, then the bar reversed through it)."""
    n = len(i0)
    N = len(ah)
    out_i = np.full(n, -1, np.int64)
    out_s = np.zeros(n, np.int64)
    for k in range(n):
        if i0[k] < 0:
            continue
        j1 = min(i1[k], N - 1)
        for i in range(i0[k], j1 + 1):
            hu = ah[i] >= up[k]
            hd = bl[i] <= dn[k]
            if hu and hd:
                out_i[k] = i
                out_s[k] = -1 if bc[i] >= bo[i] else 1
                break
            if hu:
                out_i[k] = i
                out_s[k] = 1
                break
            if hd:
                out_i[k] = i
                out_s[k] = -1
                break
    return out_i, out_s


@nb.njit(cache=False)
def _range_hl(ah, bl, i0, i1):
    n = len(i0)
    hi = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    for k in range(n):
        if i1[k] > i0[k]:
            h = -1e300
            q = 1e300
            for i in range(i0[k], i1[k]):
                if ah[i] > h:
                    h = ah[i]
                if bl[i] < q:
                    q = bl[i]
            hi[k] = h
            lo[k] = q
    return hi, lo


@nb.njit(cache=False)
def _rn_touch(ah, bl, a, ws, we, rb, ra):
    """Per day: first bar in [a, we) where bid-low <= rb (lower level) / ask-high >= ra (upper level);
    kept only if that first touch of the day is at or after ws (the level is still 'fresh')."""
    n = len(a)
    hb = np.full(n, -1, np.int64)
    ha = np.full(n, -1, np.int64)
    for k in range(n):
        if a[k] < 0 or ws[k] < 0:
            continue
        if not np.isnan(rb[k]):
            for i in range(a[k], we[k]):
                if bl[i] <= rb[k]:
                    if i >= ws[k]:
                        hb[k] = i
                    break
        if not np.isnan(ra[k]):
            for i in range(a[k], we[k]):
                if ah[i] >= ra[k]:
                    if i >= ws[k]:
                        ha[k] = i
                    break
    return hb, ha


# ----------------------------------------------------------------------------------------------
# families
# ----------------------------------------------------------------------------------------------
def _empty():
    return pd.DataFrame({"entry_i": np.zeros(0, np.int64), "side": np.zeros(0, np.int64),
                         "etype": np.zeros(0, np.int64), "level": np.zeros(0), "expiry_i": np.zeros(0, np.int64),
                         "stop": np.zeros(0), "exit_i": np.zeros(0, np.int64)})


def _side_ok(side, sides):
    if sides == "long":
        return side > 0
    if sides == "short":
        return side < 0
    return side != 0


def _orb(c, p):
    idx = c["idx"]
    tz = p["tz"]
    loc = idx[[0, -1]].tz_convert(TZ[tz]).tz_localize(None).normalize()
    dates = pd.date_range(loc[0], loc[1], freq="D")
    dates = dates[dates.dayofweek < 5]
    rs = _clock(dates, p["range_start"], tz)
    re = _clock(dates, p["range_end"], tz)
    ee = _clock(dates, p["entry_end"], tz)
    xd = dates + BDay(int(p["hold_days"])) if int(p["hold_days"]) else dates
    xt = _clock(xd, p["exit_min"], p["exit_tz"])
    t = c["t"]
    N = c["N"]
    i0 = np.searchsorted(t, rs).astype(np.int64)
    i1 = np.searchsorted(t, re).astype(np.int64)
    ie = np.searchsorted(t, ee).astype(np.int64)
    ix = _exit_idx(c, xt)
    ok = (rs >= 0) & (re >= 0) & (ee >= 0) & (xt >= 0)
    ok &= (i1 - i0) >= float(p["min_bars_frac"]) * (re - rs)
    ok &= (i1 < N) & (ie > i1)
    hi, lo = _range_hl(c["ah"], c["bl"], i0, i1)
    ok &= np.isfinite(hi) & np.isfinite(lo) & (hi > lo)
    w = hi - lo
    buf = float(p["buf_frac"]) * w
    up, dn = hi + buf, lo - buf
    a0 = np.where(ok, i1, -1).astype(np.int64)
    fi, side = _first_touch(c["ah"], c["bl"], c["bo"], c["bc"], a0, (ie - 1).astype(np.int64),
                            np.nan_to_num(up, nan=np.inf), np.nan_to_num(dn, nan=-np.inf))
    ok &= (fi >= 0) & _side_ok(side, p["sides"]) & (ix > fi)
    side = side[ok]
    o = pd.DataFrame({
        "entry_i": fi[ok], "side": side, "etype": 1,
        "level": np.where(side > 0, up[ok], dn[ok]), "expiry_i": fi[ok],
        "stop": np.where(side > 0, dn[ok], up[ok]), "exit_i": ix[ok],
        "trig_i": fi[ok], "width": w[ok],
    })
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


def _rn(c, p):
    d = days(c, p["min_bars"])
    s, e, full = d["s"], d["e"], d["full"]
    nd = len(s)
    # ATR: 14-day simple mean of the true range of the previous FULL days (bid prices), known before the day
    fk = np.flatnonzero(full)
    H, L, C = d["H"][fk], d["L"][fk], d["C"][fk]
    pc = np.r_[np.nan, C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    a_full = pd.Series(tr).rolling(int(p["atr_n"]), min_periods=int(p["atr_n"])).mean().shift(1).to_numpy()
    atr_d = np.full(nd, np.nan)
    atr_d[fk] = a_full
    ny, ldn = _wall(c, "NY"), _wall(c, "LDN")
    base = d["td"] * 1440
    a = np.full(nd, -1, np.int64)
    ws = np.full(nd, -1, np.int64)
    we = np.full(nd, -1, np.int64)
    ex = np.full(nd, -1, np.int64)
    for k in fk:
        if not np.isfinite(atr_d[k]):
            continue
        i_a, i_b = s[k], e[k]
        j0 = i_a + np.searchsorted(ldn[i_a:i_b] - base[k], int(p["win_start_ldn"]), side="left")
        j1 = i_a + np.searchsorted(ny[i_a:i_b] - base[k], int(p["win_end_ny"]), side="left")
        jx = min(i_a + np.searchsorted(ny[i_a:i_b] - base[k], int(p["exit_ny"]), side="left"), i_b - 1)
        if j0 < j1 and j0 < i_b:
            a[k], ws[k], we[k], ex[k] = i_a, j0, min(j1, jx), jx
    grid = float(p["grid"])
    p0 = np.where(a >= 0, c["bo"][np.maximum(a, 0)], np.nan)
    rb = np.floor(p0 / grid) * grid
    ra = rb + grid
    rb = np.where(rb < p0, rb, np.nan)          # price exactly on a level: no order at that level
    hb, ha = _rn_touch(c["ah"], c["bl"], a, ws, we, rb, ra)
    rows = []
    for hit, lv, side in ((hb, rb, -1), (ha, ra, 1)):
        kk = np.flatnonzero(hit >= 0)
        sd = float(p["stop_atr"]) * atr_d[kk]
        rows.append(pd.DataFrame({
            "entry_i": hit[kk], "side": side, "etype": 1, "level": lv[kk], "expiry_i": we[kk] - 1,
            "stop": lv[kk] - side * sd, "target": lv[kk] + side * float(p["tgt_r"]) * sd,
            "exit_i": ex[kk], "trig_i": hit[kk], "atr_d": atr_d[kk],
        }))
    o = pd.concat(rows, ignore_index=True)
    o = o[(o.entry_i < o.exit_i) & np.isfinite(o.stop)]
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


def _sess_mask(c, i, p):
    """True where the M1 bar `i` (decision bar) lies in the London-clock window [sess_start, sess_end)."""
    if int(p["sess_start"]) < 0:
        return np.ones(len(i), bool)
    ldn = _wall(c, "LDN")
    m = ldn[np.clip(i, 0, c["N"] - 1)] % 1440
    return (m >= int(p["sess_start"])) & (m < int(p["sess_end"]))


def _channel_state(h, l, n):
    """+1 / -1: which extreme of the n-bar channel (bar just closed included) was made most recently
    (the bar of the n-bar high is more recent than the bar of the n-bar low -> +1).  0 if unknown."""
    hs, ls = pd.Series(h), pd.Series(l)
    up, dn = hs.rolling(n).max().to_numpy(), ls.rolling(n).min().to_numpy()
    k = np.arange(len(h))
    last_hi = pd.Series(np.where(h >= up, k, np.nan)).ffill().to_numpy()   # last bar that set the n-bar high
    last_lo = pd.Series(np.where(l <= dn, k, np.nan)).ffill().to_numpy()
    st = np.where(last_hi > last_lo, 1, np.where(last_lo > last_hi, -1, 0))
    st[~(np.isfinite(last_hi) & np.isfinite(last_lo))] = 0
    return st


def _donch(c, p):
    b = bars(c, p["tf"])
    n = int(p["n"])
    a = atr(b, p["atr_n"])
    h, l = b["h"], b["l"]
    up = pd.Series(h).rolling(n).max().to_numpy()
    dn = pd.Series(l).rolling(n).min().to_numpy()
    N = c["N"]
    i0 = b["en"]
    i1 = np.r_[b["en"][1:], N] - 1
    keep = np.isfinite(up) & np.isfinite(dn) & np.isfinite(a) & (i0 < N) & (i1 >= i0)
    keep &= _sess_mask(c, i0, p)
    if float(p["squeeze"]) > 0:
        # volatility contraction: channel width <= squeeze x its own median over the previous squeeze_ref bars
        wd = pd.Series(up - dn)
        ref = wd.rolling(int(p["squeeze_ref"]), min_periods=int(p["squeeze_ref"]) // 2).median().shift(1).to_numpy()
        keep &= np.isfinite(ref) & ((up - dn) <= float(p["squeeze"]) * ref)
    # which side(s) of the bracket are placed after this bar close
    allow_l = np.full(len(up), p["sides"] in ("both", "long"))
    allow_s = np.full(len(up), p["sides"] in ("both", "short"))
    if int(p["trend_n"]) > 0:
        st = _channel_state(h, l, int(p["trend_n"]))
        allow_l &= st > 0
        allow_s &= st < 0
    keep &= allow_l | allow_s
    delay = int(p.get("delay_min", 0))
    if delay:
        i0 = i0 + delay
        keep &= i0 <= i1
    a0 = np.where(keep, i0, -1).astype(np.int64)
    hit_i, hit_s = _first_touch(c["ah"], c["bl"], c["bo"], c["bc"], a0, i1.astype(np.int64),
                                np.where(allow_l & np.isfinite(up), up, np.inf),
                                np.where(allow_s & np.isfinite(dn), dn, -np.inf))
    xi = _exit_idx(c, _add_trading_days(b["t_close"], int(p["max_days"])) - 5)
    keep &= (hit_i >= 0) & (xi > hit_i)
    side = hit_s[keep]
    o = pd.DataFrame({
        "entry_i": i0[keep], "side": side, "etype": 1,
        "level": np.where(side > 0, up[keep], dn[keep]), "expiry_i": i1[keep],
        "stop_dist": a[keep] * float(p["stop_atr"]), "exit_i": xi[keep],
        "trail": a[keep] * float(p["trail_atr"]) if np.isfinite(p["trail_atr"]) else np.nan,
        "trig_i": hit_i[keep], "atr": a[keep],
    })
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


def _pullback(c, p):
    b = bars(c, p["tf"])
    a = atr(b, p["atr_n"])
    h, l = b["h"], b["l"]
    st = _channel_state(h, l, int(p["trend_n"]))
    m = int(p["pb_n"])
    lo_m = pd.Series(l).rolling(m).min().to_numpy()
    hi_m = pd.Series(h).rolling(m).max().to_numpy()
    # uptrend + the bar just closed made the pb_n-bar low  -> buy-stop at that bar's high
    long_sig = (st > 0) & (l <= lo_m)
    short_sig = (st < 0) & (h >= hi_m)
    side = np.where(long_sig, 1, np.where(short_sig, -1, 0))
    N = c["N"]
    i0 = b["en"]
    i1 = np.r_[b["en"][1:], N] - 1
    level = np.where(side > 0, h, l)
    stop = np.where(side > 0, l - float(p["stop_buf"]) * a, h + float(p["stop_buf"]) * a)
    keep = (side != 0) & np.isfinite(a) & np.isfinite(lo_m) & np.isfinite(hi_m) & (i0 < N) & (i1 >= i0)
    keep &= _side_ok(side, p["sides"])
    a0 = np.where(keep, i0, -1).astype(np.int64)
    up = np.where(side > 0, level, np.inf)
    dn = np.where(side < 0, level, -np.inf)
    hit_i, hit_s = _first_touch(c["ah"], c["bl"], c["bo"], c["bc"], a0, i1.astype(np.int64), up, dn)
    xi = _exit_idx(c, _add_trading_days(b["t_close"], int(p["max_days"])) - 5)
    keep &= (hit_i >= 0) & (xi > hit_i)
    o = pd.DataFrame({
        "entry_i": i0[keep], "side": side[keep], "etype": 1, "level": level[keep], "expiry_i": i1[keep],
        "stop": stop[keep], "exit_i": xi[keep],
        "trail": a[keep] * float(p["trail_atr"]) if np.isfinite(p["trail_atr"]) else np.nan,
        "trig_i": hit_i[keep], "atr": a[keep],
    })
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


_FAMILIES = {"orb": _orb, "rn": _rn, "donch": _donch, "pullback": _pullback}


def resolve(params):
    """Complete parameter set of a configuration (family defaults filled in)."""
    fam = params.get("family")
    if fam not in DEFAULTS:
        raise ValueError(f"unknown family {fam!r}")
    opt = OPTIONAL.get(fam, {})
    unknown = set(params) - set(DEFAULTS[fam]) - set(opt) - {"family"}
    if unknown:
        raise ValueError(f"unknown params {unknown} for family {fam}")
    out = {"family": fam, **DEFAULTS[fam], **{k: v for k, v in params.items() if k != "family" and k not in opt}}
    out.update({k: params[k] for k in opt if k in params and params[k] != opt[k]})
    return out


def make_orders(m1, **params):
    p = resolve(params)
    if int(p.get("max_days", 0)) > 5 or int(p.get("hold_days", 0)) > 4:
        raise ValueError("forced exit must come within 5 trading days")
    c = context(m1)
    o = _FAMILIES[p["family"]](c, p)
    return o if len(o) else _empty()


# ----------------------------------------------------------------------------------------------
# Finalist, chosen on in-sample data only (entries before 2022-01-01), BEFORE any validation access
# (results/r2/gold2/finalists_preval.json).  One rule, one parameter set, one sleeve (gold).
#
# sq24_breakout_1h -- volatility-contraction breakout on XAUUSD, 1h bars (UTC hours; mid prices):
#   after every 1h bar close, if flat:
#     H = highest mid-high, L = lowest mid-low of the last 24 bars (bar just closed included); W = H - L
#     Wref = median of W over the PREVIOUS 480 bars (20 trading days)
#     if W <= 0.7 x Wref: OCO pair for the next bar only -- buy-stop at H (triggers on ask), sell-stop
#     at L (triggers on bid); the first one touched is the trade, the other is cancelled
#   stop-loss 2 x ATR14(1h, Wilder) from the fill, frozen at the decision; trailing stop at the same
#   distance from the best bid-high (long) / ask-low (short), updated at each M1 close;
#   time stop 5 New-York trading days after the decision (minus 5 minutes).  One position at a time.
# Silver (same parameters) has a gross edge of the same size but loses after FP costs: not a sleeve.
#
# OUTCOME: passed every in-sample criterion (PF 1.25, t 2.63, null 100th pct, neighbours median PF 1.27) and
# FAILED the single-shot validation 2022-2025 (PF 0.80, -0.084 R/trade, 1/4 years; every signal -0.080 R).
# DO NOT TRADE.  Kept here only so that the logged result can be reproduced.
FINALISTS = {
    "sq24_breakout_1h": {
        "syms": ["xauusd"],
        "params": {"family": "donch", "tf": 60, "n": 24, "atr_n": 14, "stop_atr": 2.0, "trail_atr": 2.0,
                   "max_days": 5, "sides": "both", "sess_start": -1, "sess_end": -1, "trend_n": 0,
                   "squeeze": 0.7, "squeeze_ref": 480},
    },
}
