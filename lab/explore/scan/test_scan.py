"""Self-tests of the scan (synthetic bars only; no real bar is read). Ends with 'N/N checks passed'.

    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B -m scan.test_scan [--quick]

(1) indicators against second, plain implementations written here; hand cases of the signal conventions
(2) no look-ahead: for every signal id and frame, signals (with their filter inputs) computed on bars cut at 40 times
    equal the full run's signals up to each cut, on two fat-tailed synthetic markets (an FX and an index calendar);
    every H4 / D1 value is known at or after its last hourly bar's end; entries are never before known_at; a planted
    leak (H4 bars stamped one hour early) is caught; the kit's own checks.truncation_test on the whole rule table
(3) the wall: discovery cuts and refuses bars of 2019 or later; confirm refuses a wrong hash
(4) a planted world (R07 on H1 followed by a drift): the pipeline picks and confirms it
(5) a world without any edge, reduced grammar: picks and confirmations (numbers reported)
(6) determinism and resume
(7) the rule count and the list's hash
(8) repairs after the review: entry at the next hourly bar without a wait limit (ENTRY-WAIT); the scheduled-end
    known_at gives the same entry bar and the same H4 / D1 trades as the end of the last hourly bar (FRAME-KNOWN);
    confirmation bound to its discovery, once per list, and run_all.sh needs the committed hash (CONFIRM-NOT-BOUND);
    the report's t distribution over n >= 30 and its notes (REPORT-T-OUTLIERS, GRAMMAR-CHOICES)
"""
import os
import sys

if os.path.dirname(os.path.abspath(__file__)) in [os.path.abspath(p) for p in sys.path if p]:
    sys.path = [p for p in sys.path if os.path.abspath(p or ".") != os.path.dirname(os.path.abspath(__file__))]

import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from kit import checks as KC  # noqa: E402
from kit import data as KD  # noqa: E402
from kit import sim  # noqa: E402

from scan import confirm as CF  # noqa: E402
from scan import discover as DS  # noqa: E402
from scan import engine as E  # noqa: E402
from scan import frames as FR  # noqa: E402
from scan import grammar as G  # noqa: E402
from scan import indicators as I  # noqa: E402
from scan import select as SL  # noqa: E402
from scan import signals as SG  # noqa: E402
from scan import worlds as W  # noqa: E402

RESULTS = []
NUMBERS = {}


def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"  [{info}]" if info else ""), flush=True)


def close(a, b, tol=1e-9):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.shape != b.shape:
        return False
    na, nb = np.isnan(a), np.isnan(b)
    if not (na == nb).all():
        return False
    d = np.abs(a[~na] - b[~nb])
    return bool((d <= tol * np.maximum(1.0, np.abs(b[~nb]))).all())


# ------------------------------------------------------------------ (1) plain implementations
def p_sma(x, n):
    out = [math.nan] * len(x)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1:i + 1]
        out[i] = math.nan if any(math.isnan(v) for v in w) else sum(w) / n
    return np.array(out)


def p_smooth(x, n, alpha):
    out = [math.nan] * len(x)
    s = next((i for i, v in enumerate(x) if not math.isnan(v)), len(x))
    if len(x) - s < n:
        return np.array(out)
    v = sum(x[s:s + n]) / n
    out[s + n - 1] = v
    for i in range(s + n, len(x)):
        v = v + alpha * (x[i] - v)
        out[i] = v
    return np.array(out)


def p_ema(x, n):
    return p_smooth(list(x), n, 2.0 / (n + 1))


def p_wilder_classic(x, n):
    """(prev x (n - 1) + x) / n seeded with the mean of the first n values."""
    x = list(x)
    out = [math.nan] * len(x)
    s = next((i for i, v in enumerate(x) if not math.isnan(v)), len(x))
    if len(x) - s < n:
        return np.array(out)
    v = sum(x[s:s + n]) / n
    out[s + n - 1] = v
    for i in range(s + n, len(x)):
        v = (v * (n - 1) + x[i]) / n
        out[i] = v
    return np.array(out)


