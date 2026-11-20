"""Signals of the grammar (GRAMMAR.md 'Signals'): for one market, the table (known_at, side) of every signal id on
every frame, computed once per signal-frame from the frame's bars and reused across filters and exits.

A signal is +1 (buy) / -1 (sell) at the close of a frame bar, known at that bar's known_at (frames.py). A STATE
condition fires on the bar where it becomes true (true on this bar, false on the previous bar, whose inputs must be
valid); an EVENT (a crossing, a flip, a pattern defined with its own previous bar) fires where it happens. A bar where
both a buy and a sell fire gives no signal."""
import numpy as np
import pandas as pd

from . import frames as FR
from . import grammar as G
from . import indicators as I

ROUND_GRID = {"eurusd": 0.01, "gbpusd": 0.01, "audusd": 0.01, "nzdusd": 0.01, "usdcad": 0.01, "usdchf": 0.01,
              "usdjpy": 1.0, "eurjpy": 1.0, "xauusd": 10.0, "xagusd": 0.5, "us100": 100.0, "ger40": 100.0,
              "us500": 50.0, "us30": 500.0}


def _prev(x, fill=np.nan):
    x = np.asarray(x)
    out = np.empty_like(x, dtype=float if x.dtype.kind == "f" else x.dtype)
    if len(x):
        out[0] = fill
        out[1:] = x[:-1]
    return out


def _prevb(b):
    b = np.asarray(b, bool)
    return np.r_[False, b[:-1]] if len(b) else b


def onset(cond, valid):
    """True where cond holds and the previous bar was valid and did not hold it."""
    cond = np.asarray(cond, bool) & np.asarray(valid, bool)
    return cond & _prevb(valid) & ~_prevb(cond)


def cross_up(a, b):
    a, b = np.asarray(a, float), np.broadcast_to(np.asarray(b, float), np.shape(a))
    pa, pb = _prev(a), _prev(b)
    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(pa) & np.isfinite(pb)
    return ok & (a > b) & (pa <= pb)


def cross_dn(a, b):
    a, b = np.asarray(a, float), np.broadcast_to(np.asarray(b, float), np.shape(a))
    pa, pb = _prev(a), _prev(b)
    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(pa) & np.isfinite(pb)
    return ok & (a < b) & (pa >= pb)


