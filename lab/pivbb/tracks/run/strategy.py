"""Track 'run' of the pivot + Bollinger study: "the pivot breaks and price runs to the next pivot".

    make_orders(m1, **params) -> orders DataFrame for goldlab.simulate / r2.evaluate
    FINALISTS = {name: params}

What the rule sees (all on MID prices of the frame it receives, so the cost-stress re-run gives the same signals)
-----------------------------------------------------------------------------------------------------------------
* Trading day = 17:00 New York to 17:00 New York. Levels of day D come from the last FULL trading day before D
  (>= 600 M1 bars): "Traditional" daily pivots P, R1-R3, S1-S3, yesterday's high / low (PDH / PDL); weekly pivots
  from the previous week. dATR = 14-day mean true range of full days up to the day before. Whether TODAY will be
  a full day is never used.
* 15-minute bars on the clock grid, Bollinger (20, 2) on their closes; a bar is known at its end.
* Signals:
    entry="close15": a 15-minute bar closes beyond the level while the previous 15-minute close was on the other
                     side. Entry at the open of the first M1 bar after the bar's end (market).
    entry="touch"  : first M1 touch of the level after price has closed >= 0.15 dATR away from it (same arming as
                     pivbb/events.py). fill="pending": stop order resting at the level; fill="market": market on
                     the next minute.
    entry="retest" : after a close15 break, price comes back to the broken level within `retest_min` minutes.
                     fill="pending": limit order at the level (fills on touch: optimistic); fill="market": market
                     on the minute after the touch.
* Bollinger conditions (state BEFORE the break): `sq_max` / `sq_min` = band width / its 24-hour median at the last
  bar closed before the breaking bar; `walk_min` = closes outside the band in the direction of the break among the
  last 8 closed bars; `bbout` = the breaking bar closes outside the band (touch: the level lies beyond the band).
* Stop: "level" = stop_atr x dATR behind the broken level; "mid" = stop_atr x dATR behind the 15-minute middle band.
* Exit: target at the next daily pivot beyond the level ("next"), an R multiple (float) or none; optional
  `trail_mid` = exit on the first 15-minute close back across the middle band; forced exit at `eod` (New York
  minute of the trading day, `hold_days` later if > 0).

Every quantity of an order is known at its entry minute; exit_i of a `trail_mid` order is the minute at which the
(causal) exit condition is first true, pre-resolved here because the engine has no indicator-based exit.
"""
import os
import sys

import numba as nb
import numpy as np
import pandas as pd

_LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if _LAB not in sys.path:
    sys.path.insert(0, _LAB)
import goldlab as gl  # noqa: E402

MIN_BARS = 600
ARM = 0.15
D_LEVELS = ["S3", "S2", "S1", "P", "R1", "R2", "R3"]
ALL_LEVELS = ["D_" + k for k in D_LEVELS] + ["W_S2", "W_S1", "W_P", "W_R1", "W_R2", "PDH", "PDL"]

DEFAULTS = dict(
    levels=("D_R1", "D_S1", "D_R2", "D_S2", "PDH", "PDL"),
    entry="close15",       # close15 | touch | retest
    fill="market",         # market | pending (touch: stop order at the level; retest: limit order at the level)
    away=None,             # None both ways | 1: only outward (R / PDH upward, S / PDL downward; P both) | -1: only toward P
    hours=(0, 24),         # New York hour window of the decision [h0, h1); h0 > h1 wraps around midnight
    nth="any",             # any | first | later : break of this level in this direction today
    sq_max=None, sq_min=None, walk_min=None, bbout=None,
    stop="level",          # level | mid
    stop_atr=0.25,
    target="next",         # "next" | None | float (R multiple)
    trail_mid=False,
    eod=1010,              # forced exit at this New York minute of the trading day (1010 = 16:50)
    hold_days=0,
    retest_min=120,
    min_rr=0.0,            # skip when the target is closer than min_rr x the stop distance (measured at the decision price)
    max_stop_atr=1.0,      # skip when the stop is further than this from the decision price (dATR)
    side=0,                # 0 both | +1 long only | -1 short only
    placebo=None,          # int seed: every level set shifted by +/- U(0.2, 0.4) x dATR (same scheme as pivbb/events.py)
    band_k=1.0,            # control levels "B_U" / "B_D" = yesterday's close +/- band_k x dATR (no pivot arithmetic at all)
)