def p_tr(h, l, c):
    tr = [h[0] - l[0]]
    for i in range(1, len(h)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return tr


def p_atr(h, l, c, n):
    tr = p_tr(h, l, c)
    return p_wilder_classic([math.nan] + tr[1:], n)


def p_rsi(c, n):
    g, lo = [math.nan], [math.nan]
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        g.append(max(d, 0.0))
        lo.append(max(-d, 0.0))
    ag, al = p_wilder_classic(g, n), p_wilder_classic(lo, n)
    out = []
    for a, b in zip(ag, al):
        if math.isnan(a) or math.isnan(b):
            out.append(math.nan)
        elif b == 0:
            out.append(50.0 if a == 0 else 100.0)
        else:
            out.append(100.0 - 100.0 / (1.0 + a / b))
    return np.array(out)


def p_adx(h, l, c, n=14):
    N = len(h)
    tr = p_tr(h, l, c)
    pdm, mdm = [math.nan], [math.nan]
    for i in range(1, N):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
    # Wilder's running SUMS (S = S - S / n + x, seeded with the sum of the first n): the ratios equal the mean form's
    def wsum(x):
        out = [math.nan] * N
        if N < n + 1:
            return out
        v = sum(x[1:n + 1])
        out[n] = v
        for i in range(n + 1, N):
            v = v - v / n + x[i]
            out[i] = v
        return out
    st, sp, sm = wsum([math.nan] + tr[1:]), wsum(pdm), wsum(mdm)
    pdi, mdi, dx = [math.nan] * N, [math.nan] * N, [math.nan] * N
    for i in range(N):
        if math.isnan(st[i]):
            continue
        pdi[i] = 100 * sp[i] / st[i] if st[i] > 0 else 0.0
        mdi[i] = 100 * sm[i] / st[i] if st[i] > 0 else 0.0
        s = pdi[i] + mdi[i]
        dx[i] = 100 * abs(pdi[i] - mdi[i]) / s if s > 0 else 0.0
    return np.array(pdi), np.array(mdi), p_wilder_classic(dx, n)


def p_boll(c, n=20, k=2.0):
    import statistics
    m, u, d = [math.nan] * len(c), [math.nan] * len(c), [math.nan] * len(c)
    for i in range(n - 1, len(c)):
        w = c[i - n + 1:i + 1]
        mu, sd = sum(w) / n, statistics.pstdev(w)
        m[i], u[i], d[i] = mu, mu + k * sd, mu - k * sd
    return np.array(m), np.array(u), np.array(d)


def p_stoch(h, l, c, n=14):
    fk = [math.nan] * len(c)
    for i in range(n - 1, len(c)):
        hh, ll = max(h[i - n + 1:i + 1]), min(l[i - n + 1:i + 1])
        fk[i] = 50.0 if hh == ll else 100 * (c[i] - ll) / (hh - ll)
    k = p_sma(fk, 3)
    return k, p_sma(list(k), 3)


def p_cci(h, l, c, n=20):
    tp = [(a + b + d) / 3 for a, b, d in zip(h, l, c)]
    out = [math.nan] * len(tp)
    for i in range(n - 1, len(tp)):
        w = tp[i - n + 1:i + 1]
        m = sum(w) / n
        mad = sum(abs(v - m) for v in w) / n
        out[i] = (tp[i] - m) / (0.015 * mad) if mad > 0 else math.nan
    return np.array(out)


def p_supertrend(h, l, c, n=10, mult=3.0):
    a = p_atr(h, l, c, n)
    N = len(c)
    d = [0.0] * N
    fu = fl = None
    for i in range(N):
        if math.isnan(a[i]):
            continue
        mid = (h[i] + l[i]) / 2
        bu, bl = mid + mult * a[i], mid - mult * a[i]
        if fu is None:
            fu, fl, d[i] = bu, bl, 1.0
            continue
        nfu = bu if (bu < fu or c[i - 1] > fu) else fu
        nfl = bl if (bl > fl or c[i - 1] < fl) else fl
        if d[i - 1] > 0:
            d[i] = -1.0 if c[i] < nfl else 1.0
        else:
            d[i] = 1.0 if c[i] > nfu else -1.0
        fu, fl = nfu, nfl
    return np.array(d)


def p_ichimoku(h, l):
    N = len(h)

    def mid(i, n):
        if i < n - 1:
            return math.nan
        return (max(h[i - n + 1:i + 1]) + min(l[i - n + 1:i + 1])) / 2
    sa, sb = [math.nan] * N, [math.nan] * N
    for i in range(26, N):
        j = i - 26
        sa[i] = (mid(j, 9) + mid(j, 26)) / 2
        sb[i] = mid(j, 52)
    return np.array(sa), np.array(sb)


def p_psar(h, l, af0=0.02, amax=0.2):
    N = len(h)
    d = [0.0] * N
    sars = [math.nan] * N
    trend_up = (h[1] + l[1]) >= (h[0] + l[0])
    sar = l[0] if trend_up else h[0]
    ep = h[1] if trend_up else l[1]
    af = af0
    sars[1], d[1] = sar, 1.0 if trend_up else -1.0
    for i in range(2, N):
        nxt = sar + af * (ep - sar)
        if trend_up:
            nxt = min(nxt, l[i - 1], l[i - 2])
            if l[i] <= nxt:
                trend_up, nxt, ep, af = False, ep, l[i], af0
            else:
                if h[i] > ep:
                    ep = h[i]
                    af = min(af + af0, amax)
        else:
            nxt = max(nxt, h[i - 1], h[i - 2])
            if h[i] >= nxt:
                trend_up, nxt, ep, af = True, ep, h[i], af0
            else:
                if l[i] < ep:
                    ep = l[i]
                    af = min(af + af0, amax)
        sar = nxt
        sars[i], d[i] = sar, 1.0 if trend_up else -1.0
    return np.array(sars), np.array(d)


def p_er(c, n=24):
    out = [math.nan] * len(c)
    for i in range(n, len(c)):
        s = sum(abs(c[j] - c[j - 1]) for j in range(i - n + 1, i + 1))
        out[i] = abs(c[i] - c[i - n]) / s if s > 0 else math.nan
    return np.array(out)


def p_std(x, n):
    out = [math.nan] * len(x)
    for i in range(n - 1, len(x)):
        w = np.array(x[i - n + 1:i + 1])
        out[i] = float(np.std(w, ddof=1)) if not np.isnan(w).any() else math.nan
    return np.array(out)


def test_indicators():
    rng = np.random.default_rng(1)
    n = 700
    c = 100 * np.exp(np.cumsum(0.004 * rng.standard_normal(n)))
    o = np.r_[c[0], c[:-1]] * np.exp(0.001 * rng.standard_normal(n))
    h = np.maximum(o, c) * np.exp(np.abs(0.003 * rng.standard_normal(n)))
    l = np.minimum(o, c) * np.exp(-np.abs(0.003 * rng.standard_normal(n)))
    C, H, L = list(c), list(h), list(l)
    check("(1) SMA(20)", close(I.sma(c, 20), p_sma(C, 20)))
    for k in (10, 20, 50, 200):
        check(f"(1) EMA({k})", close(I.ema(c, k), p_ema(C, k)))
    m, s = I.macd(c)
    pl = p_ema(C, 12) - p_ema(C, 26)
    check("(1) MACD line and signal", close(m, pl) and close(s, p_ema(list(pl), 9)))
    for k in (2, 7, 14):
        check(f"(1) RSI({k}) Wilder", close(I.rsi(c, k), p_rsi(C, k), 1e-8))
    check("(1) ATR(20) Wilder", close(I.atr(h, l, c, 20), p_atr(H, L, C, 20)))
    pdi, mdi, ad = I.adx(h, l, c, 14)
    qp, qm, qa = p_adx(H, L, C, 14)
    check("(1) ADX(14), +DI, -DI", close(pdi, qp, 1e-8) and close(mdi, qm, 1e-8) and close(ad, qa, 1e-8))
    bm, bu, bd = I.bollinger(c)
    qm_, qu, qd = p_boll(C)
    check("(1) Bollinger(20,2)", close(bm, qm_) and close(bu, qu) and close(bd, qd))
    km, ku, kd = I.keltner(h, l, c)
    pa = p_atr(H, L, C, 20)
    pe = p_ema(C, 20)
    check("(1) Keltner EMA20 +/- 2 ATR20", close(km, pe) and close(ku, pe + 2 * pa) and close(kd, pe - 2 * pa))
    sk, sd = I.stochastic(h, l, c)
    qk, qd2 = p_stoch(H, L, C)
    check("(1) Stochastic(14,3,3)", close(sk, qk) and close(sd, qd2))
    check("(1) CCI(20)", close(I.cci(h, l, c), p_cci(H, L, C), 1e-8))
    check("(1) SuperTrend(10,3) direction", (I.supertrend(h, l, c)[1] == p_supertrend(H, L, C)).all())
    _, _, sa, sb = I.ichimoku(h, l)
    qa2, qb2 = p_ichimoku(H, L)
    check("(1) Ichimoku cloud (9,26,52), displaced 26", close(sa, qa2) and close(sb, qb2))
    ps, pdr = I.psar(h, l)
    qs, qdr = p_psar(H, L)
    check("(1) Parabolic SAR(0.02,0.2)", close(ps, qs) and (pdr == qdr).all())
    check("(1) efficiency ratio(24)", close(I.efficiency_ratio(c, 24), p_er(C, 24)))
    check("(1) internal bar strength", close(I.ibs(h, l, c), (c - l) / (h - l)))
    r = I.log_returns(c)
    check("(1) rolling sd of returns (500, ddof 1)", close(I.rolling_std(r, 500), p_std(list(r), 500)))
    # hand cases of the signal conventions
    a = np.array([1.0, 1.0, 2.0, 2.0, 1.0, 1.0])
    b = np.array([1.5, 1.5, 1.5, 2.0, 2.0, 0.5])
    check("(1) cross: strict now, weak before (a tie is not a cross; leaving a tie is)",
          (np.flatnonzero(SG.cross_up(a, b)) == [2, 5]).all() and (np.flatnonzero(SG.cross_dn(a, b)) == [4]).all())
    cond = np.array([False, True, True, False, True])
    valid = np.array([False, True, True, True, True])
    check("(1) onset: first bar where the condition holds, previous bar valid",
          (np.flatnonzero(SG.onset(cond, valid)) == [4]).all())
    fr = pd.DataFrame({"open": np.ones(131), "high": np.ones(131), "low": np.ones(131),
                       "close": np.r_[np.full(121, 1.095), 1.101, 1.099, 1.102, 1.105, 1.111, 1.099, 1.112, 1.111,
                                      1.098, 1.089]})
    b_, s_ = SG._levels(SG.Ind(fr), 0.01)
    check("(1) L01: fires on a fresh level only (1.10 up at 121, 1.11 up at 125, 1.09 down at 130; re-crossings within "
          "120 bars do not fire)", list(np.flatnonzero(b_)) == [121, 125] and list(np.flatnonzero(s_)) == [130],
          f"buys {list(np.flatnonzero(b_))} sells {list(np.flatnonzero(s_))}")


# ------------------------------------------------------------------ (2) no look-ahead
def _tables_equal(full, cut, c):
    bad = []
    for k in full:
        f = full[k]
        g = cut.get(k)
        fk = f[pd.DatetimeIndex(f.known_at) <= c].reset_index(drop=True)
        if g is None:
            g = fk.iloc[:0]
        if len(g) and (pd.DatetimeIndex(g.known_at) > c).any():
            bad.append((k, "row after the cut"))
            continue
        if len(fk) != len(g):
            bad.append((k, f"{len(fk)} rows in the full run up to the cut, {len(g)} in the cut run"))
            continue
        if not ((pd.DatetimeIndex(fk.known_at) == pd.DatetimeIndex(g.known_at)).all()
                and (fk.side.to_numpy() == g.side.to_numpy()).all()
                and np.array_equal(fk.trend.to_numpy(), g.trend.to_numpy())
                and np.array_equal(fk.adx.to_numpy(), g.adx.to_numpy(), equal_nan=True)
                and (fk.hour_ny.to_numpy() == g.hour_ny.to_numpy()).all()):
            bad.append((k, "values differ"))
    return bad


def _cuts(b, full, rng, n=40):
    ends = pd.DatetimeIndex(b.index) + pd.Timedelta(hours=1)
    lo = len(ends) // 5
    out = list(ends[rng.integers(lo, len(ends), 18)])                         # random bar ends
    t0, t1 = ends[lo].value, ends[-1].value
    out += [pd.Timestamp(int(v), tz="UTC") for v in rng.integers(t0, t1, 10)]  # random instants (any minute)
    ka = pd.DatetimeIndex(pd.concat([t.known_at for t in full.values() if len(t)]))
    ka = ka[ka > ends[lo]]
    for v in ka[rng.integers(0, len(ka), 12)]:                                 # 0-6 bar ends after a signal
        j = int(np.searchsorted(ends, v)) + int(rng.integers(0, 7))
        out.append(ends[min(j, len(ends) - 1)])
    return sorted(set(out))[:n] if len(set(out)) >= n else sorted(set(out))


def truncation_check(market, seed, start, end, n_cuts=40, label=""):
    b = W.bars(market, "fat", seed, start, end)
    now = pd.Timestamp(end, tz="UTC")
    full = SG.signal_tables(b, market, now)
    rng = np.random.default_rng(seed + 11)
    cuts = _cuts(b, full, rng, n_cuts)
    failures = []
    for c in cuts:
        bc = b[pd.DatetimeIndex(b.index) + pd.Timedelta(hours=1) <= c]
        bad = _tables_equal(full, SG.signal_tables(bc, market, c), c)
        failures += [(str(c), k, why) for k, why in bad]
    empty = sorted(f"{s}|{f}" for (s, f), t in full.items() if len(t) == 0)
    return failures, len(cuts), empty, full, b


def test_lookahead(quick=False):
    span = ("2013-01-01", "2019-01-01")          # six years: every signal-frame (K07 on D1 included) has signals
    covered = {}
    for market, seed in (("eurusd", 3), ("us500", 4)):
        t0 = time.time()
        fails, nc, empty, full, b = truncation_check(market, seed, *span)
        n_sf = len(full)
        check(f"(2) truncation, {market}: {n_sf} signal-frames x {nc} cuts equal the full run up to each cut",
              not fails and nc >= 40, f"{len(fails)} failures {fails[:3]}; {time.time() - t0:.0f} s")
        for k, t in full.items():
            covered[k] = covered.get(k, 0) + len(t)
        # frames: never known before the last hourly bar closed; known_at = the block's scheduled end
        now = pd.Timestamp(span[1], tz="UTC")
        ok = True
        for f in ("H4", "D1"):
            fr = FR.build(b, f, now)
            ok &= bool((fr.known_at >= fr.last_end).all())
            hrs = pd.DatetimeIndex(fr.known_at).tz_convert("America/New_York").hour
            ok &= bool(set(hrs) <= ({17, 21, 1, 5, 9, 13} if f == "H4" else {17}))
            ok &= bool((pd.DatetimeIndex(fr.known_at) <= now).all())
        check(f"(2) {market}: every H4 / D1 value known at or after its last hourly bar's end, at 17/21/01/05/09/13 NY",
              ok)
    empty = sorted(f"{s}|{f}" for (s, f), n in covered.items() if n == 0)
    check("(2) every signal-frame has signals in the truncation samples", not empty, f"none for {empty}")
    NUMBERS["truncation_signals"] = int(sum(covered.values()))
    # entries never before known_at, at the first bar opening at or after it (no wait limit: ENTRY-WAIT)
    b = W.bars("eurusd", "fat", 3, *span)
    tabs = SG.signal_tables(b, "eurusd", pd.Timestamp(span[1], tz="UTC"),
                            sig_frames=[("T01", "D1"), ("R07", "H4"), ("K01", "H1")])
    rl = [r for r in G.rules() if r["signal"] in ("T01", "R07", "K01") and r["filter"] == "F0" and
          (r["signal"], r["frame"]) in tabs]
    ri = {r["id"]: i for i, r in enumerate(G.rules())}
    from scan import engine as E
    tr = E.simulate_rules("eurusd", sim.Book(b, "eurusd"), tabs, rl, ri)
    lag = pd.concat([pd.Series(pd.DatetimeIndex(t.entry_time) - pd.DatetimeIndex(t.known_at)) for t in tr.values()])
    bt = pd.DatetimeIndex(b.index).as_unit("ns").asi8
    first = all(bool((bt[np.searchsorted(bt, pd.DatetimeIndex(t.known_at).as_unit("ns").asi8)] ==
                      pd.DatetimeIndex(t.entry_time).as_unit("ns").asi8).all()) for t in tr.values() if len(t))
    check("(2) entries at the first bar open at or after known_at (never before it; no wait limit)",
          bool((lag >= pd.Timedelta(0)).all()) and first, f"lags {lag.min()} .. {lag.max()}")
    # planted leaks: (a) H4 blocks stamped one hour before their end are refused by the frame builder's guard;
    # (b) a signal that fires one bar before its cross (it reads the next bar) is caught by the truncation test
    orig = FR.block_ends

    def leaky(idx, frame):
        e = orig(idx, frame)
        return e - pd.Timedelta(hours=1) if frame == "H4" else e
    FR.block_ends = leaky
    bl = W.bars("eurusd", "fat", 3, "2013-01-01", "2014-07-01")
    now = pd.Timestamp("2014-07-01", tz="UTC")
    try:
        SG.signal_tables(bl, "eurusd", now, sig_frames=[("T01", "H4")])
        guard = False
    except AssertionError:
        guard = True
    finally:
        FR.block_ends = orig
    check("(2) planted leak (a): H4 values stamped 1 h before their last bar's end are refused by the frame guard",
          guard)
    orig_fn = SG.SIGNAL_FN["T01"]

    def peek(x, m):
        b_, s_ = orig_fn(x, m)
        return np.r_[b_[1:], False], np.r_[s_[1:], False]
    SG.SIGNAL_FN["T01"] = peek
    try:
        full = SG.signal_tables(bl, "eurusd", now, sig_frames=[("T01", "H4"), ("T01", "H1")])
        rng = np.random.default_rng(5)
        caught = 0
        for c in _cuts(bl, full, rng, 40):
            bc = bl[pd.DatetimeIndex(bl.index) + pd.Timedelta(hours=1) <= c]
            caught += bool(_tables_equal(full, SG.signal_tables(bc, "eurusd", c, sig_frames=list(full)), c))
    finally:
        SG.SIGNAL_FN["T01"] = orig_fn
    check("(2) planted leak (b): a signal reading the next bar is caught by the truncation test", caught > 0,
          f"{caught} of 40 cuts differ")
    # the kit's own truncation test (200 cuts) on the whole rule table of one market
    bk = W.bars("usdjpy", "fat", 6, "2013-01-01", "2014-10-01")
    rules_all = G.rules()
    ri = {r["id"]: i for i, r in enumerate(rules_all)}

    def build(d):
        bb = d["bars"]
        now = pd.DatetimeIndex(bb.index).max() + pd.Timedelta(hours=1)
        t = SG.signal_tables(bb, "usdjpy", now)
        s = SG.rule_signals(t, rules_all, ri)
        return s[["known_at", "side", "rule"]]
    t0 = time.time()
    rep = KC.truncation_test(build, {"bars": bk}, row_len={"bars": pd.Timedelta(hours=1)},
                             cols=("known_at", "side", "rule"), **({"n_random_cuts": 40, "n_after_cuts": 20,
                                                                    "n_signal_cuts": 20} if quick else {}))
    dens = rep["density_ok"] if not quick else True
    check("(2) kit.checks.truncation_test (default dense cuts) on all 1,388 rules' signals of a market",
          rep["pass"] and dens, f"{len(rep['cuts'])} cuts, {rep['n_failed_cuts']} failed, {rep['n_signals']} "
          f"signals, {time.time() - t0:.0f} s")


# ------------------------------------------------------------------ (3) the wall
def test_wall(tmp):
    b = DS.read_bars("eurusd", "noise", 0)
    check("(3) the discovery reader cuts every bar of 2019 or later",
          len(b) > 0 and pd.DatetimeIndex(b.index).max() < DS.WALL and
          (pd.DatetimeIndex(b.index).max() + pd.Timedelta(hours=1)) <= DS.WALL)
    full = W.bars("eurusd", "noise", 0)
    rl, ri = DS.selected_rules(("T01",), ("H1",))
    try:
        DS.run_market("eurusd", full, rl, ri)
        refused = False
    except DS.WallError:
        refused = True
    check("(3) run_market refuses bars at or after 2019-01-01", refused)
    with DS._kit_end(DS.WALL):
        inside = KD.period_end() == DS.WALL
        try:
            sim.Book(full[pd.DatetimeIndex(full.index) < pd.Timestamp("2019-02-01", tz="UTC")], "eurusd")
            book_refused = False
        except KD.PeriodError:
            book_refused = True
    check("(3) under the wall the kit's period end is 2019-01-01 and sim.Book refuses a 2019 bar",
          inside and book_refused and KD.period_end() == pd.Timestamp("2022-01-01", tz="UTC"))
    p = os.path.join(tmp, "fake.json")
    with open(p, "w") as f:
        f.write('{"candidates": []}\n')
    good = hashlib.sha256(open(p, "rb").read()).hexdigest()
    try:
        CF.read_candidates(p, "0" * 64)
        r1 = False
    except CF.HashError:
        r1 = True
    try:
        CF.read_candidates(p, good)
        r2 = True
    except CF.HashError:
        r2 = False
    check("(3) confirm refuses a list whose sha256 is not the one given (and accepts the right one)", r1 and r2)


# ------------------------------------------------------------------ (4)-(6) pipelines
def pipeline(tmp, world, signals, frames, procs=2, seed=0, markets=None):
    sdir = os.path.join(tmp, f"scan_{world}_{seed}")
    os.makedirs(sdir, exist_ok=True)
    DS.run(os.path.join(sdir, "discovery"), procs, False, world, seed, markets, signals, frames, log=lambda *a: None)
    p, sha, st, picked = SL.run(os.path.join(sdir, "discovery"), sdir, log=lambda *a: None)
    rep = CF.run(p, sha, sdir, log=lambda *a: None)
    from scan import report as RP
    RP.build(sdir)
    return sdir, st, picked, rep


def test_planted(tmp):
    t0 = time.time()
    sdir, st, picked, rep = pipeline(tmp, "planted", ("R07", "R01", "T01", "K01", "C02", "T06"), ("H1", "H4"))
    hit = [c for c in picked if c["rule"] == W.PLANT_RULE]
    conf = [r for r in rep["results"] if r["rule"] == W.PLANT_RULE and r["confirmed"]]
    NUMBERS["planted"] = {"picks": len(picked), "confirmed": rep["n_confirmed"],
                          "planted_rule_units_picked": [c["unit"] for c in hit],
                          "planted_rule_units_confirmed": [r["unit"] for r in conf]}
    check(f"(4) planted world: {W.PLANT_RULE} is picked", bool(hit), json.dumps(NUMBERS["planted"]))
    check(f"(4) planted world: {W.PLANT_RULE} is confirmed on 2019-2021", bool(conf), f"{time.time() - t0:.0f} s")
    check("(4) planted world: report files written",
          all(os.path.isfile(os.path.join(sdir, f)) for f in ("discovery_summary.json", "confirmation.json",
                                                               "summary.txt", "frozen_candidates.sha256")))
    return sdir


def test_noise(tmp):
    t0 = time.time()
    sigs = ("T01", "T04", "T06", "T08", "R01", "R04", "R07", "K05", "C02", "P01", "H01", "H03")
    sdir, st, picked, rep = pipeline(tmp, "noise", sigs, None, seed=1)
    NUMBERS["noise"] = {"rules": int(st.rule.nunique()), "rule_units": int(len(st)),
                        "eligible": int(st.eligible.sum()), "picks": len(picked), "confirmed": rep["n_confirmed"],
                        "basket_t_ge_2.5": int(((st.t >= 2.5) & st.basket).sum()),
                        "single_t_ge_3": int(((st.t >= 3.0) & ~st.basket).sum()),
                        "share_t_gt_2_gross_free": float((st.t > 2).mean())}
    check("(5) noise world, reduced grammar: picks and confirmations counted (no gate)",
          rep["n_confirmed"] <= len(picked), json.dumps(NUMBERS["noise"]) + f"; {time.time() - t0:.0f} s")


def _digests(d, markets):
    return {m: str(DS.load_market(d, m)["digest"]) for m in markets}


def test_determinism(tmp):
    mk = ("eurusd", "us500", "oil", "xauusd")
    sig, fr = ("T01", "R07", "K05", "L01", "H03"), None
    a = os.path.join(tmp, "detA")
    b = os.path.join(tmp, "detB")
    DS.run(a, 2, False, "fat", 2, mk, sig, fr, log=lambda *x: None)
    DS.run(b, 1, False, "fat", 2, mk, sig, fr, log=lambda *x: None)
    da, db = _digests(a, mk), _digests(b, mk)
    check("(6) two discovery runs (2 processes and 1) give the same tables", da == db)
    os.remove(os.path.join(b, "us500.npz"))
    with open(os.path.join(b, "oil.npz"), "r+b") as f:          # a file cut by a crash
        f.truncate(1000)
    msgs = []
    DS.run(b, 2, False, "fat", 2, mk, sig, fr, log=msgs.append)
    skipped = sorted(m.split()[1].rstrip(":") for m in msgs if "skipped" in m)
    check("(6) a restart redoes the missing and the broken market only, and gives the same tables",
          _digests(b, mk) == da and skipped == ["eurusd", "xauusd"], f"skipped {skipped}")
    pa, sha_a, _, _ = SL.run(a, os.path.join(tmp, "selA"), log=lambda *x: None)
    pb, sha_b, _, _ = SL.run(b, os.path.join(tmp, "selB"), log=lambda *x: None)
    check("(6) the selection is the same on both", sha_a == sha_b)
    try:
        DS.run(a, 1, False, "fat", 3, mk, sig, fr, log=lambda *x: None)
        mixed = False
    except RuntimeError:
        mixed = True
    check("(6) a directory of another run is refused (no mixing of runs)", mixed)


def test_grammar():
    rs = G.rules()
    ids = [r["id"] for r in rs]
    cells = sum(len(G.markets_of(r["signal"])) for r in rs)
    check("(7) rule count 1,388 (H1 38x8x2 + H4 39x5x2 + D1 39x5x2), cells 20,784", len(rs) == 1388 and
          cells == 20784 and len(set(ids)) == len(ids), f"{len(rs)} rules, {cells} cells")
    sha_file = G.check_rules_file()
    check("(7) scan/rules.csv equals the generated list; its sha256", sha_file == G.sha256_text(G.csv_text()),
          sha_file)
    NUMBERS["rules_sha256"] = sha_file
    sib_ok = all(s in set(ids) for i in ids for s in G.siblings(i))
    check("(7) every sibling is a rule of the list", sib_ok)
    check("(7) ids are stable: 'T04|H4|F1|72h' exists, R08 has no H1 rule, F5-F7 are H1 only",
          "T04|H4|F1|72h" in ids and not any(i.startswith("R08|H1") for i in ids) and
          not any(("|F5|" in i or "|F6|" in i or "|F7|" in i) and "|H1|" not in i for i in ids))


# ------------------------------------------------------------------ (8) repairs after the review
def _all_trades(tr):
    ts = [t for t in tr.values() if len(t)]
    return pd.concat(ts, ignore_index=True) if ts else pd.DataFrame()


def test_entry_no_wait():
    """ENTRY-WAIT: a signal enters at the open of the next hourly bar, with no time limit (DIRECTION4 section 2)."""
    check("(8) ENTRY-WAIT: the engine has no wait limit (max_wait_h None)", E.MAX_WAIT_H is None)
    for market in ("eurusd", "us500"):
        b = W.bars(market, "noise", 5, end="2016-01-01")
        now = pd.Timestamp("2016-01-01", tz="UTC")
        rl, ri = DS.selected_rules(("R07", "K05"), ("D1", "H4"))
        rl = [r for r in rl if r["filter"] == "F0"]
        tabs = SG.signal_tables(b, market, now, sig_frames=sorted({(r["signal"], r["frame"]) for r in rl}))
        tr = E.simulate_rules(market, sim.Book(b, market), tabs, rl, ri)
        cnt = E.sim_counts(tr)
        t = _all_trades(tr)
        bt = pd.DatetimeIndex(b.index)
        ka = pd.DatetimeIndex(t["known_at"]).tz_convert("UTC")
        k = np.searchsorted(bt.as_unit("ns").asi8, ka.as_unit("ns").asi8, side="left")
        first = bool((bt[k] == pd.DatetimeIndex(t["entry_time"])).all())
        wait = (pd.DatetimeIndex(t["entry_time"]) - ka) / pd.Timedelta(hours=1)
        d1 = np.isin(t["rule"].to_numpy(), [ri[r["id"]] for r in rl if r["frame"] == "D1"])
        fri = np.asarray(ka.tz_convert("America/New_York").dayofweek == 4)
        gi, gc, ge = E.signal_counts(tabs, rl, ri, b.index)
        check(f"(8) ENTRY-WAIT {market}: no signal dropped as stale, every trade enters at the first bar at or after "
              "known_at, entries more than 2 h later exist (FX: Friday D1 signals at the Sunday reopening)",
              cnt.get("stale", 0) == 0 and first and (wait > 2).any() and
              (market != "eurusd" or ((wait[d1 & fri] > 40).sum() > 0)) and bool(((gc - ge) <= 1).all()),
              f"stale {cnt.get('stale', 0)}, trades {len(t)}, wait > 2 h {int((wait > 2).sum())}, max wait "
              f"{wait.max():.0f} h, Friday D1 trades {int((d1 & fri).sum())}")


def _holed(b, rng):
    """Bars whose H4 / D1 blocks stop early: drop 5 % of the bars at random and the last 1-3 bars before 17:00 New
    York on a third of the days."""
    idx = pd.DatetimeIndex(b.index)
    ny = idx.tz_convert("America/New_York")
    keep = rng.random(len(idx)) > 0.05
    day = np.asarray(FR._clock(idx).normalize().asi8)
    cut_days = set(rng.choice(np.unique(day), len(np.unique(day)) // 3, replace=False).tolist())
    late = np.asarray(ny.hour) >= 17 - rng.integers(1, 4, len(idx))
    late &= np.asarray(ny.hour) < 17
    keep &= ~(np.isin(day, list(cut_days)) & late)
    out = b[keep]
    out.attrs.update(b.attrs)
    return out


def test_known_stamp():
    """FRAME-KNOWN: the scheduled-end stamp versus the text's 'end of its last hourly bar'. With entry at the next
    hourly bar (no wait limit) both stamps give the same entry bar; H4 / D1 rules give the same trades."""
    rng = np.random.default_rng(11)
    b = _holed(W.bars("us500", "noise", 6, end="2016-01-01"), rng)
    now = pd.Timestamp("2016-01-01", tz="UTC")
    bt = pd.DatetimeIndex(b.index).as_unit("ns").asi8
    ok, n_late = True, 0
    for f in ("H4", "D1"):
        fr = FR.build(b, f, now)
        ka = pd.DatetimeIndex(fr.known_at).as_unit("ns").asi8
        le = pd.DatetimeIndex(fr.last_end).as_unit("ns").asi8
        n_late += int((ka > le).sum())
        ok &= bool((np.searchsorted(bt, ka) == np.searchsorted(bt, le)).all())
    check("(8) FRAME-KNOWN: on bars whose blocks stop early, the first bar at or after the scheduled end is the first "
          "bar at or after the last hourly bar's end", ok and n_late > 100, f"{n_late} blocks stamped later")
    rl, ri = DS.selected_rules(("R07", "K05", "T01"), ("H4", "D1"))
    rl = [r for r in rl if r["filter"] in ("F0", "F1", "F2", "F3")]
    sf = sorted({(r["signal"], r["frame"]) for r in rl})
    later = now + pd.Timedelta(days=7)            # every block complete under both stamps

    def trades():
        tabs = SG.signal_tables(b, "us500", later, sig_frames=sf)
        t = _all_trades(E.simulate_rules("us500", sim.Book(b, "us500"), tabs, rl, ri))
        return t.sort_values(["rule", "entry_time"], kind="mergesort").reset_index(drop=True)

    a = trades()
    orig = FR.build

    def build_last_end(h1, frame, now_):
        out = orig(h1, frame, now_)
        out["known_at"] = out["last_end"]
        return out

    FR.build = build_last_end
    try:
        c = trades()
    finally:
        FR.build = orig
    cols = ["rule", "side", "entry_time", "exit_time", "R", "R_stress", "R_gross"]
    same = len(a) == len(c) and len(a) > 0 and all(a[k].equals(c[k]) for k in cols)
    check("(8) FRAME-KNOWN: H4 / D1 rules (F0-F3) give the same trades with known_at = the last hourly bar's end",
          same, f"{len(a)} trades vs {len(c)}")


def test_confirm_binding(tmp, sdir):
    """CONFIRM-NOT-BOUND: confirmation takes only the frozen selection of its discovery, once."""
    p = os.path.join(sdir, "frozen_candidates.json")
    raw = open(p, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    doc = json.loads(raw.decode())
    ddir = os.path.join(sdir, "discovery")

    def attempt(d, name, out_dir=None, s=None, dd=ddir):
        od = out_dir or os.path.join(tmp, "bind_" + name)
        os.makedirs(od, exist_ok=True)
        q = os.path.join(od, "frozen_candidates.json")
        if d is not None:
            txt = json.dumps(d, indent=1, sort_keys=True) + "\n"
            with open(q, "w") as f:
                f.write(txt)
            s = hashlib.sha256(txt.encode()).hexdigest()
        else:
            q = p
        try:
            CF.run(q, s, od, log=lambda *a: None, ddir=dd)
            return False
        except CF.BindError:
            return True

    d = json.loads(raw.decode())
    d["candidates"] = [{"order": 1, "stage": "basket", "rule": "R08|H1|F0|6h", "rule_idx": -1, "unit": "FX8",
                        "markets": ["eurusd", "gbpusd"], "discovery": {}}]
    d["nothing"] = False
    r_foreign = attempt(d, "foreign")
    r_edit = r_short = True
    if doc["candidates"]:
        d = json.loads(raw.decode())
        d["candidates"][0]["markets"] = d["candidates"][0]["markets"][:1] + ["eurusd"]
        r_edit = attempt(d, "markets")
        d = json.loads(raw.decode())
        d["candidates"] = d["candidates"][:-1]
        d["nothing"] = not d["candidates"]
        r_short = attempt(d, "short")
    d = json.loads(raw.decode())
    d["discovery_digests"] = {k: "0" * 64 for k in d["discovery_digests"]}
    r_dig = attempt(d, "digests")
    d = json.loads(raw.decode())
    d["rules_sha256"] = "0" * 64
    r_rsha = attempt(d, "rules_sha")
    check("(8) CONFIRM-NOT-BOUND: refused with its own sha256: a rule outside rules.csv, an edited market list, a "
          "shortened list, other discovery digests, another rules_sha256",
          r_foreign and r_edit and r_short and r_dig and r_rsha,
          f"{r_foreign} {r_edit} {r_short} {r_dig} {r_rsha}; {len(doc['candidates'])} candidates")
    other = os.path.join(tmp, "bind_other")
    os.makedirs(other, exist_ok=True)
    with open(os.path.join(other, "confirmation.json"), "w") as f:
        json.dump({"candidates_sha256": "f" * 64}, f)
    r_other = attempt(None, "other", other, sha)
    logged = "refused" in open(os.path.join(other, "confirmation_runs.log")).read()
    check("(8) CONFIRM-NOT-BOUND: a confirmation.json of another list is never replaced; the refusal is logged",
          r_other and logged and json.load(open(os.path.join(other, "confirmation.json")))["candidates_sha256"] ==
          "f" * 64)
    before = open(os.path.join(sdir, "confirmation.json")).read()
    rep = CF.run(p, sha, sdir, log=lambda *a: None)
    runs = [json.loads(x) for x in open(os.path.join(sdir, "confirmation_runs.log"))]
    check("(8) CONFIRM-NOT-BOUND: a second run of the frozen list reproduces confirmation.json; both runs are logged",
          open(os.path.join(sdir, "confirmation.json")).read() == before and
          sum(r["event"] == "done" for r in runs) == 2 and rep["candidates_sha256"] == sha)
    altered = os.path.join(tmp, "bind_altered")
    os.makedirs(altered, exist_ok=True)
    b2 = json.loads(before)
    b2["n_confirmed"] = b2["n_confirmed"] + 1
    with open(os.path.join(altered, "confirmation.json"), "w") as f:
        json.dump(b2, f, indent=1, sort_keys=True)
    kept = open(os.path.join(altered, "confirmation.json")).read()
    r_alt = attempt(None, "altered", altered, sha)
    check("(8) CONFIRM-NOT-BOUND: a second run that differs from confirmation.json is refused and the first kept",
          r_alt and open(os.path.join(altered, "confirmation.json")).read() == kept)
    import subprocess
    env = {k: v for k, v in os.environ.items() if k not in ("FROZEN_SHA", "EXPECT_RULES_SHA")}
    env["SCAN_DIR"] = os.path.join(tmp, "runall")
    rc = subprocess.run(["bash", os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_all.sh"), "confirm"],
                        env=env, capture_output=True, text=True)
    check("(8) CONFIRM-NOT-BOUND: run_all.sh refuses the confirm stage without FROZEN_SHA (the committed hash)",
          rc.returncode == 3 and "FROZEN_SHA" in rc.stdout and
          not os.path.isfile(os.path.join(env["SCAN_DIR"], "confirmation.json")), f"exit {rc.returncode}")


def test_report_tdist(sdir):
    """REPORT-T-OUTLIERS / GRAMMAR-CHOICES: shares and median t over rule-units with n >= 30, and the notes."""
    from scan import report as RP
    summ = json.load(open(os.path.join(sdir, "discovery_summary.json")))
    st = pd.read_csv(os.path.join(sdir, "unit_stats.csv"))
    ok = True
    for r in summ["by_family"]:
        g = st[(st.family == r["family"]) & (st.basket == (r["units"] == "baskets"))]
        k = g[g.n >= RP.N_MIN_T]
        ok &= r[f"rule_units_n_ge_{RP.N_MIN_T}"] == len(k)
        if len(k):
            ok &= abs(r[f"median_t_n_ge_{RP.N_MIN_T}"] - round(float(k.t.median()), 4)) < 1e-9
            ok &= abs(r[f"share_t_gt_2_n_ge_{RP.N_MIN_T}"] - round(float((k.t > 2).mean()), 4)) < 1e-9
    no_mean = not any("mean_t" in key or "sd_t" in key for r in summ["by_family_frame_unit"] for key in r)
    txt = open(os.path.join(sdir, "summary.txt")).read()
    check("(8) REPORT: shares and median t over rule-units with n >= 30 beside the shares over all; no mean or sd of t;"
          " the grammar notes are in the summary", ok and no_mean and len(summ["notes"]) >= 6 and "notes:" in txt and
          "no time limit" in txt)


def main(argv=None):
    quick = "--quick" in (argv or sys.argv[1:])
    t0 = time.time()
    tmp = tempfile.mkdtemp(prefix="scan_test_", dir=os.path.expanduser("~/explore_data/scan_dev"))
    try:
        test_grammar()
        test_indicators()
        test_wall(tmp)
        test_lookahead(quick)
        test_determinism(tmp)
        test_entry_no_wait()
        test_known_stamp()
        sdir = test_planted(tmp)
        test_confirm_binding(tmp, sdir)
        test_report_tdist(sdir)
        test_noise(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("numbers:", json.dumps(NUMBERS, sort_keys=True))
    n_ok = sum(ok for _, ok in RESULTS)
    print(f"{n_ok}/{len(RESULTS)} checks passed in {time.time() - t0:.0f} s")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
