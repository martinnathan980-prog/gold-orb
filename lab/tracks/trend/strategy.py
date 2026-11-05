"""Track `trend`: short-horizon trend-following / momentum / volatility breakouts on XAUUSD.

`make_orders(m1, **params)` builds a causal orders frame for goldlab.simulate on ANY M1 frame
(bid/ask columns bo bh bl bc ao ah al ac, UTC index).  Three families:

  family="donchian"  n-bar channel breakout on tf (1h / 4h / D), both sides.
                     entry="close": close beyond the PRIOR n-bar high/low -> market entry at
                       the next M1 bar.
                     entry="stop" (finalist): after each bar close, OCO buy-stop / sell-stop at
                       the n-bar high / low (incl. the bar just closed), valid until the next
                       bar close; the side touched first on M1 is the trade.
                     grid="utc" (default, 00/04/08/.. UTC H4 bars) or "ny17" (MT5 server grid).
  family="vbo"       Larry-Williams volatility breakout: OCO stop orders at
                     anchor_open +/- k * range, range = previous trading day's high-low
                     (or ATR(D)).  Whichever level is touched FIRST is the trade (resolved
                     here on M1, see `_first_touch`).  Exit at end of day (16:55 NY) of the
                     last holding day, or stop / target / trail.
  family="tsmom"     sign of the L-day return (or close vs SMA(L)) at the daily close
                     (17:00 NY), optional realized-vol regime filter, hold <= max_days.

Common exit parameters: stop (ATR or range multiple), trail (same unit), target_r (R
multiple of the initial stop), max_days (time stop in NY trading days, <= 5).

Causality: every indicator is computed on bars that are complete at the decision time
(`t_close`); rolling windows only look back; thresholds come from trailing windows.  Tested:
orders built on data truncated at arbitrary minutes are identical to those built on the
longer frame (see report.md).

Warm-up: ATR is a Wilder EWM from the first bar of the frame and the channel needs n bars, so
give make_orders an M1 frame that starts >= 2 months before the first trade you care about
(e.g. for the 2026 holdout: load from 2025-10-01 and keep trades with entry >= 2026-01-01).
"""
import math

import numba as nb
import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

import goldlab as gl

NY, LDN = gl.NY, gl.LDN

DEFAULTS = {
    "family": "donchian",
    # donchian
    "tf": "4h", "n": 20, "entry": "close", "grid": "utc",
    # vbo
    "anchor": "ldn8", "k": 0.5, "rng": "prev", "stop_k": 0.5, "trail_k": float("nan"),
    "win_end_ny": 12.0, "hold_days": 1, "nr": 0,
    # tsmom
    "lookback": 20, "signal": "ret", "vol": "none", "vol_n": 20, "vol_ref": 250,
    # common
    "atr_n": 14, "stop_atr": 2.0, "trail_atr": 2.0, "target_r": float("nan"),
    "max_days": 5, "sides": "both", "sess": "none", "trend_ma": 0,
}

_bar_cache = {}


def _key(m1):
    return (id(m1), len(m1), m1.index[0].value, m1.index[-1].value)


def bars_cached(m1, rule):
    k = _key(m1) + (rule,)
    if k not in _bar_cache:
        if len(_bar_cache) > 12:
            _bar_cache.clear()
        _bar_cache[k] = gl.bars(m1, rule)
    return _bar_cache[k]


_AGG = {"bo": "first", "bh": "max", "bl": "min", "bc": "last",
        "ao": "first", "ah": "max", "al": "min", "ac": "last"}


def bars_ny17(m1, rule):
    """Intraday bars on an MT5-style server grid: boundaries at 17:00 New York + k * rule
    (brokers whose server midnight is the NY close, UTC+2/+3).  Same columns as gl.bars."""
    k = _key(m1) + ("ny17", rule)
    if k not in _bar_cache:
        srv = (gl.local(m1.index, NY).tz_localize(None) + pd.Timedelta(hours=7))  # naive server time
        x = m1.set_axis(srv)
        b = x.resample(rule, label="left", closed="left").agg(_AGG).dropna()
        last_utc = pd.Series(m1.index, index=srv).resample(rule, label="left", closed="left").last()
        b["t_close"] = last_utc.reindex(b.index) + pd.Timedelta(minutes=1)
        for c in "ohlc":
            b[c] = (b["b" + c] + b["a" + c]) / 2
        b = b.set_axis(pd.DatetimeIndex(b["t_close"])).sort_index()   # index = close time (UTC)
        _bar_cache[k] = b
    return _bar_cache[k]


