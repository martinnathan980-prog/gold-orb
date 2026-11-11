"""Track `bounce`: FADING a touch of a pivot on gold (the user's "it bounces on the pivot" reading).

    make_orders(m1, **params) -> orders DataFrame for goldlab.simulate   (any M1 bid/ask frame of gold)
    touches(m1, **params)     -> one row per touch with its context (what make_orders filters on)
    FINALISTS = {name: params}

What the rule does
------------------
* Levels of trading day D (17:00 New York boundary): "Traditional" pivots P, R1-R3, S1-S3 from the high / low /
  close of the last FULL trading day before D (>= 600 M1 bars), on MID prices; weekly / monthly pivots from the
  previous week / month; yesterday's high / low. Daily ATR = 14-day mean true range up to that last full day.
* A TOUCH (same logic as pivbb/events.py): the level is armed from one side once an M1 close is at least
  `arm` x dATR away on that side; the first M1 bar whose mid high / low reaches the level is the touch.
  s = +1 when price came UP to the level (the fade is a SHORT), -1 when it came down (the fade is a LONG).
* Context of a touch = bars closed before the touch minute (15-min and 1-hour Bollinger (20, 2), RSI 14, ...).
* Entry: `limit` (resting order at the level; optimistic: fills on touch), `market` (open of the next minute),
  or `confirm` (wait for a 1/5/15-minute bar that closes back on the arrival side: see `pattern`; market at the
  open of the minute after that bar is complete).
* Stop: `stop_atr` x dATR beyond the level (beyond the extreme since the touch for market / confirm entries).
  Target: R multiple, the 15-minute middle band, or the previous daily pivot. Forced exit: `hold` minutes after
  the decision, at the latest `eod` minutes after 17:00 New York (default 23 h 50 = 16:50 New York).

Causality: every level / ATR of day D uses days strictly before D; indicators use bars whose end <= the touch
minute; a confirmation bar is used only when a later M1 bar proves it is complete. Nothing is fitted here.
Truncation test: pivbb/tracks/bounce/causality.py.
"""
import os
import sys

import numba as nb
import numpy as np
import pandas as pd

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
from goldlab.data import NY, exit_index, trading_day  # noqa: E402

D_LEVELS = ["S3", "S2", "S1", "P", "R1", "R2", "R3"]
W_LEVELS = ["S2", "S1", "P", "R1", "R2"]
M_LEVELS = ["S1", "P", "R1"]

