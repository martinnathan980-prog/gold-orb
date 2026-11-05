"""Mean-reversion track (meanrev) for XAUUSD -- causal order generators.

    from strategy import make_orders, FINALISTS
    orders = make_orders(m1, **FINALISTS[name])        # any M1 frame (UTC, bid/ask cols)
    trades = goldlab.simulate(m1, orders, sym="xauusd", no_overlap=True)

Families (param `family`):
  rsi   Connors-style RSI(n) extreme on tf bars ('D','4h','1h'), optional SMA trend filter
        and ADX regime filter; exit when close crosses SMA(exit_ma) or RSI normalises, time stop.
  bb    rolling z-score / Bollinger fade (|z| >= k) with target = rolling mean at signal time.
  ibs   daily Internal Bar Strength extreme, exit after `hold` days.
  sess  intraday overextension fade: at a NY clock time, price >= k x ATR(D) away from a
        session reference open -> fade; stop beyond session extreme, optional retrace target,
        forced exit at a NY clock time the same day.
  gap   weekend-gap fade: Sunday reopen vs Friday close, target = Friday close.
  soup  failed-breakout fade of the prior n-bar extreme (Connors-Raschke "Turtle Soup"):
        'close_inside' (pierced and closed back inside -> fade next session) or 'stop_entry'.
        Finalist A = soup D n=5: low < prior 5-day low but close back above it -> buy (mirror sell),
        stop = today's extreme -/+ stop_buf x ATR14(D), exit at the 3rd daily close.
  ret   multi-day return-extreme reversal (n-day log return z-score vs rolling daily vol).

Causality rules used everywhere:
  * a bar from goldlab.bars() is only known at its t_close; every indicator is a rolling /
    recursive function of bars <= the decision bar (no centred windows, no global stats);
  * entries are placed at entry_index(m1, decision_time) (first M1 bar starting >= decision);
  * daily ('D') decisions are taken at the 17:00 NY close and EXECUTED `delay_min` minutes
    after the next M1 bar (the 18:00 NY reopen, whose spread is ~3x normal);
  * exit rules (SMA cross, RSI normalisation) are evaluated on later closed bars only;
  * every order has a stop and a forced exit (exit_i) <= `hold_cap_h` hours after entry.
Warm-up: needs ~max(trend_n, 60) bars of the signal timeframe before the first usable signal.
"""
import os
import sys

import numpy as np
import pandas as pd

_LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if _LAB not in sys.path:
    sys.path.insert(0, _LAB)
import goldlab as gl  # noqa: E402


# ----------------------------------------------------------------------------- indicators
def sma(x, n):
    return x.rolling(int(n), min_periods=int(n)).mean()


def rsi(c, n):
    """Wilder RSI (recursive, causal)."""
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1.0 / n, adjust=False).mean()
    dn = (-d).clip(lower=0).ewm(alpha=1.0 / n, adjust=False).mean()
    return 100.0 - 100.0 / (1.0 + up / dn)


def adx(b, n=14):
    """Wilder ADX on mid prices (causal)."""
    h, l, c = b["h"], b["l"], b["c"]
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=b.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=b.index)
    pc = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - pc).abs(), (l - pc).abs()))
    a = tr.ewm(alpha=1.0 / n, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=1.0 / n, adjust=False).mean() / a
    mdi = 100 * mdm.ewm(alpha=1.0 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=1.0 / n, adjust=False).mean()


def _next_true(cond):
    """nxt[k] = first index >= k where cond is True (len(cond) if none)."""
    n = len(cond)
    idx = np.where(np.asarray(cond, bool), np.arange(n), n)
    return np.minimum.accumulate(idx[::-1])[::-1]


# ----------------------------------------------------------------------------- order helpers
_ORDER_COLS = ["entry_i", "side", "stop", "stop_dist", "target", "exit_i", "tag"]


def _empty():
    return pd.DataFrame({c: pd.Series(dtype="float64") for c in _ORDER_COLS}).astype(
        {"entry_i": "int64", "side": "int64", "exit_i": "int64", "tag": "object"})