def daily_bars(m1, min_minutes=600):
    """NY-17:00 trading-day bars, keeping only 'full' days (>= min_minutes of M1 data):
    drops the 2013-01-01 stub and holiday-shortened sessions whose tiny ranges would
    otherwise produce absurd stops."""
    k = _key(m1) + ("Dfull", min_minutes)
    if k not in _bar_cache:
        d = bars_cached(m1, "D")
        cnt = m1.groupby(gl.trading_day(m1.index)).size()
        _bar_cache[k] = d[cnt.reindex(d.index).fillna(0).to_numpy() >= min_minutes]
    return _bar_cache[k]


def add_trading_days(ts, n):
    """Shift UTC timestamps by n NY-17:00 trading days, keeping the New York wall clock."""
    ny = pd.DatetimeIndex(ts).tz_convert(NY).tz_localize(None)
    sh = (ny + pd.Timedelta(hours=7)) + BDay(int(n)) - pd.Timedelta(hours=7)
    return pd.DatetimeIndex(sh).tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def exit_index(m1, xt, max_gap_min=30):
    """M1 index at whose OPEN a time stop scheduled at `xt` executes.  If `xt` falls inside a
    market closure (weekend, holiday, early close: next bar > max_gap_min later) the exit is
    done on the last bar BEFORE the closure instead of after it (keeps hold <= the limit)."""
    idx = m1.index.values
    xv = pd.DatetimeIndex(xt).values
    xi = np.searchsorted(idx, xv, side="left").astype(np.int64)
    nxt = idx[np.clip(xi, 0, len(idx) - 1)]
    gap = (xi >= len(idx)) | ((nxt - xv) > np.timedelta64(max_gap_min, "m"))
    xi = np.where(gap & (xi > 0), xi - 1, xi)
    return np.where(pd.isna(xt), -1, xi).astype(np.int64)


FAMILY_KEYS = {
    "donchian": ["tf", "n", "atr_n", "stop_atr", "trail_atr", "target_r", "max_days", "sides",
                 "sess", "trend_ma"],
    "vbo": ["anchor", "k", "rng", "atr_n", "stop_k", "trail_k", "target_r", "win_end_ny",
            "hold_days", "nr", "sides"],
    "tsmom": ["tf", "lookback", "signal", "vol", "vol_n", "vol_ref", "atr_n", "stop_atr",
              "trail_atr", "target_r", "max_days", "sides"],
}


def resolve(params):
    """Full, family-specific parameter set (what gets logged / stored for finalists).
    donchian `entry` is only listed when it is not the default 'close' (keeps the keys of the
    configs logged before that option existed)."""
    p = _p(params)
    out = {"family": p["family"], **{k: p[k] for k in FAMILY_KEYS[p["family"]]}}
    if p["family"] == "donchian" and p["entry"] != "close":
        out["entry"] = p["entry"]
    if p["family"] == "donchian" and p["grid"] != "utc":
        out["grid"] = p["grid"]
    return out