DEFAULTS = dict(
    fam="D",              # levels traded: "D" daily pivots | "WM" weekly + monthly pivots | "ALL" = D + WM + yesterday's high / low
    levels=None,          # subset of names (e.g. ("D_S1", "D_R1")); None = the whole family
    arm=0.15,             # arming distance, x dATR
    entry="market",       # limit | market | confirm
    tf=5,                 # confirm: bar width in minutes (1, 5 or 15), clock grid
    pattern="close",      # confirm: close | wick | engulf | fail
    window=3,             # confirm: number of tf bars (the bar holding the touch = first) that may confirm
    rej=0.0,              # confirm: the confirming close is at least rej x dATR back on the arrival side of the level
    wick=0.5,             # pattern wick: rejection wick >= this share of the bar's range (and the bar reached the level)
    pen=0.05,             # pattern fail: an M1 close at least pen x dATR BEYOND the level must come first
    max_pen=0.25,         # confirm: give up once price is more than max_pen x dATR beyond the level
    in_band=False,        # confirm: the confirming close must also be inside the 15-min band (band as of the touch)
    stop_atr=0.25,        # stop distance beyond the level / the extreme since the touch, x dATR
    tgt=1.0,              # float = R multiple | "mid15" = 15-min middle band | "prev" = previous daily pivot | None
    min_rr=0.5,           # mid15 / prev targets: skip when the target is closer than min_rr x risk
    hold=None,            # time stop in minutes after the decision (None = end of day only)
    eod=1430,             # forced exit, minutes after 17:00 New York (1430 = 16:50 New York)
    t_min=65,             # no touch before this many minutes after 17:00 New York (reopen at 18:00: wide spread)
    t_gap=30,             # no touch in the last t_gap minutes before the forced exit
    # filters on the context of the touch: (lo, hi) = keep lo <= x < hi ; None = no filter
    nth=None,             # rank of the touch of this level today (0 = first)
    ny=None,              # New York hour window (lo, hi); lo > hi wraps over midnight, e.g. (18, 3)
    stretch15=None,       # where the level sits against the 15-min band on the arrival side (1 = on the band)
    stretch60=None,       # same against the 1-hour band
    rsi=None,             # RSI 14 (15 min) in the direction of arrival
    mom4=None,            # move of the last 4 closed 15-min bars in the direction of arrival, in 15-min ATR
    squeeze=None,         # 15-min band width / its median over the last 96 bars
    range_used=None,      # the day's range before the touch, x dATR
    walk=None,            # how many of the last 8 15-min closes were outside the band on the arrival side
    conf=None,            # confluence: "WM" | "PD" | "RN" | "any" (WM or PD)
    conf_dist=0.10,       # ... within this many dATR of the other level
    rn_grid=10.0,         # round-number grid ($)
    rn_dist=1.5,          # ... within this many $ of a grid multiple
    div=False,            # RSI divergence: a new extreme against the last 3 hours with a lower RSI than at the previous extreme
    roles="any",          # classic = R levels only from below, S levels only from above (P either way)
    side=0,               # 0 both | +1 longs only | -1 shorts only
    placebo=None,         # int seed: every level set shifted by +/- U(0.2, 0.4) x dATR (as in pivbb/events.py)
)

_CTX = {}


# ----------------------------------------------------------------------------------------------
# numba kernels
# ----------------------------------------------------------------------------------------------
@nb.njit(cache=True)
def _touch_all(h, l, c, first, last, lv, arm_d):
    """Touches of every level [day, level] (events.py logic). Returns bar, side, level column, rank."""
    nd, nl = lv.shape
    cap = 4096
    ti = np.empty(cap, np.int64)
    ts = np.empty(cap, np.int64)
    tj = np.empty(cap, np.int64)
    tq = np.empty(cap, np.int64)
    td = np.empty(cap, np.int64)
    n = 0
    for d in range(nd):
        arm = arm_d[d]
        if not (arm > 0):
            continue
        for j in range(nl):
            level = lv[d, j]
            if np.isnan(level):
                continue
            side = 0
            q = 0
            for i in range(first[d], last[d]):
                hit = 0
                if side == 1 and h[i] >= level:
                    hit = 1
                elif side == -1 and l[i] <= level:
                    hit = -1
                if hit != 0:
                    if n == cap:
                        cap *= 2
                        ti = np.concatenate((ti, np.empty(n, np.int64)))
                        ts = np.concatenate((ts, np.empty(n, np.int64)))
                        tj = np.concatenate((tj, np.empty(n, np.int64)))
                        tq = np.concatenate((tq, np.empty(n, np.int64)))
                        td = np.concatenate((td, np.empty(n, np.int64)))
                    ti[n], ts[n], tj[n], tq[n], td[n] = i, hit, j, q, d
                    n += 1
                    q += 1
                    side = 0
                else:
                    if c[i] <= level - arm:
                        side = 1
                    elif c[i] >= level + arm:
                        side = -1
    return ti[:n], ts[:n], tj[:n], tq[:n], td[:n]


@nb.njit(cache=True)
def _cum_range(h, l, first, last):
    hi = np.empty(len(h))
    lo = np.empty(len(h))
    for d in range(len(first)):
        a, b = -np.inf, np.inf
        for i in range(first[d], last[d]):
            if h[i] > a:
                a = h[i]
            if l[i] < b:
                b = l[i]
            hi[i], lo[i] = a, b
    return hi, lo