def _exec_index(m1, times, delay_min, max_gap_min):
    """M1 index where a decision taken at `times` is executed.
    delay_min > 0: `delay_min` minutes after the first tradable bar (skips the reopen spread).
    Returns (index array, ok mask)."""
    N = len(m1)
    ix = m1.index
    i0 = gl.entry_index(m1, times)
    ok = i0 < N
    i0c = np.minimum(i0, N - 1)
    if delay_min and delay_min > 0:
        i1 = gl.entry_index(m1, ix[i0c] + pd.Timedelta(minutes=delay_min))
        ok &= i1 < N
        return np.minimum(i1, N - 1), ok
    if max_gap_min is not None:
        gap = (ix[i0c] - pd.DatetimeIndex(times)) / pd.Timedelta(minutes=1)
        ok &= np.asarray(gap <= max_gap_min)
    return i0c, ok


def _bar_orders(m1, b, j, side, stop_dist, exit_bar, delay_min=0, max_gap_min=10,
                hold_cap_h=166.0, target=None, tag="", xkind=None):
    """Orders for signals on bars b at positions j (decision at b.t_close[j])."""
    if len(j) == 0:
        return _empty()
    N, nb_ = len(m1), len(b)
    tc = pd.DatetimeIndex(b["t_close"].to_numpy())
    ei, ok = _exec_index(m1, tc[j], delay_min, max_gap_min)
    # exit decision at close of exit_bar, executed like an entry (same delay rule)
    xb = np.minimum(exit_bar, nb_ - 1)
    xi, okx = _exec_index(m1, tc[xb], delay_min, None)
    xi = np.where((exit_bar >= nb_) | ~okx, N - 1, xi)
    cap = gl.entry_index(m1, m1.index[ei] + pd.Timedelta(hours=hold_cap_h))
    xi = np.minimum(xi, np.minimum(cap, N - 1))
    o = pd.DataFrame({
        "entry_i": ei.astype(np.int64), "side": np.asarray(side, np.int64),
        "stop": np.nan, "stop_dist": np.asarray(stop_dist, float),
        "target": np.nan if target is None else np.asarray(target, float),
        "exit_i": xi.astype(np.int64), "tag": tag,
        "xkind": 0 if xkind is None else np.asarray(xkind, np.int64),
    })
    o = o[ok & np.isfinite(o.stop_dist.to_numpy()) & (o.stop_dist.to_numpy() > 0)]
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


# ----------------------------------------------------------------------------- families
def _rsi_orders(m1, tf="D", rsi_n=2, lo=10.0, hi=90.0, trend_n=200, exit_ma=5, exit_rsi=None,
                max_bars=5, stop_atr=3.0, atr_n=14, sides="both", adx_max=None, adx_n=14,
                delay_min=None, hold_cap_h=166.0):
    b = gl.bars(m1, tf)
    if delay_min is None:
        delay_min = 120 if tf == "D" else 0
    c = b["c"]
    r = rsi(c, rsi_n)
    a = gl.atr(b, atr_n)
    lg = (r < lo).to_numpy().copy()
    sh = (r > hi).to_numpy().copy()
    if trend_n:
        m = sma(c, trend_n)
        lg &= (c > m).to_numpy()
        sh &= (c < m).to_numpy()
    if adx_max:
        ad = adx(b, adx_n).to_numpy()
        lg &= ad < adx_max
        sh &= ad < adx_max
    do_l, do_s = sides in ("both", "long"), sides in ("both", "short")
    lg &= do_l
    sh &= do_s
    # exit conditions (evaluated at later closes)
    if exit_ma:
        me = sma(c, exit_ma)
        xl = (c > me).to_numpy()
        xs = (c < me).to_numpy()
    else:
        xl = (r > exit_rsi).to_numpy()
        xs = (r < 100 - exit_rsi).to_numpy()
    nl, ns = _next_true(xl), _next_true(xs)
    nb_ = len(b)
    jl, js = np.flatnonzero(lg), np.flatnonzero(sh)
    j = np.r_[jl, js]
    side = np.r_[np.ones(len(jl), int), -np.ones(len(js), int)]
    nxt_l = np.r_[nl, nb_][np.minimum(jl + 1, nb_)]
    nxt_s = np.r_[ns, nb_][np.minimum(js + 1, nb_)]
    nxt = np.r_[nxt_l, nxt_s]
    xb = np.minimum(nxt, j + max_bars)
    sd = stop_atr * a.to_numpy()[j]
    return _bar_orders(m1, b, j, side, sd, xb, delay_min=delay_min, hold_cap_h=hold_cap_h,
                       tag=f"rsi{tf}", xkind=(nxt <= j + max_bars).astype(int))