def _shift(x, k):
    """x[t - k] (NaN for t < k)."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if k < len(x):
        out[k:] = x[:len(x) - k]
    return out


def _fin(*xs):
    ok = np.ones(len(xs[0]), bool)
    for x in xs:
        ok &= np.isfinite(np.asarray(x, float))
    return ok


class Ind:
    """Cached indicators of one frame's bars."""

    def __init__(self, fr):
        self.o, self.h, self.l, self.c = (fr[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.n = len(self.c)
        self._c = {}

    def get(self, key, fn):
        if key not in self._c:
            self._c[key] = fn()
        return self._c[key]

    def ema(self, n):
        return self.get(("ema", n), lambda: I.ema(self.c, n))

    def atr(self, n):
        return self.get(("atr", n), lambda: I.atr(self.h, self.l, self.c, n))

    def adx(self):
        return self.get(("adx",), lambda: I.adx(self.h, self.l, self.c, 14))

    def boll(self):
        return self.get(("boll",), lambda: I.bollinger(self.c, 20, 2.0))

    def rsi(self, n):
        return self.get(("rsi", n), lambda: I.rsi(self.c, n))

    def ret(self):
        return self.get(("ret",), lambda: I.log_returns(self.c))

    def sd500(self):
        """sd (ddof 1) of the 500 log returns before each bar: r[t-500..t-1]."""
        return self.get(("sd500p",), lambda: _shift(I.rolling_std(self.ret(), 500, ddof=1), 1))

    def shock_z(self):
        return self.get(("z",), lambda: self.ret() / self.sd500())

    def ibs(self):
        return self.get(("ibs",), lambda: I.ibs(self.h, self.l, self.c))

    def er(self):
        return self.get(("er",), lambda: I.efficiency_ratio(self.c, 24))


# ------------------------------------------------------------------ one function per signal: (buy, sell) bool arrays
def _ema_cross(x, f, s):
    a, b = x.ema(f), x.ema(s)
    return cross_up(a, b), cross_dn(a, b)


def _macd_sig(x):
    line = x.get(("macd",), lambda: I.macd(x.c, 12, 26, 9))
    return cross_up(line[0], line[1]), cross_dn(line[0], line[1])


def _macd_zero(x):
    line = x.get(("macd",), lambda: I.macd(x.c, 12, 26, 9))[0]
    return cross_up(line, 0.0), cross_dn(line, 0.0)


def _breakout(x, n):
    hh = _shift(I.rolling_max(x.h, n), 1)
    ll = _shift(I.rolling_min(x.l, n), 1)
    v = _fin(hh, ll)
    return onset(x.c > hh, v), onset(x.c < ll, v)


def _flip(d):
    d = np.asarray(d, float)
    pd_ = _prev(d, 0.0)
    return (d > 0) & (pd_ < 0), (d < 0) & (pd_ > 0)


def _supertrend(x):
    return _flip(I.supertrend(x.h, x.l, x.c, 10, 3.0)[1])


def _ichimoku(x):
    _, _, sa, sb = I.ichimoku(x.h, x.l, 9, 26, 52)
    v = _fin(sa, sb)
    top, bot = np.fmax(sa, sb), np.fmin(sa, sb)
    return onset(x.c > top, v), onset(x.c < bot, v)


def _keltner(x):
    _, up, lo = x.get(("kelt",), lambda: I.keltner(x.h, x.l, x.c, 20, 2.0))
    v = _fin(up, lo)
    return onset(x.c > up, v), onset(x.c < lo, v)


def _boll_out(x):
    _, up, lo = x.boll()
    v = _fin(up, lo)
    return onset(x.c > up, v), onset(x.c < lo, v)


def _di_cross(x):
    pdi, mdi, a = x.adx()
    strong = np.isfinite(a) & (a >= 25)
    return cross_up(pdi, mdi) & strong, cross_dn(pdi, mdi) & strong


def _psar(x):
    return _flip(I.psar(x.h, x.l, 0.02, 0.2)[1])


def _rsi(x, n, lo, hi):
    r = x.rsi(n)
    v = np.isfinite(r)
    return onset(r < lo, v), onset(r > hi, v)


def _stoch(x):
    k, d = x.get(("stoch",), lambda: I.stochastic(x.h, x.l, x.c, 14, 3, 3))
    return cross_up(k, d) & (d < 20), cross_dn(k, d) & (d > 80)


def _cci(x):
    v = I.cci(x.h, x.l, x.c, 20)
    p = _prev(v)
    ok = _fin(v, p)
    return ok & (v > -100) & (p <= -100), ok & (v < 100) & (p >= 100)


def _three(x):
    c = x.c
    c1, c2, c3 = _shift(c, 1), _shift(c, 2), _shift(c, 3)
    v = _fin(c, c1, c2, c3)
    return onset(v & (c < c1) & (c1 < c2) & (c2 < c3), v), onset(v & (c > c1) & (c1 > c2) & (c2 > c3), v)


def _ibs1(x):
    b = x.ibs()
    v = np.isfinite(b)
    return onset(b < 0.2, v), onset(b > 0.8, v)


def _shock(x, k):
    z = x.shock_z()
    v = np.isfinite(z)
    return onset(z > k, v), onset(z < -k, v)


def _range_shock(x):
    a = _shift(x.atr(20), 1)
    rng = x.h - x.l
    v = np.isfinite(a)
    big = v & (rng > 2.5 * a)
    return onset(big & (x.c > x.o), v), onset(big & (x.c < x.o), v)


def _shock_retrace(x):
    """K07: every bar s with |z| > 3 (K01's score) is a shock; level L = c_s - 0.382 (c_s - c_{s-1}); the first bar
    j in s+1..s+6 whose low reaches L (up shock) and whose close is above L gives a buy (down shock mirrored)."""
    z = x.shock_z()
    n = x.n
    buy, sell = np.zeros(n, bool), np.zeros(n, bool)
    c, h, l = x.c, x.h, x.l
    for s in np.flatnonzero(np.isfinite(z) & (np.abs(z) > 3)):
        if s < 1:
            continue
        lev = c[s] - 0.382 * (c[s] - c[s - 1])
        up = z[s] > 0
        for j in range(s + 1, min(s + 7, n)):
            if up and l[j] <= lev and c[j] > lev:
                buy[j] = True
                break
            if (not up) and h[j] >= lev and c[j] < lev:
                sell[j] = True
                break
    return buy, sell


def _squeeze(x):
    _, up, lo = x.boll()
    mid = x.boll()[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        w = (up - lo) / mid
    mn = I.rolling_min(w, 120)
    low = np.isfinite(mn) & np.isfinite(w) & (w <= mn)
    recent = np.zeros(x.n, bool)
    for k in range(1, 7):
        recent |= np.r_[np.zeros(min(k, x.n), bool), low[:max(x.n - k, 0)]]
    finmn = np.isfinite(mn)
    known = np.ones(x.n, bool)                     # the 6 previous bars all have a defined 120-bar minimum
    for k in range(1, 7):
        known &= np.r_[np.zeros(min(k, x.n), bool), finmn[:max(x.n - k, 0)]]
    v = known & _fin(up, lo)
    return onset(recent & (x.c > up), v), onset(recent & (x.c < lo), v)


def _nr7(x):
    rng = x.h - x.l
    nr = np.isfinite(I.rolling_min(rng, 7)) & (rng <= I.rolling_min(rng, 7))
    nrp = _prevb(nr)
    hp, lp = _shift(x.h, 1), _shift(x.l, 1)
    v = np.r_[np.zeros(min(7, x.n), bool), np.ones(max(x.n - 7, 0), bool)]
    return onset(nrp & (x.c > hp), v), onset(nrp & (x.c < lp), v)


def _inside(x):
    h1, l1, h2, l2 = _shift(x.h, 1), _shift(x.l, 1), _shift(x.h, 2), _shift(x.l, 2)
    v = _fin(h1, l1, h2, l2)
    ins = v & (h1 <= h2) & (l1 >= l2) & ((h1 - l1) < (h2 - l2))
    return onset(ins & (x.c > h2), v), onset(ins & (x.c < l2), v)


def _engulf(x):
    o, c, h, l = x.o, x.c, x.h, x.l
    o1, c1 = _shift(o, 1), _shift(c, 1)
    l1, h1 = _shift(l, 1), _shift(h, 1)
    ll, hh = I.rolling_min(l, 10), I.rolling_max(h, 10)
    v = _fin(o1, c1, ll, hh)
    bull = v & (c1 < o1) & (c > o) & (o <= c1) & (c >= o1) & ((c - o) > (o1 - c1)) & (np.fmin(l, l1) <= ll)
    bear = v & (c1 > o1) & (c < o) & (o >= c1) & (c <= o1) & ((o - c) > (c1 - o1)) & (np.fmax(h, h1) >= hh)
    return onset(bull, v), onset(bear, v)


def _pin(x):
    o, c, h, l = x.o, x.c, x.h, x.l
    body, rng = np.abs(c - o), h - l
    lw, uw = np.fmin(o, c) - l, h - np.fmax(o, c)
    ll, hh = I.rolling_min(l, 10), I.rolling_max(h, 10)
    v = _fin(ll, hh)
    bull = v & (rng > 0) & (lw >= 2 * body) & (lw >= 0.6 * rng) & (l <= ll)
    bear = v & (rng > 0) & (uw >= 2 * body) & (uw >= 0.6 * rng) & (h >= hh)
    return onset(bull, v), onset(bear, v)


def _levels(x, grid):
    """L01: cell k_t = floor(c_t / grid) (a close on a level is at or above it, after rounding c / grid to 9 decimals);
    a move from k_{t-1} to k_t crosses the levels m x grid for k_{t-1} < m <= k_t (up) or k_t < m <= k_{t-1}
    (down). Fires (follow) when at least one crossed level was crossed by no close move of the 120 previous bars
    (t-120..t-1); needs t >= 120."""
    k = np.floor(np.round(x.c / grid, 9)).astype(np.int64)
    n = x.n
    buy, sell = np.zeros(n, bool), np.zeros(n, bool)
    last = {}
    for t in range(1, n):
        if k[t] == k[t - 1]:
            continue
        lo_, hi_ = (k[t - 1] + 1, k[t]) if k[t] > k[t - 1] else (k[t] + 1, k[t - 1])
        fresh = False
        for m in range(lo_, hi_ + 1):
            j = last.get(m)
            if j is None or j < t - 120:
                fresh = True
            last[m] = t
        if fresh and t >= 120:
            if k[t] > k[t - 1]:
                buy[t] = True
            else:
                sell[t] = True
    return buy, sell


def _er_rise(x):
    er = x.er()
    p = _prev(er)
    ok = _fin(er, p)
    ev = ok & (er > 0.5) & (p <= 0.5)
    mv = x.c - _shift(x.c, 24)
    return ev & (mv > 0), ev & (mv < 0)


def _er_fade(x):
    er = x.er()
    v = np.isfinite(er) & np.isfinite(I.rolling_max(x.c, 24))
    hi = v & (er < 0.15) & (x.c >= I.rolling_max(x.c, 24))
    lo = v & (er < 0.15) & (x.c <= I.rolling_min(x.c, 24))
    return onset(lo, v), onset(hi, v)


def _above_share(x):
    e = x.ema(20)
    ve = np.isfinite(e)
    ab = np.where(ve, (x.c > e).astype(float), np.nan)
    cnt = I.sma(ab, 20) * 20.0
    cnt = np.round(cnt)
    v = np.isfinite(cnt)
    return onset(cnt >= 17, v), onset(cnt <= 3, v)


def _ibs3(x):
    b = x.ibs()
    b1, b2 = _shift(b, 1), _shift(b, 2)
    v = _fin(b, b1, b2)
    return onset(v & (b > 0.8) & (b1 > 0.8) & (b2 > 0.8), v), onset(v & (b < 0.2) & (b1 < 0.2) & (b2 < 0.2), v)


def _zmove(x):
    sd = _shift(I.rolling_std(x.ret(), 500, ddof=1), 24)        # the 500 returns before the 24-bar move
    mv = np.log(x.c / _shift(x.c, 24))
    z = mv / (sd * np.sqrt(24.0))
    p = _prev(z)
    ok = _fin(z, p)
    return ok & (z > 3) & (p <= 3), ok & (z < -3) & (p >= -3)


def _swap(bs):
    return bs[1], bs[0]


SIGNAL_FN = {
    "T01": lambda x, m: _ema_cross(x, 10, 30), "T02": lambda x, m: _ema_cross(x, 20, 50),
    "T03": lambda x, m: _ema_cross(x, 50, 200), "T04": lambda x, m: _macd_sig(x), "T05": lambda x, m: _macd_zero(x),
    "T06": lambda x, m: _breakout(x, 20), "T07": lambda x, m: _breakout(x, 55), "T08": lambda x, m: _supertrend(x),
    "T09": lambda x, m: _ichimoku(x), "T10": lambda x, m: _keltner(x), "T11": lambda x, m: _boll_out(x),
    "T12": lambda x, m: _di_cross(x), "T13": lambda x, m: _psar(x),
    "R01": lambda x, m: _rsi(x, 2, 10, 90), "R02": lambda x, m: _rsi(x, 7, 20, 80),
    "R03": lambda x, m: _rsi(x, 14, 30, 70), "R04": lambda x, m: _stoch(x), "R05": lambda x, m: _swap(_boll_out(x)),
    "R06": lambda x, m: _cci(x), "R07": lambda x, m: _three(x), "R08": lambda x, m: _ibs1(x),
    "K01": lambda x, m: _shock(x, 3.0), "K02": lambda x, m: _shock(x, 4.0),
    "K03": lambda x, m: _swap(_shock(x, 3.0)), "K04": lambda x, m: _swap(_shock(x, 4.0)),
    "K05": lambda x, m: _range_shock(x), "K06": lambda x, m: _swap(_range_shock(x)),
    "K07": lambda x, m: _shock_retrace(x),
    "C01": lambda x, m: _squeeze(x), "C02": lambda x, m: _nr7(x), "C03": lambda x, m: _inside(x),
    "P01": lambda x, m: _engulf(x), "P02": lambda x, m: _pin(x),
    "L01": lambda x, m: _levels(x, ROUND_GRID[m]),
    "H01": lambda x, m: _er_rise(x), "H02": lambda x, m: _er_fade(x), "H03": lambda x, m: _above_share(x),
    "H04": lambda x, m: _ibs3(x), "H05": lambda x, m: _zmove(x),
}
assert set(SIGNAL_FN) == set(G.SIGNALS)


def events(sig, x, market):
    """(bar positions, sides) of one signal on one frame's indicators."""
    b, s = SIGNAL_FN[sig](x, market)
    b, s = np.asarray(b, bool), np.asarray(s, bool)
    both = b & s
    b, s = b & ~both, s & ~both
    pos = np.flatnonzero(b | s)
    return pos, np.where(b[pos], 1, -1).astype(np.int64)


# ------------------------------------------------------------------ filters
def h4_trend(fr_h4):
    """Series of sign(close - EMA200 of the H4 closes) indexed by the H4 bars' known_at (0 where undefined)."""
    e = I.ema(fr_h4["close"].to_numpy(float), 200)
    c = fr_h4["close"].to_numpy(float)
    tr = np.where(np.isfinite(e), np.sign(c - e), 0.0)
    return pd.Series(tr, index=pd.DatetimeIndex(fr_h4["known_at"]))


def _asof(series, times):
    """Last value known at or before each time (equality counts), 0 before the first."""
    if len(series) == 0:
        return np.zeros(len(times))
    k = np.searchsorted(series.index.as_unit("ns").asi8, pd.DatetimeIndex(times).as_unit("ns").asi8, side="right") - 1
    v = series.to_numpy()
    return np.where(k >= 0, v[np.clip(k, 0, None)], 0.0)


def filter_mask(flt, side, trend, adx_v, hour_ny):
    if flt == "F0":
        return np.ones(len(side), bool)
    if flt == "F1":
        return (trend != 0) & (side == trend)
    if flt == "F2":
        return (trend != 0) & (side == -trend)
    if flt == "F3":
        return np.isfinite(adx_v) & (adx_v >= 25)
    if flt == "F4":
        return np.isfinite(adx_v) & (adx_v < 20)
    if flt == "F5":
        return (hour_ny >= 18) | (hour_ny <= 2)
    if flt == "F6":
        return (hour_ny >= 3) & (hour_ny <= 7)
    if flt == "F7":
        return (hour_ny >= 8) & (hour_ny <= 16)
    raise ValueError(flt)


# ------------------------------------------------------------------ one market
def signal_tables(h1, market, now, sig_frames=None):
    """{(signal, frame): DataFrame(known_at, side, trend, adx, hour_ny)} for every signal-frame of the grammar (or
    the given pairs), each computed once from the frame's bars."""
    frs = FR.all_frames(h1, now)
    trend = h4_trend(frs["H4"])
    want = sig_frames if sig_frames is not None else [(s, f) for s, (_, fs, _) in G.SIGNALS.items() for f in fs]
    out = {}
    inds = {}
    for s, f in want:
        if market in G.NO_MARKET.get(s, ()):
            continue
        fr = frs[f]
        x = inds.setdefault(f, Ind(fr))
        pos, side = events(s, x, market)
        ka = pd.DatetimeIndex(fr["known_at"].to_numpy()[pos]) if len(pos) else pd.DatetimeIndex([], tz="UTC")
        ka = ka.tz_convert("UTC") if ka.tz is not None else ka.tz_localize("UTC")
        out[(s, f)] = pd.DataFrame({"known_at": ka, "side": side, "trend": _asof(trend, ka),
                                    "adx": x.adx()[2][pos] if len(pos) else np.zeros(0),
                                    "hour_ny": fr["hour_ny"].to_numpy()[pos] if len(pos) else np.zeros(0, int)})
    return out


def rule_signals(tables, rule_list, rule_index=None):
    """Long table (rule, known_at, side) of the given rules from the signal-frame tables; `rule` holds the rule's
    index in rule_index (default: position in rule_list)."""
    parts = []
    for i, r in enumerate(rule_list):
        t = tables.get((r["signal"], r["frame"]))
        if t is None or len(t) == 0:
            continue
        m = filter_mask(r["filter"], t["side"].to_numpy(), t["trend"].to_numpy(), t["adx"].to_numpy(),
                        t["hour_ny"].to_numpy())
        if not m.any():
            continue
        parts.append(pd.DataFrame({"rule": (i if rule_index is None else rule_index[r["id"]]),
                                   "known_at": t["known_at"].to_numpy()[m], "side": t["side"].to_numpy()[m]}))
    if not parts:
        return pd.DataFrame({"rule": np.zeros(0, np.int64), "known_at": pd.DatetimeIndex([], tz="UTC"),
                             "side": np.zeros(0, np.int64)})
    out = pd.concat(parts, ignore_index=True)
    out["known_at"] = pd.DatetimeIndex(out["known_at"]).tz_convert("UTC") if pd.DatetimeIndex(out["known_at"]).tz \
        else pd.DatetimeIndex(out["known_at"]).tz_localize("UTC")
    return out