@nb.njit(cache=True)
def _confirm(o, h, l, c, tmin, ti, ts, lvl, atr, day_end, tf, window, pat, rej, wickf, pen, max_pen, in_band, band):
    """For each touch: the M1 index of the LAST minute of the confirming tf bar (-1 = none) and the extreme
    reached since the touch (highest high for s = +1, lowest low for s = -1), level included.
    pat: 0 close, 1 wick, 2 engulf, 3 fail. A bar is used only once a later M1 bar shows it is complete."""
    n = len(ti)
    dec = np.full(n, -1, np.int64)
    ext = np.empty(n)
    N = len(c)
    for k in range(n):
        i, s, L, A = ti[k], ts[k], lvl[k], atr[k]
        ext[k] = L
        key0 = tmin[i] // tf
        e = day_end[k]
        # the tf bar that holds the touch starts before the touch minute: rebuild it from its first minute
        j0 = i
        while j0 - 1 >= 0 and tmin[j0 - 1] // tf == key0:
            j0 -= 1
        bo, bh, bl = o[j0], -np.inf, np.inf
        for j in range(j0, i):
            if h[j] > bh:
                bh = h[j]
            if l[j] < bl:
                bl = l[j]
        key = key0
        b0h, b0l = np.nan, np.nan           # range of the bar that holds the touch (for engulf)
        x = L                                # extreme since the touch
        penetrated = False
        reached = True                       # the current bar reached the level (true for the touch bar)
        for j in range(i, e):
            kj = tmin[j] // tf
            if kj != key:                    # a new tf bar starts
                if kj - key0 >= window:
                    break
                key = kj
                bo, bh, bl = o[j], -np.inf, np.inf
                reached = False
            if h[j] > bh:
                bh = h[j]
            if l[j] < bl:
                bl = l[j]
            if s == 1:
                if h[j] > x:
                    x = h[j]
                if h[j] >= L:
                    reached = True
            else:
                if l[j] < x:
                    x = l[j]
                if l[j] <= L:
                    reached = True
            if s * (x - L) > max_pen * A:
                break
            if s * (c[j] - L) >= pen * A:
                penetrated = True
            if j + 1 >= N:
                break                        # cannot know that the bar is complete
            if tmin[j + 1] // tf == key:
                continue                     # bar not finished
            # bar [key] is complete with close c[j]
            if key == key0:
                b0h, b0l = bh, bl
            ok = s * (L - c[j]) >= rej * A
            if ok and in_band:
                ok = s * (band[k] - c[j]) > 0
            if ok and pat == 1:
                rng = bh - bl
                w = (bh - max(bo, c[j])) if s == 1 else (min(bo, c[j]) - bl)
                ok = reached and rng > 0 and w >= wickf * rng
            elif ok and pat == 2:
                ok = key != key0 and ((c[j] < b0l) if s == 1 else (c[j] > b0h))
            elif ok and pat == 3:
                ok = penetrated
            if ok:
                dec[k] = j
                break
        ext[k] = x
    return dec, ext


@nb.njit(cache=True)
def _divergence(bh, bl, rsi, k15, ts, lvl):
    """RSI divergence at the touch: the level is a new extreme against the 15-min bars k-12 .. k-2 and the RSI of
    the last closed bar is lower (higher for s = -1) than at that previous extreme, which was itself stretched."""
    out = np.zeros(len(k15), np.bool_)
    for q in range(len(k15)):
        k, s = k15[q], ts[q]
        if k < 14:
            continue
        j = k - 12
        for m in range(k - 12, k - 1):
            if (s == 1 and bh[m] > bh[j]) or (s == -1 and bl[m] < bl[j]):
                j = m
        if s == 1:
            out[q] = lvl[q] >= bh[j] and rsi[j] >= 60 and rsi[k] < rsi[j]
        else:
            out[q] = lvl[q] <= bl[j] and rsi[j] <= 40 and rsi[k] > rsi[j]
    return out


# ----------------------------------------------------------------------------------------------
# context (depends on MID prices only, so it is shared by the cost-stress and gross re-runs)
# ----------------------------------------------------------------------------------------------
def _rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    return 100.0 * up / np.maximum(up + dn, 1e-12)