def ny_clock(dates, hour):
    """UTC timestamps of NY wall-clock `hour` (float) on the given naive dates."""
    d = pd.DatetimeIndex(dates).tz_localize(None).normalize()
    t = d + pd.to_timedelta(int(round(hour * 60)), unit="min")
    return t.tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def ldn_clock(dates, hour):
    """UTC timestamps of London wall-clock `hour` (float) on the given naive dates."""
    d = pd.DatetimeIndex(dates).tz_localize(None).normalize()
    t = d + pd.to_timedelta(int(round(hour * 60)), unit="min")
    return t.tz_localize(LDN, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC")


def _p(params):
    p = dict(DEFAULTS)
    unknown = set(params) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown params {unknown}")
    p.update(params)
    return p


def _nan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def _session_mask(t_close, sess):
    """Keep decisions whose time (London wall clock) is inside the session."""
    if sess == "none":
        return np.ones(len(t_close), bool)
    h = gl.local(pd.DatetimeIndex(t_close), LDN)
    hh = h.hour + h.minute / 60.0
    if sess == "ldn_ny":          # 07:00 - 17:00 London (London + NY overlap)
        return (hh >= 7) & (hh <= 17)
    if sess == "ny":              # 12:00 - 17:00 London ~ 07:00 - 12:00 NY
        return (hh >= 12) & (hh <= 17)
    raise ValueError(sess)


def _finish(m1, dec_time, side, stop_dist, trail, target_r, max_days, extra=None):
    """Assemble a market-entry orders frame from decisions known at `dec_time` (UTC)."""
    dec_time = pd.DatetimeIndex(dec_time)
    ei = gl.entry_index(m1, dec_time)
    xt = add_trading_days(dec_time, max_days) - pd.Timedelta(minutes=5)
    xi = exit_index(m1, xt)
    o = pd.DataFrame({
        "entry_i": ei, "side": np.asarray(side, np.int64), "etype": 0,
        "stop_dist": np.asarray(stop_dist, float),
        "exit_i": xi,
        "trail": np.asarray(trail, float) if trail is not None else np.nan,
    })
    if not _nan(target_r):
        o["target_dist"] = o["stop_dist"] * float(target_r)
    o["dec_time"] = dec_time
    if extra is not None:
        for k, v in extra.items():
            o[k] = np.asarray(v)
    ok = (o.entry_i < len(m1)) & np.isfinite(o.stop_dist) & (o.stop_dist > 0) & (o.exit_i > o.entry_i)
    return o[ok].sort_values("entry_i", kind="stable").reset_index(drop=True)


def _sides_filter(side, sides):
    if sides == "long":
        return side > 0
    if sides == "short":
        return side < 0
    return side != 0


def _trend_filter(m1, b, side, trend_ma):
    """Optional: only trade in the direction of close vs SMA(trend_ma) of DAILY closes known
    at the decision time."""
    if not trend_ma:
        return np.ones(len(side), bool)
    d = daily_bars(m1)
    sma = d["c"].rolling(int(trend_ma)).mean()
    ref = pd.Series((d["c"] - sma).to_numpy(), index=pd.DatetimeIndex(d["t_close"]))
    ref = ref[~ref.index.duplicated()].sort_index()
    pos = np.searchsorted(ref.index.values, pd.DatetimeIndex(b["t_close"]).values, side="right") - 1
    val = np.where(pos >= 0, ref.to_numpy()[np.clip(pos, 0, None)], np.nan)
    return np.sign(val) == side


# --------------------------------------------------------------------------- donchian
def _donchian(m1, p):
    if p["tf"] == "D":
        b = daily_bars(m1)
    elif p["grid"] == "ny17":
        b = bars_ny17(m1, p["tf"])
    else:
        b = bars_cached(m1, p["tf"])
    n = int(p["n"])
    a = gl.atr(b, int(p["atr_n"]))
    if p["entry"] == "stop":
        return _donchian_stop(m1, p, b, a, n)
    hi = b["h"].rolling(n).max().shift(1)
    lo = b["l"].rolling(n).min().shift(1)
    side = np.where(b["c"] > hi, 1, np.where(b["c"] < lo, -1, 0))
    keep = _sides_filter(side, p["sides"]) & _session_mask(b["t_close"], p["sess"])
    keep &= _trend_filter(m1, b, side, p["trend_ma"]) & np.isfinite(a.to_numpy())
    b, a, side = b[keep], a[keep], side[keep]
    trail = None if _nan(p["trail_atr"]) else a.to_numpy() * float(p["trail_atr"])
    return _finish(m1, b["t_close"], side, a.to_numpy() * float(p["stop_atr"]), trail,
                   p["target_r"], p["max_days"], extra={"atr": a.to_numpy()})


def _donchian_stop(m1, p, b, a, n):
    """Turtle-style variant: after each bar close, OCO stop orders at the n-bar high / low
    (channel INCLUDING the just-closed bar), valid until the next bar closes.  The side that
    is touched first on M1 is the trade (`_first_touch`)."""
    up = b["h"].rolling(n).max().to_numpy()
    dn = b["l"].rolling(n).min().to_numpy()
    tc = pd.DatetimeIndex(b["t_close"])
    i0 = gl.entry_index(m1, tc)
    i1 = np.r_[gl.entry_index(m1, tc[1:]), len(m1)] - 1
    keep = (np.isfinite(up) & np.isfinite(dn) & np.isfinite(a.to_numpy()) & (i0 < len(m1))
            & (i1 >= i0) & _session_mask(tc, p["sess"]))
    i0c = np.clip(i0, 0, len(m1) - 1).astype(np.int64)
    hit_i, hit_s = _first_touch(m1["ah"].to_numpy(), m1["bl"].to_numpy(), m1["bo"].to_numpy(),
                                m1["bc"].to_numpy(), i0c, i1.astype(np.int64),
                                np.nan_to_num(up, nan=np.inf), np.nan_to_num(dn, nan=-np.inf))
    keep &= hit_i >= 0
    keep &= _sides_filter(hit_s, p["sides"]) & _trend_filter(m1, b, hit_s, p["trend_ma"])
    av = a.to_numpy()
    xt = add_trading_days(tc, int(p["max_days"])) - pd.Timedelta(minutes=5)
    xi = exit_index(m1, xt)
    keep &= xi > hit_i
    side = hit_s[keep]
    o = pd.DataFrame({
        "entry_i": i0c[keep], "side": side, "etype": 1,
        "level": np.where(side > 0, up[keep], dn[keep]), "expiry_i": i1[keep],
        "stop_dist": av[keep] * float(p["stop_atr"]), "exit_i": xi[keep],
        "trail": np.nan if _nan(p["trail_atr"]) else av[keep] * float(p["trail_atr"]),
        "atr": av[keep], "trig_i": hit_i[keep], "dec_time": tc[keep],
    })
    if not _nan(p["target_r"]):
        o["target_dist"] = o["stop_dist"] * float(p["target_r"])
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


# --------------------------------------------------------------------------- vbo
@nb.njit(cache=True)
def _first_touch(ah, bl, bo, bc, i0, i1, up, dn):
    """First M1 bar in [i0, i1] where ask-high >= up (buy stop) or bid-low <= dn (sell stop).
    Returns (bar index, side).  Both inside the same bar -> assume the adverse order: the side
    AGAINST that bar's net move (it filled first and the bar then reversed through it)."""
    n = len(i0)
    N = len(ah)
    out_i = np.full(n, -1, np.int64)
    out_s = np.zeros(n, np.int64)
    for k in range(n):
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


def _vbo(m1, p):
    d = daily_bars(m1)
    days = pd.DatetimeIndex(d.index)
    rng_prev = (d["h"] - d["l"]).shift(1)
    if p["rng"] == "atr":
        rng_prev = gl.atr(d, int(p["atr_n"])).shift(1)
    # narrow-range filter (Crabel NR-n): previous day's range is the smallest of the last nr days
    nr_ok = np.ones(len(d), bool)
    if int(p["nr"]) > 1:
        r = d["h"] - d["l"]
        nr_ok = (r.shift(1) <= r.shift(1).rolling(int(p["nr"])).min()).to_numpy()
    if p["anchor"] == "day":       # trading-day open: first M1 bar after 17:00 NY of the previous business day
        t0 = ny_clock(days - BDay(1), 17.0)
    elif p["anchor"] == "ldn8":
        t0 = ldn_clock(days, 8.0)
    elif p["anchor"] == "ny8":
        t0 = ny_clock(days, 8.0)
    else:
        raise ValueError(p["anchor"])
    t_end = ny_clock(days, float(p["win_end_ny"]))
    t_exit = add_trading_days(ny_clock(days, 16 + 55 / 60), int(p["hold_days"]) - 1)
    ok = (np.isfinite(rng_prev.to_numpy()) & (rng_prev.to_numpy() > 0) & nr_ok
          & ~pd.isna(t0) & ~pd.isna(t_end) & ~pd.isna(t_exit))
    t0, t_end, t_exit = pd.DatetimeIndex(t0)[ok], pd.DatetimeIndex(t_end)[ok], pd.DatetimeIndex(t_exit)[ok]
    rng = rng_prev.to_numpy()[ok]
    i0 = gl.entry_index(m1, t0)
    i1 = gl.entry_index(m1, t_end) - 1
    xi = exit_index(m1, t_exit)
    valid = (i0 < len(m1)) & (i1 >= i0)
    i0c = np.clip(i0, 0, len(m1) - 1)
    o_px = ((m1["bo"].to_numpy() + m1["ao"].to_numpy()) / 2)[i0c]
    k = float(p["k"])
    up, dn = o_px + k * rng, o_px - k * rng
    ah, bl = m1["ah"].to_numpy(), m1["bl"].to_numpy()
    bo, bc = m1["bo"].to_numpy(), m1["bc"].to_numpy()
    hit_i, hit_s = _first_touch(ah, bl, bo, bc, i0c.astype(np.int64), i1.astype(np.int64), up, dn)
    sel = valid & (hit_i >= 0) & (xi > hit_i)
    sel &= _sides_filter(hit_s, p["sides"])
    side = hit_s[sel]
    level = np.where(side > 0, up[sel], dn[sel])
    trail = np.nan if _nan(p["trail_k"]) else rng[sel] * float(p["trail_k"])
    o = pd.DataFrame({
        "entry_i": i0c[sel], "side": side, "etype": 1, "level": level,
        "expiry_i": i1[sel], "stop_dist": rng[sel] * float(p["stop_k"]),
        "exit_i": xi[sel], "trail": trail, "rng": rng[sel], "trig_i": hit_i[sel],
        "dec_time": t0[sel],
    })
    if not _nan(p["target_r"]):
        o["target_dist"] = o["stop_dist"] * float(p["target_r"])
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


# --------------------------------------------------------------------------- tsmom
def _tsmom(m1, p):
    tf = p["tf"] if p["tf"] in ("4h", "D") else "D"
    b = daily_bars(m1) if tf == "D" else bars_cached(m1, tf)
    L = int(p["lookback"])
    c = b["c"]
    if p["signal"] == "ret":
        sig = np.sign(c - c.shift(L))
    elif p["signal"] == "sma":
        sig = np.sign(c - c.rolling(L).mean())
    else:
        raise ValueError(p["signal"])
    a = gl.atr(b, int(p["atr_n"]))
    keep = np.isfinite(sig.to_numpy()) & np.isfinite(a.to_numpy())
    if p["vol"] != "none":
        lr = np.log(c).diff()
        rv = lr.rolling(int(p["vol_n"])).std()
        ref = rv.rolling(int(p["vol_ref"]), min_periods=int(p["vol_ref"]) // 2).median()
        hi = (rv > ref).to_numpy()
        keep &= np.isfinite(ref.to_numpy()) & (hi if p["vol"] == "hi" else ~hi)
    side = np.nan_to_num(sig.to_numpy()).astype(int)
    keep &= _sides_filter(side, p["sides"])
    b, a, side = b[keep], a[keep], side[keep]
    trail = None if _nan(p["trail_atr"]) else a.to_numpy() * float(p["trail_atr"])
    return _finish(m1, b["t_close"], side, a.to_numpy() * float(p["stop_atr"]), trail,
                   p["target_r"], p["max_days"], extra={"atr": a.to_numpy()})


def make_orders(m1, **params):
    p = _p(params)
    if int(p["max_days"]) > 5 or int(p.get("hold_days", 1)) > 5:
        raise ValueError("max hold must be <= 5 trading days")
    fam = p["family"]
    if fam == "donchian":
        return _donchian(m1, p)
    if fam == "vbo":
        return _vbo(m1, p)
    if fam == "tsmom":
        return _tsmom(m1, p)
    raise ValueError(fam)


# Finalist chosen on IS only (2013-2021), BEFORE any validation access (see
# lab/results/trend/report.md and finalists_preval.json).  Regenerate on any M1 frame with
#   make_orders(m1, **FINALISTS["donch4h_stop"])  then  gl.simulate(m1, orders)  (no_overlap=True).
FINALISTS = {
    # Turtle-style 10-trading-day (60 x H4) channel breakout, both sides.  After each H4 bar
    # close (UTC 4h grid: 00/04/08/12/16/20 UTC), if flat: buy-stop at the highest MID high and
    # sell-stop at the lowest MID low of the last 60 H4 bars (incl. the bar just closed), OCO,
    # valid until the next H4 close (buy-stop triggers on ask, sell-stop on bid).
    # Initial stop 2 x ATR14(H4) from the fill (Wilder ATR on mid H4 bars, frozen at the
    # decision), trailing stop at 2 x that ATR from the best M1 bid-high (long) / ask-low
    # (short), updated at each M1 close; forced exit 5 NY trading days after the decision bar
    # close, at the same NY wall-clock time minus 5 min (last bar before a closure if needed).
    "donch4h_stop": {"family": "donchian", "tf": "4h", "n": 60, "entry": "stop",
                     "stop_atr": 2.0, "trail_atr": 2.0, "max_days": 5, "atr_n": 14,
                     "target_r": float("nan"), "sides": "both", "sess": "none", "trend_ma": 0},
}
