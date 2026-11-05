"""crossasset track: order generators (causal, usable on any M1 data incl. 2026 holdout / live).

    make_orders(m1, others=None, **params) -> orders DataFrame for goldlab.simulate

  m1      M1 frame (bid/ask) of the TRADED symbol (params['sym'], default xauusd)
  others  dict {symbol: M1 frame} of predictor markets, only for cross-asset rules
          (e.g. {'usdjpy': m1_usdjpy}).  Research code may instead pass cache={(sym, tf): bars}
          with pre-resampled gl.bars() frames (identical results, checked).
  params  'rule' selects the generator, the rest are its parameters (see each function).
  FINALISTS is empty (nothing passed IS); REFERENCE + regenerate() rebuild the near-misses.

Conventions (see lab/README.md): bars are labelled by START and known at t_close; every decision
uses closed bars only and enters at gl.entry_index(m1, decision_time).  Predictor bars are aligned
on the same bar interval (start label) and the decision time is the NOMINAL end of the interval,
which is >= the close of both the gold bar and the predictor bar (no same-bar leakage).
Every order has a stop and a forced exit (exit_i) within 5 trading days.
"""
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab.data import trading_day  # noqa: E402


# ----------------------------------------------------------------------------- helpers
def add_trading_days(ts, n):
    """Same wall-clock time n (<= 5) trading days later (skips the weekend)."""
    ts = pd.DatetimeIndex(ts)
    dow = trading_day(ts).dayofweek.to_numpy()
    extra = ((dow + n) // 5) * 2
    return ts + pd.to_timedelta(n + extra, unit="D")


def wilder_rsi(c, n):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1.0 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1.0 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(dn.notna())


def exit_index(m1, times, tol_min=60):
    """M1 index for a forced exit at `times`: the first bar at/after the time, unless the market is
    closed then (next bar more than tol_min later, e.g. holiday / data gap) -> the last bar before
    the closure.  Keeps the holding time <= the planned one (5 trading days rule)."""
    t = pd.DatetimeIndex(times)
    i = gl.entry_index(m1, t)
    idx = m1.index.values
    n = len(idx)
    late = (i >= n) | (idx[np.minimum(i, n - 1)] - t.values > np.timedelta64(tol_min, "m"))
    return np.where(late, i - 1, i).astype(np.int64)


def _orders(m1, dec_times, side, stop_dist, exit_times, **extra):
    o = pd.DataFrame({
        "entry_i": gl.entry_index(m1, dec_times),
        "side": np.asarray(side, dtype=np.int64),
        "stop_dist": np.asarray(stop_dist, dtype=float),
        "exit_i": exit_index(m1, exit_times),
    })
    for k, v in extra.items():
        o[k] = np.asarray(v) if not np.isscalar(v) else v
    o = o[(o.entry_i < len(m1)) & (o.exit_i > o.entry_i) & np.isfinite(o.stop_dist) & (o.stop_dist > 0)]
    return o.reset_index(drop=True)


# ----------------------------------------------------------------------------- Part B generic rules
def orb_orders(m1, tz=gl.LDN, start_min=8 * 60, range_min=60, expiry_min=16 * 60, exit_min=20 * 60,
               min_cover=0.5, **_):
    """Opening-range breakout. Range = M1 mid high/low over [start, start+range) local time.
    At the end of the range an OCO pair (buy-stop at range high, sell-stop at range low) is active
    until `expiry_min` local; the first level touched is taken (if both inside the same minute the
    buy is taken and the simulator stops it out on that bar = pessimistic).  Stop = opposite side
    of the range.  Forced exit at `exit_min` local the same day."""
    lt = gl.local(m1.index, tz)
    day = (lt.year * 10000 + lt.month * 100 + lt.day).to_numpy()
    tod = (lt.hour * 60 + lt.minute).to_numpy()
    wd = lt.dayofweek.to_numpy()
    mh = ((m1.bh + m1.ah) / 2).to_numpy()
    ml = ((m1.bl + m1.al) / 2).to_numpy()
    ah, bl = m1.ah.to_numpy(), m1.bl.to_numpy()
    # day boundaries
    brk = np.flatnonzero(np.diff(day)) + 1
    starts = np.r_[0, brk]
    ends = np.r_[brk, len(day)]
    rows = []
    for a, b in zip(starts, ends):
        if wd[a] >= 5:
            continue
        t = tod[a:b]
        r = np.flatnonzero((t >= start_min) & (t < start_min + range_min))
        if len(r) < min_cover * range_min:
            continue
        hi = mh[a + r].max()
        lo = ml[a + r].min()
        if not hi > lo:
            continue
        w = np.flatnonzero((t >= start_min + range_min) & (t < expiry_min))
        if len(w) == 0:
            continue
        wi = a + w
        tb = np.flatnonzero(ah[wi] >= hi)
        ts_ = np.flatnonzero(bl[wi] <= lo)
        ib = wi[tb[0]] if len(tb) else -1
        is_ = wi[ts_[0]] if len(ts_) else -1
        if ib < 0 and is_ < 0:
            continue
        if ib >= 0 and (is_ < 0 or ib <= is_):
            side, i0, lvl, st = 1, ib, hi, lo
        else:
            side, i0, lvl, st = -1, is_, lo, hi
        x = np.flatnonzero(t >= exit_min)
        if len(x) and t[x[0]] <= exit_min + 30:
            xi = a + x[0]                  # first bar at/after the exit time
        else:                              # early close (holiday): last bar before the gap
            xi = a + (x[0] - 1 if len(x) else len(t) - 1)
        if xi <= i0:
            continue
        rows.append((i0, side, lvl, st, xi, hi - lo))
    o = pd.DataFrame(rows, columns=["entry_i", "side", "level", "stop", "exit_i", "range"])
    o["etype"] = 1
    o["expiry_i"] = o["entry_i"]
    return o


def channel_orders(m1, rule_tf="4h", n=20, atr_n=14, stop_atr=2.0, trail_atr=2.0, max_days=5, bars=None, **_):
    """Donchian breakout: close above the highest high of the previous n bars -> long (below the
    lowest low -> short), market entry after the bar close, initial stop and trailing stop in
    ATR(atr_n) of the same timeframe, forced exit after max_days trading days."""
    b = bars if bars is not None else gl.bars(m1, rule_tf)
    hh = b.h.rolling(n).max().shift(1)
    ll = b.l.rolling(n).min().shift(1)
    a = gl.atr(b, atr_n)
    side = np.where(b.c > hh, 1, np.where(b.c < ll, -1, 0))
    m = (side != 0) & a.notna().to_numpy()
    s = b[m]
    o = _orders(m1, s.t_close, side[m], stop_atr * a[m].to_numpy(),
                add_trading_days(s.t_close, max_days), trail=trail_atr * a[m].to_numpy())
    return o


def rsi2_orders(m1, rsi_n=2, lo=10.0, hi=90.0, sma_n=5, atr_n=14, stop_atr=2.0, max_days=5, bars=None, **_):
    """Daily RSI(2) fade: RSI < lo -> long, RSI > hi -> short at the next bar after the daily close
    (17:00 NY).  Exit after the first daily close beyond the SMA(sma_n) (long: close > SMA), or
    after max_days trading days; protective stop stop_atr x ATR(atr_n, daily)."""
    d = bars if bars is not None else gl.bars(m1, "D")
    r = wilder_rsi(d.c, rsi_n)
    sma = d.c.rolling(sma_n).mean()
    a = gl.atr(d, atr_n)
    side = np.where(r < lo, 1, np.where(r > hi, -1, 0))
    tc = d.t_close.to_numpy()
    c, sm = d.c.to_numpy(), sma.to_numpy()
    rows = []
    for i in np.flatnonzero((side != 0) & a.notna().to_numpy() & sma.notna().to_numpy()):
        s = side[i]
        j_exit = None
        for j in range(i + 1, min(i + max_days, len(d) - 1) + 1):
            if (s > 0 and c[j] > sm[j]) or (s < 0 and c[j] < sm[j]):
                j_exit = j
                break
        if j_exit is None:
            j_exit = i + max_days
        cap = add_trading_days([tc[i]], max_days)[0]
        x_time = min(tc[j_exit], cap) if j_exit < len(d) else cap
        rows.append((tc[i], s, stop_atr * a.iloc[i], x_time))
    if not rows:
        return pd.DataFrame(columns=["entry_i", "side", "stop_dist", "exit_i"])
    t0, sd, st, xt = zip(*rows)
    return _orders(m1, pd.DatetimeIndex(t0), sd, st, pd.DatetimeIndex(xt))


# ----------------------------------------------------------------------------- Part A cross-asset
TF_MIN = {"5min": 5, "15min": 15, "1h": 60, "4h": 240}
USD = ["eurusd", "gbpusd", "usdjpy"]


def _get_bars(sym, tf, m1, others, cache):
    """Bars of `sym` at `tf`: from the research cache if given, else resampled from M1."""
    if cache is not None and (sym, tf) in cache:
        return cache[(sym, tf)]
    src = m1 if sym == "xauusd" and not (others and "xauusd" in others) else others[sym]
    b = gl.bars(src, tf)
    if cache is not None:
        cache[(sym, tf)] = b
    return b


def xpanel(m1, others, tf, preds, cache=None):
    """Aligned log returns (bp) on the gold bar grid (bar START labels).  A return at label t is
    defined only if gold has bars at t and t-tf (consecutive) and the predictor has bars at the same
    two labels.  `dec` = nominal end of the interval = decision time; at `dec` the gold bar AND the
    predictor bar of the same interval are both closed (their t_close <= dec): no leakage."""
    g = _get_bars("xauusd", tf, m1, others, cache)
    step = pd.Timedelta(minutes=TF_MIN[tf])
    lab = g.index
    contig = np.r_[False, (lab[1:] - lab[:-1]) == step]
    P = pd.DataFrame(index=lab)
    P["close"] = g["c"]
    P["g"] = np.where(contig, np.log(g["c"]).diff().to_numpy() * 1e4, np.nan)
    for s in preds:
        lp = np.log(_get_bars(s, tf, m1, others, cache)["c"]).reindex(lab)
        P[s] = np.where(contig, lp.diff().to_numpy() * 1e4, np.nan)
    if all(s in preds for s in USD):
        P["u"] = (P["eurusd"] + P["gbpusd"] - P["usdjpy"]) / 3   # > 0 = weaker dollar
    P["dec"] = lab + step
    return P


def roll_beta(y, x, win):
    """Rolling OLS slope of y on x over `win` bars (jointly valid obs only). NOT shifted."""
    v = y.notna() & x.notna()
    y, x = y.where(v), x.where(v)
    mp = win // 2
    mx, my = x.rolling(win, min_periods=mp).mean(), y.rolling(win, min_periods=mp).mean()
    cov = (x * y).rolling(win, min_periods=mp).mean() - mx * my
    var = (x * x).rolling(win, min_periods=mp).mean() - mx * mx
    return cov / var


def _sd(x, win):
    return x.rolling(win, min_periods=win // 2).std().shift(1)


def leadlag_orders(m1, others=None, tf="5min", k_sigma=3.0, max_cover=0.5, hold_min=60, win=5760,
                   stop_k=1.5, min_beta=0.2, cache=None, **_):
    """A1 'dollar shock not yet in gold': the USD basket moved > k_sigma rolling sd in the last bar
    and gold covered < max_cover of the beta-implied move -> trade gold toward the implied move,
    exit after hold_min, stop = stop_k x gold sd over the holding horizon (past-only estimates)."""
    P = xpanel(m1, others, tf, USD, cache)
    g, u = P.g, P.u
    v = g.notna() & u.notna()
    beta = roll_beta(g, u, win).shift(1)
    su, sg = _sd(u.where(v), win), _sd(g.where(v), win)
    m = beta * u
    cover = g / m
    sig = (v & (u.abs() > k_sigma * su) & (beta > min_beta) & (cover < max_cover)).to_numpy()
    S = P[sig]
    nb = hold_min / TF_MIN[tf]
    stop = stop_k * sg[sig] * np.sqrt(nb) * 1e-4 * S.close
    return _orders(m1, S.dec, np.sign(m[sig]).astype(int), stop.to_numpy(),
                   S.dec + pd.Timedelta(minutes=hold_min))


def diverge_orders(m1, others=None, tf="1h", n=24, z_in=2.0, win=1380, hold_days=1, hold_h=None,
                   stop_k=1.5, direction=-1, at_hour=None, tz=gl.LDN, component="res", trail_k=None,
                   cache=None, **_):
    """A2 divergence vs the rolling-beta USD basket: z = cumulative gold residual (gold - beta*u)
    over the last n bars / (sd_res*sqrt(n)).  direction=-1: trade gold back toward the basket-implied
    path (long when gold lagged, z < -z_in); +1 = residual momentum (trade WITH gold's
    idiosyncratic move).  at_hour: only decide at that local hour (e.g. 8 = London open, residual of
    the Asian session), else on threshold crossings.  component='gold' uses the raw gold return
    instead of the residual (control without cross-asset information).  trail_k: optional trailing
    stop, in the same sd-over-horizon units as stop_k."""
    P = xpanel(m1, others, tf, USD, cache)
    g, u = P.g, P.u
    v = g.notna() & u.notna()
    beta = roll_beta(g, u, win).shift(1)
    res = (g - beta * u).where(v) if component == "res" else g.where(v)
    z = res.rolling(n, min_periods=int(0.8 * n)).sum() / (_sd(res, win) * np.sqrt(n))
    if at_hour is None:
        lo = (z < -z_in) & (z.shift(1) >= -z_in)
        hi = (z > z_in) & (z.shift(1) <= z_in)
    else:
        lt = gl.local(P.dec, tz)
        at = pd.Series((lt.hour == at_hour) & (lt.minute == 0), index=P.index)
        lo, hi = at & (z < -z_in), at & (z > z_in)
    side = np.where(lo, -direction, np.where(hi, direction, 0))
    m = side != 0
    S = P[m]
    hh = hold_h if hold_h is not None else 24 * hold_days
    unit = (_sd(g.where(v), win)[m] * np.sqrt(hh * 60 / TF_MIN[tf]) * 1e-4 * S.close).to_numpy()
    xt = S.dec + pd.Timedelta(hours=hold_h) if hold_h is not None else add_trading_days(S.dec, hold_days)
    extra = {"trail": trail_k * unit} if trail_k else {}
    return _orders(m1, S.dec, side[m], stop_k * unit, xt, **extra)


def yen_orders(m1, others=None, tf="1h", z_in=2.5, win=480, hold_h=8, stop_k=1.5, start_hours=None,
               tz=gl.LDN, cache=None, **_):
    """A3a yen shock (risk-off / risk-on proxy): USDJPY moved < -z_in rolling sd in the last bar
    (yen bid) -> long gold; > +z_in -> short gold.  Exit after hold_h, stop stop_k x gold sd over
    the horizon.  start_hours: optional set of local (London) START hours of the signal bar."""
    P = xpanel(m1, others, tf, ["usdjpy"], cache)
    g, j = P.g, P.usdjpy
    z = j / _sd(j, win)
    side = np.where(z < -z_in, 1, np.where(z > z_in, -1, 0))
    if start_hours is not None:
        side = np.where(np.isin(gl.local(P.index, tz).hour, list(start_hours)), side, 0)
    m = side != 0
    S = P[m]
    stop = stop_k * _sd(g, win)[m] * np.sqrt(hold_h * 60 / TF_MIN[tf]) * 1e-4 * S.close
    return _orders(m1, S.dec, side[m], stop.to_numpy(), S.dec + pd.Timedelta(hours=hold_h))


def _session_ret(b, open_min, close_min, tz):
    """log return (bp) from the open of the first 5-min bar at open_min to the close of the last
    5-min bar ending by close_min (local time), per local date."""
    lt = gl.local(b.index, tz)
    tod = lt.hour * 60 + lt.minute
    date = pd.Index(lt.tz_localize(None).normalize())
    o = b.o[(tod >= open_min) & (tod < open_min + 30)].groupby(date[(tod >= open_min) & (tod < open_min + 30)]).first()
    mc = (tod + 5 <= close_min) & (tod >= close_min - 60)
    c = b.c[mc].groupby(date[mc]).last()
    return (np.log(c / o) * 1e4).dropna()


def riskoff_orders(m1, others=None, open_min=480, close_min=990, z_in=1.5, win=60, mode="giveback",
                   hold_days=3, exit_min=1260, stop_k=1.0, jpy_confirm=True, tz=gl.LDN, cache=None, **_):
    """A3b risk-off / risk-on European session: DAX return from the 08:00 London open to the 16:30
    London cash close, z-scored by its rolling sd over `win` past sessions; risk-off = z < -z_in
    (and USDJPY down over the same window if jpy_confirm), risk-on = z > z_in (USDJPY up).
    mode 'follow': long gold on risk-off (safe-haven continuation), exit exit_min London same day.
    mode 'giveback': short gold on risk-off / long on risk-on, exit after hold_days trading days.
    Stop = stop_k x gold ATR(14, daily) of the last completed trading day."""
    rd = _session_ret(_get_bars("deuidxeur", "5min", m1, others, cache), open_min, close_min, tz)
    rj = _session_ret(_get_bars("usdjpy", "5min", m1, others, cache), open_min, close_min, tz)
    z = rd / rd.rolling(win, min_periods=win // 2).std().shift(1)
    rj = rj.reindex(z.index)
    off = (z < -z_in) & ((rj < 0) | (not jpy_confirm))
    on = (z > z_in) & ((rj > 0) | (not jpy_confirm))
    sgn = 1 if mode == "follow" else -1
    side = np.where(off, sgn, np.where(on, -sgn, 0))
    m = side != 0
    days = z.index[m]
    dec = (days + pd.Timedelta(minutes=close_min)).tz_localize(tz).tz_convert("UTC")
    gd = _get_bars("xauusd", "D", m1, others, cache)
    a = gl.atr(gd, 14)
    known = pd.DataFrame({"t": pd.DatetimeIndex(gd.t_close), "atr": a.to_numpy()}).sort_values("t")
    st = pd.merge_asof(pd.DataFrame({"t": dec}), known, on="t", direction="backward")["atr"].to_numpy()
    if mode == "follow":
        xt = (days + pd.Timedelta(minutes=exit_min)).tz_localize(tz).tz_convert("UTC")
    else:
        xt = add_trading_days(dec, hold_days)
    return _orders(m1, dec, side[m], stop_k * st, xt)


def channel_usd_orders(m1, others=None, n=20, usd_n=20, mode="confirm", atr_n=14, stop_atr=2.0,
                       trail_atr=2.0, max_days=5, cache=None, **_):
    """A4 gold H4 Donchian breakout (as channel_orders) filtered by the USD basket trend: sum of the
    basket returns over the last usd_n H4 bars.  confirm: gold longs only while the dollar weakens
    (sum > 0), shorts only while it strengthens; contra: the opposite (gold-specific breakouts)."""
    P = xpanel(m1, others, "4h", USD, cache)
    b = _get_bars("xauusd", "4h", m1, others, cache)
    hh = b.h.rolling(n).max().shift(1)
    ll = b.l.rolling(n).min().shift(1)
    a = gl.atr(b, atr_n)
    side = np.where(b.c > hh, 1, np.where(b.c < ll, -1, 0))
    um = P.u.rolling(usd_n, min_periods=int(0.8 * usd_n)).sum().to_numpy()
    agree = np.sign(um) == side
    keep = agree if mode == "confirm" else (~agree & np.isfinite(um) & (um != 0))
    m = (side != 0) & keep & a.notna().to_numpy()
    S = P[m]
    return _orders(m1, S.dec, side[m], stop_atr * a[m].to_numpy(), add_trading_days(S.dec, max_days),
                   trail=trail_atr * a[m].to_numpy())


for _f in (leadlag_orders, diverge_orders, yen_orders, riskoff_orders, channel_usd_orders):
    _f.needs_others = True

RULES = {"orb": orb_orders, "channel": channel_orders, "rsi2": rsi2_orders,
         "leadlag": leadlag_orders, "diverge": diverge_orders, "yen": yen_orders,
         "riskoff": riskoff_orders, "channel_usd": channel_usd_orders}


def make_orders(m1, others=None, rule="channel", **params):
    """m1 = M1 frame of the traded symbol; others = {sym: M1 frame} for cross-asset rules."""
    params.pop("sym", None)
    f = RULES[rule]
    if getattr(f, "needs_others", False):
        return f(m1, others, **params)
    return f(m1, **params)


# No configuration of this track passed the pre-registered IS criteria (see
# results/crossasset/report.md), so there is no finalist and VAL was not accessed.
FINALISTS = {}

# Best near-misses / reference rules, kept so they can be regenerated on any data (2026, live).
# NOT validated, NOT recommended for trading.  'sym' = traded symbol, 'others' = predictor M1 frames
# make_orders() needs:  orders = make_orders(m1[sym], {s: m1[s] for s in others}, **params)
REFERENCE = {
    "yen_shock_ldn_morning": dict(sym="xauusd", others=["usdjpy"], rule="yen", tf="1h", z_in=2.5, win=480,
                                  hold_h=8, stop_k=1.5, start_hours=[7, 8, 9, 10, 11, 12]),
    "riskoff_giveback": dict(sym="xauusd", others=["deuidxeur", "usdjpy"], rule="riskoff", z_in=1.0, win=60,
                             mode="giveback", hold_days=3, stop_k=1.0),
    "h4_breakout_usd_confirm": dict(sym="xauusd", others=["eurusd", "gbpusd", "usdjpy"], rule="channel_usd",
                                    n=20, usd_n=20, mode="confirm"),
    "orb_london_dax": dict(sym="deuidxeur", others=[], rule="orb", start_min=480, range_min=60,
                           expiry_min=960, exit_min=1200),
}


def regenerate(name, m1_by_sym):
    """Orders of a FINALISTS / REFERENCE entry from a dict {symbol: M1 frame}.
    Returns (sym, orders); simulate with gl.simulate(m1_by_sym[sym], orders, sym=sym)."""
    p = dict(FINALISTS.get(name) or REFERENCE[name])
    sym, others = p.pop("sym"), p.pop("others", [])
    return sym, make_orders(m1_by_sym[sym], {s: m1_by_sym[s] for s in others}, **p)