def _bb_orders(m1, tf="1h", n=20, k=2.0, stop_atr=2.0, atr_n=14, max_bars=24, sides="both",
               target="mean", trend_n=0, adx_max=None, adx_n=14, delay_min=None, hold_cap_h=166.0):
    b = gl.bars(m1, tf)
    if delay_min is None:
        delay_min = 120 if tf == "D" else 0
    c = b["c"]
    m = sma(c, n)
    s = c.rolling(n, min_periods=n).std(ddof=0)
    z = ((c - m) / s).to_numpy()
    a = gl.atr(b, atr_n).to_numpy()
    lg = z < -k
    sh = z > k
    if trend_n:
        mt = sma(c, trend_n)
        lg &= (c > mt).to_numpy()
        sh &= (c < mt).to_numpy()
    if adx_max:
        ad = adx(b, adx_n).to_numpy()
        lg &= ad < adx_max
        sh &= ad < adx_max
    lg &= sides in ("both", "long")
    sh &= sides in ("both", "short")
    jl, js = np.flatnonzero(lg), np.flatnonzero(sh)
    j = np.r_[jl, js]
    side = np.r_[np.ones(len(jl), int), -np.ones(len(js), int)]
    tgt = m.to_numpy()[j] if target == "mean" else None
    return _bar_orders(m1, b, j, side, stop_atr * a[j], j + max_bars, delay_min=delay_min,
                       hold_cap_h=hold_cap_h, target=tgt, tag=f"bb{tf}")


def _ibs_orders(m1, lo=0.2, hi=0.8, hold=1, stop_atr=2.5, atr_n=14, trend_n=0, sides="both",
                delay_min=120, hold_cap_h=166.0):
    b = gl.bars(m1, "D")
    c = b["c"]
    rng = (b["h"] - b["l"]).replace(0, np.nan)
    ibs = ((c - b["l"]) / rng).to_numpy()
    a = gl.atr(b, atr_n).to_numpy()
    lg, sh = ibs < lo, ibs > hi
    if trend_n:
        mt = sma(c, trend_n)
        lg &= (c > mt).to_numpy()
        sh &= (c < mt).to_numpy()
    lg &= sides in ("both", "long")
    sh &= sides in ("both", "short")
    jl, js = np.flatnonzero(lg), np.flatnonzero(sh)
    j = np.r_[jl, js]
    side = np.r_[np.ones(len(jl), int), -np.ones(len(js), int)]
    return _bar_orders(m1, b, j, side, stop_atr * a[j], j + hold, delay_min=delay_min,
                       hold_cap_h=hold_cap_h, tag="ibs")


def _day_times(days, hhmm, tz):
    """UTC times of wall-clock `hhmm` in `tz` on the (NY) calendar date of each trading day."""
    hh, mm = (int(x) for x in hhmm.split(":"))
    loc = (pd.DatetimeIndex(days) + pd.Timedelta(hours=hh, minutes=mm)).tz_localize(
        tz, ambiguous="NaT", nonexistent="NaT")
    return loc.tz_convert("UTC")