def _pivots(h, l, c):
    p = (h + l + c) / 3.0
    return {"P": p, "R1": 2 * p - l, "S1": 2 * p - h, "R2": p + (h - l), "S2": p - (h - l),
            "R3": 2 * p + (h - 2 * l), "S3": 2 * p - (2 * h - l)}


def _bars(g, width):
    key = g["tmin"] // width
    first = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
    last = np.r_[first[1:], len(key)] - 1
    b = pd.DataFrame({"start": key[first] * width, "o": g["o"][first], "h": np.maximum.reduceat(g["h"], first),
                      "l": np.minimum.reduceat(g["l"], first), "c": g["c"][last]})
    b["end"] = b.start + width
    b["mid"] = b.c.rolling(20).mean()
    b["sd"] = b.c.rolling(20).std(ddof=0)
    pc = b.c.shift(1)
    b["atr"] = np.maximum(b.h - b.l, np.maximum((b.h - pc).abs(), (b.l - pc).abs())).rolling(14).mean()
    b["rsi"] = _rsi(b.c.to_numpy())
    b["bw_med"] = (4 * b.sd).rolling(96).median()
    b["out_up"] = (b.c > b.mid + 2 * b.sd).rolling(8).sum()
    b["out_dn"] = (b.c < b.mid - 2 * b.sd).rolling(8).sum()
    return {k: b[k].to_numpy() for k in b.columns}