_CTX = {}


def _pivots(h, l, c):
    p = (h + l + c) / 3.0
    return {"P": p, "R1": 2 * p - l, "S1": 2 * p - h, "R2": p + (h - l), "S2": p - (h - l),
            "R3": 2 * p + (h - 2 * l), "S3": 2 * p - (2 * h - l)}


def context(m1):
    """Everything that depends on the frame only (mid prices, days, levels, 15-minute bars)."""
    key = (len(m1), m1.index[0], m1.index[-1], round(float(m1["bc"].iloc[-2000:].sum() + m1["ac"].iloc[-2000:].sum()), 4))
    if key in _CTX:
        return _CTX[key]
    _CTX.clear()
    idx = m1.index
    c = {"N": len(m1)}
    c["tmin"] = (idx.as_unit("ms").asi8 // 60_000).astype(np.int64)
    c["o"] = ((m1["bo"] + m1["ao"]) / 2).to_numpy(np.float64)
    c["h"] = ((m1["bh"] + m1["ah"]) / 2).to_numpy(np.float64)
    c["l"] = ((m1["bl"] + m1["al"]) / 2).to_numpy(np.float64)
    c["c"] = ((m1["bc"] + m1["ac"]) / 2).to_numpy(np.float64)
    td = gl.trading_day(idx)
    day = td.asi8
    first = np.r_[0, np.flatnonzero(np.diff(day)) + 1]
    last = np.r_[first[1:], len(day)]
    dates = pd.DatetimeIndex(td[first])
    c["first"], c["last"], c["dates"] = first, last, dates
    c["day_of"] = np.repeat(np.arange(len(first)), last - first)
    ny = idx.tz_convert(gl.NY)
    c["ny_min"] = (ny.hour * 60 + ny.minute).to_numpy().astype(np.int32)
    D = pd.DataFrame({"o": c["o"][first], "h": np.maximum.reduceat(c["h"], first), "l": np.minimum.reduceat(c["l"], first),
                      "c": c["c"][last - 1], "n": last - first}, index=dates)
    D["full"] = D.n >= MIN_BARS
    F = D[D.full]
    pc = F.c.shift(1)
    tr = np.maximum(F.h - F.l, np.maximum((F.h - pc).abs(), (F.l - pc).abs()))
    # known at the open of a day: the last full day BEFORE it (a day never uses its own row)
    known = pd.DataFrame({"ph": F.h, "pl": F.l, "pc": F.c, "atr": tr.rolling(14).mean()})
    prev = known.reindex(D.index).ffill().shift(1)
    D = D.join(prev)
    wk = F.index.to_period("W-FRI")
    W = F.groupby(wk).agg(h=("h", "max"), l=("l", "min"), c=("c", "last")).shift(1)
    kd = D.index.to_period("W-FRI")
    for col in "hlc":
        D["w" + col] = W[col].reindex(kd).to_numpy()
    c["D"] = D
    # 15-minute bars on the clock grid
    key15 = c["tmin"] // 15
    bfirst = np.r_[0, np.flatnonzero(np.diff(key15)) + 1]
    blast = np.r_[bfirst[1:], len(key15)] - 1
    b = pd.DataFrame({"c": c["c"][blast]})
    mid = b.c.rolling(20).mean()
    sd = b.c.rolling(20).std(ddof=0)
    bw_med = (4 * sd).rolling(96).median()
    c["b_end"] = (key15[bfirst] * 15 + 15).astype(np.int64)        # the bar is known from this minute on
    c["b_ei"] = (blast + 1).astype(np.int64)                        # first M1 bar after the bar
    c["b_day"] = c["day_of"][bfirst].astype(np.int64)
    c["b_c"] = b.c.to_numpy()
    c["b_mid"] = mid.to_numpy()
    c["b_sd"] = sd.to_numpy()
    c["b_sq"] = (4 * sd / bw_med).to_numpy()
    c["b_out_up"] = (b.c > mid + 2 * sd).rolling(8).sum().to_numpy()
    c["b_out_dn"] = (b.c < mid - 2 * sd).rolling(8).sum().to_numpy()
    nd = len(first)
    c["kb0"] = np.searchsorted(c["b_day"], np.arange(nd), side="left").astype(np.int64)
    c["kb1"] = np.searchsorted(c["b_day"], np.arange(nd), side="right").astype(np.int64)
    _CTX[key] = c
    return c


def level_table(c, placebo=None, band_k=1.0):
    """{name: array per day}; the daily set, the weekly set and yesterday's high / low; placebo shifts as in events.py."""
    D = c["D"]
    rng = np.random.default_rng(placebo) if placebo is not None else None
    atr = D.atr.to_numpy()
    sh = lambda: 0.0 if rng is None else rng.uniform(0.2, 0.4, len(D)) * rng.choice([-1.0, 1.0], len(D)) * atr
    out = {}
    d, s = _pivots(D.ph.to_numpy(), D.pl.to_numpy(), D.pc.to_numpy()), sh()
    for k in D_LEVELS:
        out["D_" + k] = d[k] + s
    w, s = _pivots(D.wh.to_numpy(), D.wl.to_numpy(), D.wc.to_numpy()), sh()
    for k in ("S2", "S1", "P", "R1", "R2"):
        out["W_" + k] = w[k] + s
    if rng is not None:
        sh()                                                        # the monthly set's draw in events.py (kept for the same seeds)
    s = sh()
    out["PDH"], out["PDL"] = D.ph.to_numpy() + s, D.pl.to_numpy() + s
    out["B_U"], out["B_D"] = D.pc.to_numpy() + band_k * atr, D.pc.to_numpy() - band_k * atr
    return out


def _role(name):
    if name in ("PDH", "B_U") or "_R" in name:
        return 1
    if name in ("PDL", "B_D") or "_S" in name:
        return -1
    return 0


@nb.njit(cache=True)
def _close_crosses(bc, kb0, kb1, LV, ok_day):
    """15-minute closes crossing a level: (bar, level index, direction, nth cross of that level in that direction today)."""
    nd, nl = LV.shape
    cap = 1 << 16
    K = np.empty(cap, np.int64)
    J = np.empty(cap, np.int64)
    S = np.empty(cap, np.int64)
    Q = np.empty(cap, np.int64)
    n = 0
    cnt = np.zeros((nl, 2), np.int64)
    for d in range(nd):
        if not ok_day[d]:
            continue
        cnt[:, :] = 0
        for k in range(max(kb0[d], 1), kb1[d]):
            p, x = bc[k - 1], bc[k]
            for j in range(nl):
                L = LV[d, j]
                if not np.isfinite(L):
                    continue
                s = 0
                if p <= L and x > L:
                    s = 1
                elif p >= L and x < L:
                    s = -1
                if s != 0:
                    if n == len(K):
                        K = np.concatenate((K, K))
                        J = np.concatenate((J, J))
                        S = np.concatenate((S, S))
                        Q = np.concatenate((Q, Q))
                    K[n], J[n], S[n] = k, j, s
                    Q[n] = cnt[j, (s + 1) // 2]
                    cnt[j, (s + 1) // 2] += 1
                    n += 1
    return K[:n], J[:n], S[:n], Q[:n]


@nb.njit(cache=True)
def _m1_touches(h, l, cl, first, last, LV, atr, ok_day, arm):
    """M1 touches of a level (armed once a close is >= arm x dATR away): (bar, level index, direction, nth touch today)."""
    nd, nl = LV.shape
    cap = 1 << 16
    I = np.empty(cap, np.int64)
    J = np.empty(cap, np.int64)
    S = np.empty(cap, np.int64)
    Q = np.empty(cap, np.int64)
    n = 0
    for d in range(nd):
        if not ok_day[d]:
            continue
        a = arm * atr[d]
        for j in range(nl):
            L = LV[d, j]
            if not np.isfinite(L):
                continue
            side = 0
            q = 0
            for i in range(first[d], last[d]):
                hit = 0
                if side == 1 and h[i] >= L:
                    hit = 1
                elif side == -1 and l[i] <= L:
                    hit = -1
                if hit != 0:
                    if n == len(I):
                        I = np.concatenate((I, I))
                        J = np.concatenate((J, J))
                        S = np.concatenate((S, S))
                        Q = np.concatenate((Q, Q))
                    I[n], J[n], S[n], Q[n] = i, j, hit, q
                    n += 1
                    q += 1
                    side = 0
                else:
                    if cl[i] <= L - a:
                        side = 1
                    elif cl[i] >= L + a:
                        side = -1
    return I[:n], J[:n], S[:n], Q[:n]


@nb.njit(cache=True)
def _first_return(bh, bl, ah, al, e0, e1, L, S):
    """Retest: first M1 bar in [e0, e1) where a limit order at the level would fill (ask low <= L for a buy, bid high >= L for a sell)."""
    out = np.full(len(e0), -1, np.int64)
    for q in range(len(e0)):
        for i in range(e0[q], e1[q]):
            if (S[q] == 1 and al[i] <= L[q]) or (S[q] == -1 and bh[i] >= L[q]):
                out[q] = i
                break
    return out


@nb.njit(cache=True)
def _mid_exit(bc, bmid, b_ei, k0, S, xi):
    """First M1 bar after a 15-minute close on the wrong side of the middle band, among bars from k0 on; capped at xi."""
    out = xi.copy()
    nb_ = len(bc)
    for q in range(len(k0)):
        k = k0[q]
        while k < nb_ and b_ei[k] < xi[q]:
            if S[q] * (bc[k] - bmid[k]) < 0:
                out[q] = b_ei[k]
                break
            k += 1
    return out


def signals(m1, **params):
    """Decision table (one row per signal, before the engine): used by make_orders and by the descriptive tables."""
    p = dict(DEFAULTS)
    unknown = set(params) - set(p)
    if unknown:
        raise ValueError(f"unknown parameters: {unknown}")
    p.update(params)
    c = context(m1)
    D = c["D"]
    N = c["N"]
    names = list(p["levels"])
    T = level_table(c, p["placebo"], p["band_k"])
    LV = np.column_stack([T[k] for k in names])
    DP = np.sort(np.column_stack([T["D_" + k] for k in D_LEVELS]), axis=1)
    atr = D.atr.to_numpy()
    ok_day = np.isfinite(atr) & (atr > 0)
    role = np.array([_role(k) for k in names])
    if p["entry"] in ("close15", "retest"):
        K, J, S, Q = _close_crosses(c["b_c"], c["kb0"], c["kb1"], LV, ok_day)
        d = c["b_day"][K]
        dec_i = c["b_ei"][K]                       # first M1 bar after the break bar: decision / entry minute
        kdec = K                                   # last bar closed at the decision
        kpre = K - 1                               # last bar closed before the breaking bar
        ref = c["b_c"][K]                          # price known at the decision
        ok = dec_i < N
        ok &= c["day_of"][np.minimum(dec_i, N - 1)] == d
    elif p["entry"] == "touch":
        I, J, S, Q = _m1_touches(c["h"], c["l"], c["c"], c["first"], c["last"], LV, atr, ok_day, ARM)
        d = c["day_of"][I]
        K = np.searchsorted(c["b_end"], c["tmin"][I], side="right") - 1      # last 15-minute bar closed before the touch minute
        kdec = kpre = K
        dec_i = I
        ref = LV[d, J]
        ok = K >= 0
    else:
        raise ValueError(p["entry"])
    L = LV[d, J]
    A = atr[d]
    kq = np.maximum(kpre, 0)
    kd_ = np.maximum(kdec, 0)
    mid, sd = c["b_mid"][kd_], c["b_sd"][kd_]
    sq = c["b_sq"][kq]
    walk = np.where(S == 1, c["b_out_up"][kd_], c["b_out_dn"][kd_])
    ok &= np.isfinite(mid) & np.isfinite(sd) & (sd > 0) & np.isfinite(sq)
    if p["entry"] == "touch":
        out_band = S * (L - mid) >= 2 * sd
    else:
        out_band = S * (c["b_c"][kd_] - mid) > 2 * sd
    # filters
    if p["away"] is not None:
        ok &= (role[J] * S == p["away"]) | ((role[J] == 0) & (p["away"] == 1))
    if p["side"]:
        ok &= S == p["side"]
    if p["nth"] == "first":
        ok &= Q == 0
    elif p["nth"] == "later":
        ok &= Q >= 1
    if p["sq_max"] is not None:
        ok &= sq < p["sq_max"]
    if p["sq_min"] is not None:
        ok &= sq >= p["sq_min"]
    if p["walk_min"] is not None:
        ok &= walk >= p["walk_min"]
    if p["bbout"] is not None:
        ok &= out_band == bool(p["bbout"])
    hmin = c["ny_min"][np.minimum(dec_i, N - 1)] / 60.0
    h0, h1 = p["hours"]
    ok &= ((hmin >= h0) & (hmin < h1)) if h0 <= h1 else ((hmin >= h0) | (hmin < h1))
    # stop and target
    if p["stop"] == "level":
        stop = L - S * p["stop_atr"] * A
    elif p["stop"] == "mid":
        stop = mid - S * p["stop_atr"] * A
    else:
        raise ValueError(p["stop"])
    tgt = np.full(len(L), np.nan)
    if p["target"] == "next":
        up = np.array([np.searchsorted(DP[i], x + 1e-9, side="right") for i, x in zip(d, L)], dtype=np.int64) if len(L) else np.zeros(0, np.int64)
        dn = np.array([np.searchsorted(DP[i], x - 1e-9, side="left") - 1 for i, x in zip(d, L)], dtype=np.int64) if len(L) else np.zeros(0, np.int64)
        tu = np.where(up < 7, DP[d, np.minimum(up, 6)], np.nan)
        tdn = np.where(dn >= 0, DP[d, np.maximum(dn, 0)], np.nan)
        tgt = np.where(S == 1, tu, tdn)
    # forced exit
    day_ts = c["dates"][d] + pd.to_timedelta(p["eod"], unit="m")
    if p["hold_days"]:
        day_ts = day_ts + pd.tseries.offsets.BDay(int(p["hold_days"]))
    xi = gl.exit_index(m1, pd.DatetimeIndex(day_ts).tz_localize(gl.NY)) if len(L) else np.zeros(0, np.int64)
    sig = pd.DataFrame({"dec_i": dec_i, "day": d, "lv": J, "side": S, "nth": Q, "level": L, "atr": A, "ref": ref, "stop": stop,
                        "target": tgt, "xi": xi, "kdec": kdec, "sq": sq, "walk": walk, "out_band": out_band, "hour": hmin})
    sig = sig[ok].sort_values(["dec_i", "lv"], kind="stable").reset_index(drop=True)
    sig["name"] = np.array(names)[sig.lv.to_numpy()] if len(sig) else []
    return sig, p, c


def make_orders(m1, **params):
    sig, p, c = signals(m1, **params)
    N = c["N"]
    S = sig.side.to_numpy()
    L = sig.level.to_numpy()
    A = sig.atr.to_numpy()
    stop = sig["stop"].to_numpy().copy()
    tgt = sig.target.to_numpy().copy()
    xi = sig.xi.to_numpy().astype(np.int64)
    dec_i = sig.dec_i.to_numpy().astype(np.int64)
    etype = np.zeros(len(sig), np.int64)
    level = np.full(len(sig), np.nan)
    keep = np.ones(len(sig), bool)
    if p["entry"] == "close15":
        entry_i, ref = dec_i, sig.ref.to_numpy()
    elif p["entry"] == "touch":
        if p["fill"] == "pending":
            entry_i, etype, level, ref = dec_i, etype + 1, L.copy(), L
        else:
            entry_i, ref = dec_i + 1, c["c"][dec_i]                  # the touch minute's close is known when the order is sent
            keep &= c["day_of"][np.minimum(entry_i, N - 1)] == sig.day.to_numpy()
    else:   # retest
        e1 = np.minimum(np.minimum(dec_i + int(p["retest_min"]), xi - 15), N)
        ti = _first_return(m1["bh"].to_numpy(np.float64), m1["bl"].to_numpy(np.float64), m1["ah"].to_numpy(np.float64),
                           m1["al"].to_numpy(np.float64), dec_i, np.maximum(e1, dec_i), L, S)
        keep &= ti >= 0
        ti = np.maximum(ti, 0)
        if p["fill"] == "pending":
            entry_i, etype, level, ref = ti, etype + 2, L.copy(), L
        else:
            entry_i, ref = ti + 1, c["c"][ti]
    entry_i = np.minimum(entry_i, N - 1)
    risk = S * (ref - stop)
    keep &= (risk > 0.02 * A) & (risk <= p["max_stop_atr"] * A)
    if p["target"] == "next":
        reward = S * (tgt - ref)
        keep &= ~(reward <= 0)                                       # NaN target (no pivot beyond) is kept: forced exit only
        if p["min_rr"] > 0:
            keep &= ~(reward < p["min_rr"] * risk)
    elif p["target"] is not None:
        tgt = ref + S * float(p["target"]) * risk
    keep &= entry_i < xi - 15
    exit_i = xi
    if p["trail_mid"]:
        k0 = np.searchsorted(c["b_end"], c["tmin"][entry_i], side="right").astype(np.int64)   # first bar ending after the entry minute
        exit_i = _mid_exit(c["b_c"], c["b_mid"], c["b_ei"], k0, S.astype(np.int64), xi)
        exit_i = np.minimum(np.maximum(exit_i, entry_i + 1), N - 1)
    o = pd.DataFrame({"entry_i": entry_i, "side": S, "etype": etype, "level": level, "expiry_i": np.where(etype > 0, entry_i, -1),
                      "stop": stop, "target": tgt, "exit_i": exit_i, "lv_name": sig.name.to_numpy(), "nth": sig.nth.to_numpy(),
                      "lv_px": L, "atr_d": A})
    return o[keep].sort_values("entry_i", kind="stable").reset_index(drop=True)


# In-sample finalists of the track (frozen 2026-11-11; no model, nothing fitted: every number is a fixed rule parameter).
FINALISTS = {
    # A. "R2 / S2 touched -> run to the next pivot". Each trading day (17:00 New York), R2 and S2 of the Traditional daily
    #    pivots. When price touches one of them after having closed at least 0.15 dATR away from it (either direction),
    #    enter at market on the next minute in the direction of the touch; stop 0.25 dATR behind the level; target = the
    #    next daily pivot beyond it (R3 / P-side R1, S3 / S1); otherwise exit at 16:50 New York. One position at a time.
    "r2s2_touch_run": dict(levels=["D_R2", "D_S2"], entry="touch", fill="market", stop="level", stop_atr=0.25, target="next", eod=1010),
    # B. "close beyond an outer pivot -> ride until the end of the day". A 15-minute bar closes beyond R2, S2, R3 or S3
    #    (previous 15-minute close on the other side), decision between 02:00 and 12:00 New York; market on the next minute;
    #    stop 0.25 dATR behind the level; no target; exit at 16:50 New York. One position at a time.
    #    NOT specific to pivots: yesterday's close +/- 0.88 dATR gives the same result.
    "outer_close_ride": dict(levels=["D_R2", "D_S2", "D_R3", "D_S3"], entry="close15", fill="market", hours=[2, 12], stop="level", stop_atr=0.25,
                             target=None, eod=1010),
}