def _sess_orders(m1, ref="ldn", check="11:00", k=1.0, target_frac=0.5, stop_buf=0.25,
                 stop_mode="extreme", stop_atr=1.0, exit_at="16:30", atr_n=14, sides="both",
                 adx_max=None, adx_n=14, max_gap_min=5):
    """Fade intraday overextension. ref: 'day' = trading-day open (18:00 NY reopen),
    'ldn' = 08:00 London, 'ny' = 08:20 NY (pre-US-data). check/exit_at are NY wall clock
    on the NY calendar date of the trading day."""
    N = len(m1)
    D = gl.bars(m1, "D")
    days = D.index
    aD = gl.atr(D, atr_n).shift(1).to_numpy()          # ATR known before the day starts
    adD = adx(D, adx_n).shift(1).to_numpy() if adx_max else None
    t_chk = _day_times(days, check, gl.NY)
    t_ext = _day_times(days, exit_at, gl.NY)
    if ref == "day":
        # first M1 bar of the trading day = first bar >= previous day's t_close
        t_ref = pd.DatetimeIndex(D["t_close"].shift(1).to_numpy())
    elif ref == "ldn":
        t_ref = _day_times(days, "08:00", gl.LDN)
    elif ref == "ny":
        t_ref = _day_times(days, "08:20", gl.NY)
    else:
        raise ValueError(ref)
    valid = ~(pd.isna(t_chk) | pd.isna(t_ext) | pd.isna(t_ref)) & np.isfinite(aD)
    valid = np.asarray(valid)
    days, aD = days[valid], aD[valid]
    if adD is not None:
        adD = adD[valid]
    t_chk, t_ext, t_ref = t_chk[valid], t_ext[valid], t_ref[valid]
    ir = gl.entry_index(m1, t_ref)
    ic = gl.entry_index(m1, t_chk)              # executed at open of bar ic; info = bars < ic
    ix = gl.entry_index(m1, t_ext)
    # never hold past the last bar of the trading day (early closes / missing bars)
    last_i = gl.entry_index(m1, pd.DatetimeIndex(D["t_close"]).values[valid]) - 1
    ix = np.minimum(ix, last_i)
    ok = (ir < N) & (ic < N) & (ix < N) & (ic - 1 > ir) & (ix > ic)
    ir, ic, ix = np.minimum(ir, N - 1), np.minimum(ic, N - 1), np.minimum(ix, N - 1)
    idx = m1.index
    td_all = gl.trading_day(idx)
    tdv = td_all.values
    # the check bar and the reference bar must belong to the same trading day as `days`
    dv = days.values.astype("datetime64[ns]")
    ok &= (tdv[ir] == dv) & (tdv[ic - 1] == dv) & (tdv[ic] == dv)
    # the last known bar must be recent (market open) and the entry bar must be on time
    ok &= np.asarray((idx[ic] - t_chk) <= pd.Timedelta(minutes=max_gap_min))
    ok &= np.asarray((t_chk - idx[ic - 1]) <= pd.Timedelta(minutes=max_gap_min + 1))
    mo = ((m1["bo"] + m1["ao"]) / 2).to_numpy()
    mc = ((m1["bc"] + m1["ac"]) / 2).to_numpy()
    mh = ((m1["bh"] + m1["ah"]) / 2).to_numpy()
    ml = ((m1["bl"] + m1["al"]) / 2).to_numpy()
    sel = np.flatnonzero(ok)
    if len(sel) == 0:
        return _empty()
    ir_, ic_, ix_ = ir[sel], ic[sel], ix[sel]
    refp = mo[ir_]
    px = mc[ic_ - 1]
    # session extremes over [ir, ic)
    hi = np.array([mh[a:b_].max() for a, b_ in zip(ir_, ic_)])
    lo_ = np.array([ml[a:b_].min() for a, b_ in zip(ir_, ic_)])
    at = aD[sel]
    disp = (px - refp) / at
    side = np.where(disp >= k, -1, np.where(disp <= -k, 1, 0))
    if adx_max:
        side = np.where(adD[sel] < adx_max, side, 0)
    if sides == "long":
        side = np.where(side > 0, side, 0)
    elif sides == "short":
        side = np.where(side < 0, side, 0)
    keep = side != 0
    if stop_mode == "extreme":
        stop = np.where(side < 0, hi + stop_buf * at, lo_ - stop_buf * at)
        sd = np.full(len(side), np.nan)
    else:
        stop = np.full(len(side), np.nan)
        sd = stop_atr * at
    tgt = px + (refp - px) * target_frac if target_frac else np.full(len(side), np.nan)
    o = pd.DataFrame({"entry_i": ic_, "side": side, "stop": stop, "stop_dist": sd,
                      "target": tgt, "exit_i": ix_, "tag": "sess"})[keep]
    # a stop on the wrong side of the expected fill would be a degenerate order: drop
    o = o[~((o.side > 0) & (o.stop >= px[keep])) & ~((o.side < 0) & (o.stop <= px[keep]))]
    return o.sort_values("entry_i").reset_index(drop=True)