def context(m1):
    mc = (m1["bc"].to_numpy(np.float64) + m1["ac"].to_numpy(np.float64)) / 2
    key = (len(m1), m1.index[0], m1.index[-1], float(mc.sum()), float(mc[::997].sum()))
    if key in _CTX:
        return _CTX[key]
    _CTX.clear()
    g = {"N": len(m1), "index": m1.index, "c": mc}
    for k, (b, a) in {"o": ("bo", "ao"), "h": ("bh", "ah"), "l": ("bl", "al")}.items():
        g[k] = (m1[b].to_numpy(np.float64) + m1[a].to_numpy(np.float64)) / 2
    g["tmin"] = (m1.index.as_unit("ms").asi8 // 60_000).astype(np.int64)
    ny = m1.index.tz_convert(NY)
    g["ny_min"] = (ny.hour * 60 + ny.minute).to_numpy().astype(np.int64)
    g["td_min"] = (g["ny_min"] + 420) % 1440                       # minutes after 17:00 New York
    td = trading_day(m1.index)
    day = td.asi8
    first = np.r_[0, np.flatnonzero(np.diff(day)) + 1]
    last = np.r_[first[1:], len(day)]
    g["first"], g["last"] = first.astype(np.int64), last.astype(np.int64)
    dates = pd.DatetimeIndex(td[first])
    D = pd.DataFrame({"o": g["o"][first], "h": np.maximum.reduceat(g["h"], first), "l": np.minimum.reduceat(g["l"], first),
                      "c": mc[last - 1], "n": last - first}, index=dates)
    D["full"] = D.n >= 600
    F = D[D.full]
    tr = np.maximum(F.h - F.l, np.maximum((F.h - F.c.shift(1)).abs(), (F.l - F.c.shift(1)).abs()))
    Fp = pd.DataFrame({"ph": F.h, "pl": F.l, "pc": F.c, "atr": tr.rolling(14).mean()})
    # what day D knows at its open: the last FULL day strictly before it (today's own bar count is never used)
    D = D.join(Fp.reindex(D.index).ffill().shift(1))
    for tag, freq in (("w", "W-FRI"), ("m", "M")):
        agg = F.groupby(F.index.to_period(freq)).agg(h=("h", "max"), l=("l", "min"), c=("c", "last"))
        pos = np.searchsorted(agg.index.asi8, D.index.to_period(freq).asi8, side="left") - 1   # last period strictly before
        for col in "hlc":
            D[tag + col] = np.where(pos >= 0, agg[col].to_numpy()[np.maximum(pos, 0)], np.nan)
    g["D"] = D
    g["day_start"] = pd.DatetimeIndex(D.index).tz_localize(NY) - pd.Timedelta(hours=7)        # 17:00 New York the evening before
    g["b15"], g["b60"] = _bars(g, 15), _bars(g, 60)
    g["cumhi"], g["cumlo"] = _cum_range(g["h"], g["l"], g["first"], g["last"])
    g["touch_cache"] = {}
    _CTX[key] = g
    return g


def level_sets(g, seed=None):
    """{name: per-day price}. seed = None: the real levels; else every set shifted by +/- U(0.2, 0.4) x dATR."""
    D = g["D"]
    # one random stream per set and per draw, so that the shifts of the first days do not depend on the frame's length
    sh = lambda q: 0.0 if seed is None else (np.random.default_rng([int(seed), q, 0]).uniform(0.2, 0.4, len(D))
                                             * np.random.default_rng([int(seed), q, 1]).choice([-1.0, 1.0], len(D)) * D.atr.to_numpy())
    out = {}
    d, s = _pivots(D.ph, D.pl, D.pc), sh(0)
    for k in D_LEVELS:
        out["D_" + k] = d[k].to_numpy() + s
    w, s = _pivots(D.wh, D.wl, D.wc), sh(1)
    for k in W_LEVELS:
        out["W_" + k] = w[k].to_numpy() + s
    m, s = _pivots(D.mh, D.ml, D.mc), sh(2)
    for k in M_LEVELS:
        out["M_" + k] = m[k].to_numpy() + s
    s = sh(3)
    out["PDH"], out["PDL"] = D.ph.to_numpy() + s, D.pl.to_numpy() + s
    return out


def _rng(x, r):
    return np.ones(len(x), bool) if r is None else (x >= r[0]) & (x < r[1])


def touches(m1, **params):
    """One row per touch of a traded level, with the context known just before the touch minute."""
    p = dict(DEFAULTS)
    p.update(params)
    g = context(m1)
    ck = (p["fam"], p["arm"], p["placebo"])
    if ck in g["touch_cache"]:
        return g["touch_cache"][ck]
    D = g["D"]
    L = level_sets(g, p["placebo"])
    names = {"D": [k for k in L if k.startswith("D_")], "WM": [k for k in L if k[0] in "WM"], "ALL": list(L)}[p["fam"]]
    lv = np.column_stack([L[k] for k in names])
    atr_d = D.atr.to_numpy()
    lv = np.where((np.isfinite(atr_d) & (atr_d > 0))[:, None], lv, np.nan)
    ti, ts, tj, tq, tdd = _touch_all(g["h"], g["l"], g["c"], g["first"], g["last"], np.ascontiguousarray(lv), p["arm"] * atr_d)
    o = np.lexsort((tj, ti))
    ti, ts, tj, tq, tdd = ti[o], ts[o], tj[o], tq[o], tdd[o]
    px, A = lv[tdd, tj], atr_d[tdd]
    b15, b60 = g["b15"], g["b60"]
    k = np.searchsorted(b15["end"], g["tmin"][ti], side="right") - 1
    k6 = np.searchsorted(b60["end"], g["tmin"][ti], side="right") - 1
    kk, kk6 = np.maximum(k, 16), np.maximum(k6, 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = pd.DataFrame({
            "i": ti, "s": ts, "level": np.array(names, dtype=object)[tj], "px": px, "atr_d": A, "d": tdd, "nth": tq,
            "k15": k,
            "stretch15": ts * (px - b15["mid"][kk]) / (2 * b15["sd"][kk]),
            "stretch60": ts * (px - b60["mid"][kk6]) / (2 * b60["sd"][kk6]),
            "squeeze": 4 * b15["sd"][kk] / b15["bw_med"][kk],
            "walk": np.where(ts == 1, b15["out_up"][kk], b15["out_dn"][kk]),
            "rsi": np.where(ts == 1, b15["rsi"][kk], 100 - b15["rsi"][kk]),
            "mom4": ts * (b15["c"][kk] - b15["c"][kk - 4]) / b15["atr"][kk],
            "mom16": ts * (b15["c"][kk] - b15["c"][kk - 16]) / b15["atr"][kk],
            "atr15_d": b15["atr"][kk] / A,
            "ny_hour": g["ny_min"][ti] / 60.0, "td_min": g["td_min"][ti],
            "range_used": np.where(ti > g["first"][tdd], (g["cumhi"][np.maximum(ti - 1, 0)] - g["cumlo"][np.maximum(ti - 1, 0)]) / A, 0.0),
            "from_open": ts * (px - g["o"][g["first"][tdd]]) / A,
            "mid15": b15["mid"][kk], "band": b15["mid"][kk] + ts * 2 * b15["sd"][kk],
        })
    ok = (k >= 120) & np.isfinite(b15["bw_med"][kk]) & (b15["sd"][kk] > 0) & (b15["atr"][kk] > 0)
    # confluence: distance to the nearest weekly / monthly pivot and to yesterday's high / low, in dATR
    wm = np.column_stack([L[n][tdd] for n in L if n[0] in "WM"])
    pd_ = np.column_stack([L["PDH"][tdd], L["PDL"][tdd]])
    with np.errstate(invalid="ignore"):
        t["d_wm"] = np.nanmin(np.where(np.isfinite(wm), np.abs(wm - px[:, None]), np.inf), axis=1) / A
        t["d_pd"] = np.nanmin(np.where(np.isfinite(pd_), np.abs(pd_ - px[:, None]), np.inf), axis=1) / A
    t["div"] = _divergence(b15["h"], b15["l"], b15["rsi"], kk.astype(np.int64), ts, px)
    # previous daily pivot (the one behind the touch), for the "prev" target
    dl = np.column_stack([L["D_" + n][tdd] for n in D_LEVELS])
    below = np.where(dl < (px - 1e-9)[:, None], dl, -np.inf).max(axis=1)
    above = np.where(dl > (px + 1e-9)[:, None], dl, np.inf).min(axis=1)
    t["prev"] = np.where(ts == 1, below, above)
    t = t[ok].reset_index(drop=True)
    g["touch_cache"][ck] = t
    return t


def make_orders(m1, **params):
    unknown = set(params) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown params {unknown}")
    p = dict(DEFAULTS)
    p.update(params)
    g = context(m1)
    t = touches(m1, **p)
    D = g["D"]
    # ---- filters on the context
    m = (t.td_min >= p["t_min"]) & (t.td_min < p["eod"] - p["t_gap"])
    if p["levels"] is not None:
        m &= t.level.isin(list(p["levels"]))
    for col in ("nth", "stretch15", "stretch60", "rsi", "mom4", "squeeze", "range_used", "walk"):
        m &= _rng(t[col].to_numpy(), p[col])
    if p["ny"] is not None:
        lo, hi = p["ny"]
        hnow = t.ny_hour.to_numpy()
        m &= ((hnow >= lo) & (hnow < hi)) if lo <= hi else ((hnow >= lo) | (hnow < hi))
    if p["conf"] is not None:
        rn = np.abs(t.px - np.round(t.px / p["rn_grid"]) * p["rn_grid"]) <= p["rn_dist"]
        wm, pdl = t.d_wm <= p["conf_dist"], t.d_pd <= p["conf_dist"]
        m &= {"WM": wm, "PD": pdl, "RN": rn, "any": wm | pdl}[p["conf"]]
    if p["div"]:
        m &= t["div"]
    if p["roles"] == "classic":
        kind = t.level.str[2]
        m &= ~((kind == "R") & (t.s != 1)) & ~((kind == "S") & (t.s != -1))
    if p["side"]:
        m &= (-t.s) == p["side"]
    t = t[m.to_numpy()].reset_index(drop=True)
    cols = ["entry_i", "side", "etype", "level", "expiry_i", "stop", "target", "exit_i", "lvl", "s", "nth", "atr_d", "touch_i", "dec_i", "risk_ref"]
    if len(t) == 0:
        return pd.DataFrame(columns=cols)
    ti, s, L, A = t.i.to_numpy(np.int64), t.s.to_numpy(np.int64), t.px.to_numpy(), t.atr_d.to_numpy()
    day_end = g["last"][t.d.to_numpy()]
    h, l, c, tmin = g["h"], g["l"], g["c"], g["tmin"]
    # ---- entry
    if p["entry"] == "limit":
        dec, ext = ti.copy(), L.copy()
        entry_i, etype, level, ref = ti.copy(), np.full(len(t), 2), L.copy(), L.copy()
    elif p["entry"] == "market":
        dec = ti.copy()
        ext = np.where(s == 1, np.maximum(L, h[ti]), np.minimum(L, l[ti]))
        entry_i, etype, level, ref = ti + 1, np.zeros(len(t), np.int64), np.full(len(t), np.nan), c[ti]
    elif p["entry"] == "confirm":
        pat = {"close": 0, "wick": 1, "engulf": 2, "fail": 3}[p["pattern"]]
        dec, ext = _confirm(g["o"], h, l, c, tmin, ti, s, L, A, day_end.astype(np.int64), int(p["tf"]), int(p["window"]), pat,
                            float(p["rej"]), float(p["wick"]), float(p["pen"]), float(p["max_pen"]), bool(p["in_band"]),
                            t.band.to_numpy())
        entry_i, etype, level = dec + 1, np.zeros(len(t), np.int64), np.full(len(t), np.nan)
        ref = c[np.maximum(dec, 0)]
    else:
        raise ValueError(p["entry"])
    ok = (dec >= 0) & (entry_i < day_end) & (entry_i < g["N"])
    ei = np.minimum(entry_i, g["N"] - 1)
    ok &= (tmin[ei] - tmin[np.maximum(dec, 0)]) <= 10              # no entry after a hole in the data
    stop = ext + s * p["stop_atr"] * A
    risk = s * (stop - ref)
    ok &= risk > 0.02 * A
    # ---- target
    if p["tgt"] is None:
        target = np.full(len(t), np.nan)
    elif p["tgt"] == "mid15":
        kd = np.maximum(np.searchsorted(g["b15"]["end"], tmin[np.maximum(dec, 0)] + 1, side="right") - 1, 0)
        target = g["b15"]["mid"][kd] if p["entry"] != "limit" else t.mid15.to_numpy()
        ok &= s * (ref - target) >= p["min_rr"] * risk
    elif p["tgt"] == "prev":
        target = t.prev.to_numpy()
        ok &= np.isfinite(target) & (s * (ref - target) >= p["min_rr"] * risk)
    else:
        target = ref - s * float(p["tgt"]) * risk
    # ---- forced exit
    start = g["day_start"][t.d.to_numpy()]
    x_time = start + pd.Timedelta(minutes=int(p["eod"]))
    exit_i = exit_index(m1, x_time)
    if p["hold"] is not None:
        xt = g["index"][np.maximum(dec, 0)] + pd.Timedelta(minutes=int(p["hold"]) + 1)
        exit_i = np.minimum(exit_i, exit_index(m1, xt))
    ok &= entry_i < exit_i
    o = pd.DataFrame({"entry_i": entry_i, "side": -s, "etype": etype, "level": level,
                      "expiry_i": np.where(etype > 0, ti + 5, -1), "stop": stop, "target": target, "exit_i": exit_i,
                      "lvl": t.level.to_numpy(), "s": s, "nth": t.nth.to_numpy(), "atr_d": A, "touch_i": ti, "dec_i": dec,
                      "risk_ref": risk})[ok]
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


# 64 configurations (results/pivbb/bounce/trials.jsonl): none met the in-sample criteria of PROTOCOL_PIVBB -> no finalist.
# The best one, kept here for the record only (NOT a finalist: t = 1.82 < 2.5, as good on shifted lines, PF 1.03 on all lines):
BEST_NOT_FINALIST = {"I3_range_used_1.5": {"range_used": (1.5, 99)}}
FINALISTS = {}
