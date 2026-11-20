"""Causal indicators on one frame's bars (plain numpy). Every function takes 1-d float arrays in time order and
returns arrays of the same length; the value at index i uses indices <= i only, and is NaN during the warm-up (the
exact warm-up of each indicator is written in scan/GRAMMAR.md, section 'Indicators').

Conventions (GRAMMAR.md):
- SMA(n): mean of the last n values, NaN while fewer than n values exist or one of them is NaN.
- EMA(n): alpha = 2 / (n + 1), seeded with the SMA of the first n valid values (at the n-th valid value); a NaN
  inside the series after the seed propagates (never happens on bars).
- Wilder(n): alpha = 1 / n, seeded the same way (the SMA of the first n values).
- True range: TR_0 = h_0 - l_0, TR_i = max(h_i - l_i, |h_i - c_{i-1}|, |l_i - c_{i-1}|). ATR(n) = Wilder(n) of TR_1..,
  so its first value is at index n (the mean of TR_1..TR_n).
- Standard deviations of a window: population (ddof 0) for Bollinger, sample (ddof 1) for returns.
"""
import numpy as np


def _valid_start(x):
    ok = np.flatnonzero(np.isfinite(x))
    return int(ok[0]) if len(ok) else len(x)


def sma(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    w = np.lib.stride_tricks.sliding_window_view(x, n)
    out[n - 1:] = w.mean(axis=1)           # a NaN in a window gives NaN
    return out


def rolling_max(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = np.lib.stride_tricks.sliding_window_view(x, n).max(axis=1)
    return out


def rolling_min(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = np.lib.stride_tricks.sliding_window_view(x, n).min(axis=1)
    return out


def rolling_std(x, n, ddof=1):
    """Standard deviation of the last n values (ddof 1 by default), NaN while fewer than n or a NaN inside."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = np.lib.stride_tricks.sliding_window_view(x, n).std(axis=1, ddof=ddof)
    return out


def _recursive(x, n, alpha):
    """Exponential smoothing seeded by the SMA of the first n values from the first valid one."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    s = _valid_start(x)
    if len(x) - s < n:
        return out
    v = float(np.mean(x[s:s + n]))
    out[s + n - 1] = v
    a, b = alpha, 1.0 - alpha
    for i in range(s + n, len(x)):
        v = a * x[i] + b * v
        out[i] = v
    return out


def ema(x, n):
    return _recursive(x, n, 2.0 / (n + 1.0))


def wilder(x, n):
    return _recursive(x, n, 1.0 / n)


def true_range(h, l, c):
    h, l, c = (np.asarray(a, float) for a in (h, l, c))
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    if len(tr):
        tr[0] = h[0] - l[0]
    return tr


def atr(h, l, c, n):
    tr = true_range(h, l, c)
    tr1 = tr.copy()
    if len(tr1):
        tr1[0] = np.nan                     # Wilder's ATR starts with the first bar that has a previous close
    return wilder(tr1, n)


def rsi(c, n):
    """Wilder's RSI: average gain and loss by Wilder(n) of the close changes (first value at index n). Average loss 0:
    100 (50 when the average gain is 0 too)."""
    c = np.asarray(c, float)
    d = np.r_[np.nan, np.diff(c)]
    g = wilder(np.where(np.isfinite(d), np.maximum(d, 0.0), np.nan), n)
    lo = wilder(np.where(np.isfinite(d), np.maximum(-d, 0.0), np.nan), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100.0 - 100.0 / (1.0 + g / lo)
    r = np.where(lo == 0, np.where(g == 0, 50.0, 100.0), r)
    return np.where(np.isfinite(g) & np.isfinite(lo), r, np.nan)


def macd(c, fast=12, slow=26, sig=9):
    line = ema(c, fast) - ema(c, slow)
    return line, ema(line, sig)


def adx(h, l, c, n=14):
    """(+DI, -DI, ADX) of Wilder: +DM = up move if it is > the down move and > 0, else 0 (and the reverse); +DI =
    100 Wilder(+DM) / ATR (both Wilder(n) from index 1); DX = 100 |+DI - -DI| / (+DI + -DI) (0 when the sum is 0);
    ADX = Wilder(n) of DX (first value at index 2n - 1)."""
    h, l, c = (np.asarray(a, float) for a in (h, l, c))
    up = np.r_[np.nan, h[1:] - h[:-1]]
    dn = np.r_[np.nan, l[:-1] - l[1:]]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pdm[0] = mdm[0] = np.nan
    a = atr(h, l, c, n)
    sp, sm = wilder(pdm, n), wilder(mdm, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = np.where(a > 0, 100.0 * sp / a, 0.0)
        mdi = np.where(a > 0, 100.0 * sm / a, 0.0)
        s = pdi + mdi
        dx = np.where(s > 0, 100.0 * np.abs(pdi - mdi) / s, 0.0)
    ok = np.isfinite(a) & np.isfinite(sp) & np.isfinite(sm)
    pdi, mdi, dx = (np.where(ok, v, np.nan) for v in (pdi, mdi, dx))
    return pdi, mdi, wilder(dx, n)


def bollinger(c, n=20, k=2.0):
    """(middle, upper, lower): SMA(n) +/- k x population standard deviation of the last n closes."""
    m = sma(c, n)
    sd = rolling_std(c, n, ddof=0)
    return m, m + k * sd, m - k * sd


def keltner(h, l, c, n=20, k=2.0):
    """(middle, upper, lower): EMA(n) of the close +/- k x ATR(n) (Wilder)."""
    m = ema(c, n)
    a = atr(h, l, c, n)
    return m, m + k * a, m - k * a


def stochastic(h, l, c, n=14, k_smooth=3, d_smooth=3):
    """Slow stochastic: fast %K = 100 (c - lowest low n) / (highest high n - lowest low n) (50 when the range is 0),
    %K = SMA(k_smooth) of it, %D = SMA(d_smooth) of %K."""
    hh, ll = rolling_max(h, n), rolling_min(l, n)
    rng = hh - ll
    with np.errstate(divide="ignore", invalid="ignore"):
        fk = np.where(rng > 0, 100.0 * (np.asarray(c, float) - ll) / rng, 50.0)
    fk = np.where(np.isfinite(rng), fk, np.nan)
    k = sma(fk, k_smooth)
    return k, sma(k, d_smooth)


def cci(h, l, c, n=20):
    """(TP - SMA(n) of TP) / (0.015 x mean absolute deviation of the last n TP around that SMA); NaN when the
    deviation is 0. TP = (h + l + c) / 3."""
    tp = (np.asarray(h, float) + np.asarray(l, float) + np.asarray(c, float)) / 3.0
    m = sma(tp, n)
    out = np.full(len(tp), np.nan)
    if len(tp) >= n:
        w = np.lib.stride_tricks.sliding_window_view(tp, n)
        mad = np.abs(w - m[n - 1:, None]).mean(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[n - 1:] = np.where(mad > 0, (tp[n - 1:] - m[n - 1:]) / (0.015 * mad), np.nan)
    return out


def supertrend(h, l, c, n=10, mult=3.0):
    """(line, direction +1/-1). ATR(n) Wilder; basic bands hl2 +/- mult ATR; final upper band = basic upper if it is
    below the previous final upper or the previous close was above it, else the previous final upper (lower band
    mirrored); direction starts at +1 on the first bar with an ATR, turns -1 when the close falls below the final
    lower band, +1 when it rises above the final upper band. NaN / 0 before the first ATR."""
    h, l, c = (np.asarray(a, float) for a in (h, l, c))
    a = atr(h, l, c, n)
    hl2 = (h + l) / 2.0
    ub, lb = hl2 + mult * a, hl2 - mult * a
    N = len(c)
    fub, flb = np.full(N, np.nan), np.full(N, np.nan)
    d = np.zeros(N)
    line = np.full(N, np.nan)
    s = _valid_start(a)
    for i in range(s, N):
        if i == s:
            fub[i], flb[i], d[i] = ub[i], lb[i], 1.0
        else:
            fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
            flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
            if d[i - 1] > 0:
                d[i] = -1.0 if c[i] < flb[i] else 1.0
            else:
                d[i] = 1.0 if c[i] > fub[i] else -1.0
        line[i] = flb[i] if d[i] > 0 else fub[i]
    return line, d


def ichimoku(h, l, n1=9, n2=26, n3=52):
    """(tenkan, kijun, span A, span B) where the spans are those of the cloud drawn AT each bar, i.e. computed at
    the bar n2 bars earlier (displacement n2: cloud at i = ((tenkan + kijun) / 2 at i - n2, (HH n3 + LL n3) / 2 at
    i - n2))."""
    ten = (rolling_max(h, n1) + rolling_min(l, n1)) / 2.0
    kij = (rolling_max(h, n2) + rolling_min(l, n2)) / 2.0
    a0 = (ten + kij) / 2.0
    b0 = (rolling_max(h, n3) + rolling_min(l, n3)) / 2.0
    sa, sb = np.full(len(a0), np.nan), np.full(len(b0), np.nan)
    sa[n2:], sb[n2:] = a0[:-n2], b0[:-n2]
    return ten, kij, sa, sb


def psar(h, l, af0=0.02, af_max=0.2):
    """Wilder's Parabolic SAR: (sar, direction +1/-1) with sar = the stop level in force DURING each bar. Start at
    bar 1: up if h1 + l1 >= h0 + l0, SAR = the extreme of bar 0 on the other side,
    EP = the extreme of bar 1, AF = af0. Each next bar: SAR += AF (EP - SAR), capped by the two previous lows (up)
    / highs (down); a bar whose low (high) reaches the SAR flips: the new SAR is the old EP, EP = that bar's extreme,
    AF = af0; otherwise a new extreme raises AF by af0 up to af_max. Direction of bar i = the trend AFTER bar i."""
    h, l = np.asarray(h, float), np.asarray(l, float)
    N = len(h)
    sar, d = np.full(N, np.nan), np.zeros(N)
    if N < 2:
        return sar, d
    up = (h[1] + l[1]) >= (h[0] + l[0])
    s = l[0] if up else h[0]
    ep = h[1] if up else l[1]
    af = af0
    sar[1], d[1] = s, (1.0 if up else -1.0)
    for i in range(2, N):
        s = s + af * (ep - s)
        if up:
            s = min(s, l[i - 1], l[i - 2])
            if l[i] <= s:
                up, s, ep, af = False, ep, l[i], af0
            elif h[i] > ep:
                ep, af = h[i], min(af + af0, af_max)
        else:
            s = max(s, h[i - 1], h[i - 2])
            if h[i] >= s:
                up, s, ep, af = True, ep, h[i], af0
            elif l[i] < ep:
                ep, af = l[i], min(af + af0, af_max)
        sar[i], d[i] = s, (1.0 if up else -1.0)
    return sar, d


def efficiency_ratio(c, n=24):
    """|c_i - c_{i-n}| / sum of |c_j - c_{j-1}| for j = i-n+1..i; NaN when the sum is 0 or during the warm-up."""
    c = np.asarray(c, float)
    out = np.full(len(c), np.nan)
    if len(c) <= n:
        return out
    ad = np.abs(np.diff(c))
    cs = np.r_[0.0, np.cumsum(ad)]
    den = cs[n:] - cs[:-n]                    # sum of the n changes ending at i = n..N-1
    num = np.abs(c[n:] - c[:-n])
    with np.errstate(divide="ignore", invalid="ignore"):
        out[n:] = np.where(den > 0, num / den, np.nan)
    return out


def ibs(h, l, c):
    """Internal bar strength (c - l) / (h - l); NaN when h == l."""
    h, l, c = (np.asarray(a, float) for a in (h, l, c))
    rng = h - l
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(rng > 0, (c - l) / rng, np.nan)


def log_returns(c):
    c = np.asarray(c, float)
    return np.r_[np.nan, np.log(c[1:] / c[:-1])]