def _gap_orders(m1, g=0.25, delay_min=60, stop_atr=1.0, hold_h=16.0, atr_n=14, sides="both",
                min_weekend_h=36.0):
    """Fade the weekend gap: Sunday reopen vs Friday last price, target Friday close."""
    N = len(m1)
    idx = m1.index
    D = gl.bars(m1, "D")
    aD = gl.atr(D, atr_n)
    dt = np.diff(idx.values).astype("timedelta64[m]").astype(float) / 60.0
    wk = np.flatnonzero(dt >= min_weekend_h) + 1         # first bar after a weekend break
    if len(wk) == 0:
        return _empty()
    mc = ((m1["bc"] + m1["ac"]) / 2).to_numpy()
    mo = ((m1["bo"] + m1["ao"]) / 2).to_numpy()
    fri = mc[wk - 1]
    gap = mo[wk] - fri
    # ATR known at the Friday close: last D bar whose t_close <= time of bar wk-1 (+1 min)
    tcD = pd.DatetimeIndex(D["t_close"]).values            # datetime64 (UTC)
    jD = np.searchsorted(tcD, (idx[wk - 1] + pd.Timedelta(minutes=1)).values, side="right") - 1
    at = aD.to_numpy()[np.maximum(jD, 0)]
    ei = gl.entry_index(m1, idx[wk] + pd.Timedelta(minutes=delay_min))
    ok = (ei < N) & (jD >= 0) & np.isfinite(at)
    ei = np.minimum(ei, N - 1)
    px = mc[ei - 1]                                       # last known price at decision
    side = np.where(gap >= g * at, -1, np.where(gap <= -g * at, 1, 0))
    # gap must still be open at decision time (price still beyond Friday close)
    side = np.where((side < 0) & (px > fri), side, np.where((side > 0) & (px < fri), side, 0))
    if sides == "long":
        side = np.where(side > 0, side, 0)
    elif sides == "short":
        side = np.where(side < 0, side, 0)
    keep = ok & (side != 0)
    xi = gl.entry_index(m1, idx[ei] + pd.Timedelta(hours=hold_h))
    o = pd.DataFrame({"entry_i": ei, "side": side, "stop": np.nan, "stop_dist": stop_atr * at,
                      "target": fri, "exit_i": np.minimum(xi, N - 1), "tag": "gap"})[keep]
    return o.sort_values("entry_i").reset_index(drop=True)


def _soup_orders(m1, n=20, min_age=4, mode="close_inside", stop_buf=0.25, max_bars=3, atr_n=14,
                 sides="both", delay_min=None, hold_cap_h=166.0, tf="D", target_r=None):
    """Failed-breakout fade of the prior n-day extreme (Connors-Raschke 'Turtle Soup').
    close_inside: today's low pierced the prior n-day low (set >= min_age days ago) but the day
                  CLOSED back above it -> buy next session; stop below today's low.
    stop_entry  : today broke and closed below the old low -> next trading day place a buy-stop at
                  the old low (re-entry inside the range); stop below today's low.  Shorts mirror."""
    b = gl.bars(m1, tf)
    if delay_min is None:
        delay_min = 120 if tf == "D" else 0
    h, l, c = b["h"], b["l"], b["c"]
    a = gl.atr(b, atr_n).to_numpy()
    plo = l.rolling(n, min_periods=n).min().shift(1).to_numpy()
    phi = h.rolling(n, min_periods=n).max().shift(1).to_numpy()
    # age (in bars) of the prior extreme, measured from today
    age_lo = (n - l.rolling(n, min_periods=n).apply(np.argmin, raw=True)).shift(1).to_numpy()
    age_hi = (n - h.rolling(n, min_periods=n).apply(np.argmax, raw=True)).shift(1).to_numpy()
    hv, lv_, cv = h.to_numpy(), l.to_numpy(), c.to_numpy()
    if mode == "close_inside":
        lg = (lv_ < plo) & (cv > plo) & (age_lo >= min_age)
        sh = (hv > phi) & (cv < phi) & (age_hi >= min_age)
    else:
        lg = (lv_ < plo) & (cv < plo) & (age_lo >= min_age)
        sh = (hv > phi) & (cv > phi) & (age_hi >= min_age)
    lg &= sides in ("both", "long")
    sh &= sides in ("both", "short")
    jl, js = np.flatnonzero(lg), np.flatnonzero(sh)
    j = np.r_[jl, js]
    side = np.r_[np.ones(len(jl), int), -np.ones(len(js), int)]
    stop = np.where(side > 0, lv_[j] - stop_buf * a[j], hv[j] + stop_buf * a[j])
    o = _bar_orders(m1, b, j, side, np.abs(cv[j] - stop), j + max_bars, delay_min=delay_min,
                    hold_cap_h=hold_cap_h, tag="soup")
    if len(o) == 0:
        return o
    # rebuild absolute stops / pending levels aligned with the kept rows
    key = pd.DataFrame({"j": j, "side": side, "stop": stop,
                        "lvl": np.where(side > 0, plo[j], phi[j])})
    tc = pd.DatetimeIndex(b["t_close"].to_numpy())
    ei, ok = _exec_index(m1, tc[j], delay_min, 10)
    key["entry_i"] = ei
    key = key[ok & np.isfinite(np.abs(cv[j] - stop)) & (np.abs(cv[j] - stop) > 0)]
    key = key.sort_values("entry_i", kind="stable").reset_index(drop=True)
    o["stop"] = key["stop"].to_numpy()
    o["stop_dist"] = np.nan
    if target_r:
        # target at target_r x the initial risk measured from the signal close
        cj = cv[key["j"].to_numpy()]
        o["target"] = cj + o["side"].to_numpy() * target_r * np.abs(cj - o["stop"].to_numpy())
    if mode == "stop_entry":
        # pending buy/sell-stop valid until the end of the next trading day
        nxt_close = tc[np.minimum(key["j"].to_numpy() + 1, len(b) - 1)]
        o["etype"] = 1
        o["level"] = key["lvl"].to_numpy()
        o["expiry_i"] = gl.entry_index(m1, nxt_close) - 1
    # a stop on the wrong side of the (expected) entry is degenerate -> drop
    ref = o["level"] if mode == "stop_entry" else pd.Series(cv[key["j"].to_numpy()])
    bad = ((o.side > 0) & (o.stop >= ref.to_numpy())) | ((o.side < 0) & (o.stop <= ref.to_numpy()))
    return o[~bad.to_numpy()].reset_index(drop=True)


def _ret_orders(m1, n=5, k=2.0, vol_n=60, hold=5, stop_atr=3.0, atr_n=14, sides="both",
                delay_min=120, hold_cap_h=166.0):
    """Multi-day return extreme reversal: z = n-day log return / (rolling daily sd * sqrt(n))."""
    b = gl.bars(m1, "D")
    c = b["c"]
    lr = np.log(c).diff()
    sd = lr.rolling(vol_n, min_periods=vol_n).std()
    z = (np.log(c / c.shift(n)) / (sd * np.sqrt(n))).to_numpy()
    a = gl.atr(b, atr_n).to_numpy()
    lg, sh = z < -k, z > k
    lg &= sides in ("both", "long")
    sh &= sides in ("both", "short")
    jl, js = np.flatnonzero(lg), np.flatnonzero(sh)
    j = np.r_[jl, js]
    side = np.r_[np.ones(len(jl), int), -np.ones(len(js), int)]
    return _bar_orders(m1, b, j, side, stop_atr * a[j], j + hold, delay_min=delay_min,
                       hold_cap_h=hold_cap_h, tag="ret")


_FAMILIES = {"rsi": _rsi_orders, "bb": _bb_orders, "ibs": _ibs_orders, "sess": _sess_orders,
             "gap": _gap_orders, "soup": _soup_orders, "ret": _ret_orders}


def make_orders(m1, family="rsi", **params):
    """Build the order frame for one configuration on any M1 frame."""
    return _FAMILIES[family](m1, **params)


# Finalists chosen on IS only (see results/meanrev/report.md).  NOTE: no meanrev configuration
# met the pre-registered IS criteria; "A" is the best-effort candidate selected by the
# pre-declared rule "highest IS PF among frequency-feasible configs (IS n>=200, 25-750/yr)".
# It FAILS the IS criteria (PF 1.03, t 0.19, 5/9 years, neighbour median PF 1.00, stress PF 0.98)
# and must not be traded.  Live use: evaluate only right after the 17:00 New York daily close
# (the last D bar must be complete); execution is 120 min after the 18:00 NY reopen.
FINALISTS = {
    "meanrev-A-failedbreak-D5": dict(family="soup", tf="D", n=5, min_age=1, mode="close_inside",
                                     stop_buf=1.0, max_bars=3),
}
