"""Pivot / key-level strategies on XAUUSD (research track 'pivots').

    make_orders(m1, **params) -> orders DataFrame for goldlab.simulate
    FINALISTS = {name: params}

Causality
---------
* Every level of trading day D is computed from the PREVIOUS full trading day (NY-17:00
  boundary, i.e. broker "server day", BID prices like an MT5 D1 bar, >= 600 M1 bars so that
  holiday stubs / data holes are skipped).  Weekly levels come from the previous week.
  The daily ATR used for stops is a 14-day SMA of true range on previous full days.
  => all levels / ATR are known before the first bar of day D.
* Fade (limit) orders: a level is "armed" at the window start if the price is on one side
  of it; the order is the first touch of the level inside the window (resting limit order,
  fills when ASK low <= level for a buy limit, BID high >= level for a sell limit, exactly
  the simulator's fill rule).  entry_i = that first-touch bar, which reproduces the true
  chronological order of several resting orders (the simulator processes orders by entry_i).
* Break orders: decision on the CLOSE of an M15 (or H1) bar beyond the level, entry at the
  open of the next M1 bar (= goldlab.entry_index(m1, bar.t_close)).
* Every order has an absolute stop and a forced exit (exit_i) at `eod` NY time of the same
  trading day (or `hold_days` later, <= 4).

The same code regenerates the finalists on any M1 frame (needs >= ~15 trading days of
history before the first trade for the ATR warm-up).
"""
import os
import sys

import numba as nb
import numpy as np
import pandas as pd

_LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if _LAB not in sys.path:
    sys.path.insert(0, _LAB)
import goldlab as gl  # noqa: E402

MIN_BARS = 600          # a trading day with fewer M1 bars is a stub/data hole: not used for levels, not traded
ATR_N = 14

FAMILIES = {
    "floor": ["S3", "S2", "S1", "P", "R1", "R2", "R3"],
    "cam": ["L4", "L3", "L2", "L1", "H1", "H2", "H3", "H4"],
    "pdhl": ["PDL", "PDC", "PDH"],
    "wfloor": ["WS2", "WS1", "WP", "WR1", "WR2"],
    "round": ["RB", "RA"],     # nearest round number below / above the window-open price
}

DEFAULTS = dict(
    family="floor",              # floor | cam | pdhl | wfloor | round
    levels=("S1", "R1"),         # level names traded (round: RB/RA)
    grid=50.0,                   # round-number grid in $
    mode="fade",                 # fade: resting LIMIT at the level (bounce) | tbreak: resting STOP at the
                                 #   level (break-through at first touch) | break: bar close beyond -> market
                                 #   | reject: after a touch, first bar close back on the arming side -> market
    tf=15,                       # break / reject modes: confirmation bar in minutes (5, 15 or 60)
    win=("LDN", 480, "NY", 720),  # active window [start, end): (tz, minutes after local midnight of the
                                 #   trading date) -- here 08:00 London -> 12:00 New York
    eod=960,                     # forced exit at this NY minute (960 = 16:00) of the exit day
    hold_days=0,                 # 0 = same trading day; n = forced exit n trading days later (<= 4)
    stop_atr=0.25,               # stop distance beyond the level, in daily-ATR units
    tgt="next",                  # 'next' = next level of the family; float = R multiple of the stop;
                                 #   None = no target (stop or forced exit)
    bias=None,                   # None | 'with' (only the side of sign(window open - P)) | 'against'
    side=0,                      # 0 both | +1 long only | -1 short only
    min_rr=0.0,                  # skip if target distance < min_rr * stop distance
    roles="any",                 # any: a level's role (support/resistance) is set by the price at window
                                 #   start | classic: S/L-type levels must be below the price (support),
                                 #   R/H-type levels above (resistance); P, PDC, WP, round: either
    placebo=None,                # int seed: shift all the day's levels by +-U(0.2,0.4)*ATR (random levels)
    rng=None,                    # (lo, hi): only trade if the day's range so far (from 17:00 NY to the
                                 #   decision) / ATR is in [lo, hi)
    offset_atr=0.0,              # tbreak: place the stop order this far BEYOND the level (ATR units);
                                 #   stop/target are measured from that entry level
    fresh=False,                 # True: levels are armed at the START of the trading day (17:00 NY) and a
                                 #   trade needs the day's FIRST touch to fall inside the active window
)

SUPPORT_NAMES = {"S1", "S2", "S3", "L1", "L2", "L3", "L4", "PDL", "WS1", "WS2"}
RESIST_NAMES = {"R1", "R2", "R3", "H1", "H2", "H3", "H4", "PDH", "WR1", "WR2"}

_CTX = {}


# ----------------------------------------------------------------------------------------------
# context: per-bar clocks and per-day tables
# ----------------------------------------------------------------------------------------------
def context(m1):
    key = (id(m1), len(m1), m1.index[0], m1.index[-1])
    if key in _CTX:
        return _CTX[key]
    _CTX.clear()
    idx = m1.index
    c = {"N": len(m1)}
    for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"):
        c[k] = m1[k].to_numpy(np.float64)
    td = gl.trading_day(idx)                                   # naive NY trading date
    tdv = td.values.astype("datetime64[m]").astype(np.int64)
    ny = gl.local(idx, gl.NY).tz_localize(None).values.astype("datetime64[m]").astype(np.int64)
    ldn = gl.local(idx, gl.LDN).tz_localize(None).values.astype("datetime64[m]").astype(np.int64)
    c["tdmin_NY"] = (ny - tdv).astype(np.int32)                # minutes after local midnight of trading date
    c["tdmin_LDN"] = (ldn - tdv).astype(np.int32)
    um = idx.values.astype("datetime64[m]").astype(np.int64)
    c["umin"] = um
    days, s = np.unique(td.values, return_index=True)
    e = np.r_[s[1:], len(idx)]
    nb_ = e - s
    full = nb_ >= MIN_BARS
    bh, bl, bo, bc = c["bh"], c["bl"], c["bo"], c["bc"]
    H = np.maximum.reduceat(bh, s)
    L = np.minimum.reduceat(bl, s)
    O = bo[s]
    C = bc[e - 1]
    D = pd.DataFrame({"s": s, "e": e, "n": nb_, "full": full, "O": O, "H": H, "L": L, "C": C},
                     index=pd.DatetimeIndex(days, name="day"))
    F = D[D.full].copy()
    pc = F.C.shift(1)
    tr = np.maximum(F.H - F.L, np.maximum((F.H - pc).abs(), (F.L - pc).abs()))
    F["atr"] = tr.rolling(ATR_N, min_periods=ATR_N).mean().shift(1)     # known before the day
    F["pH"], F["pL"], F["pC"] = F.H.shift(1), F.L.shift(1), F.C.shift(1)
    wk = F.index - pd.to_timedelta(F.index.weekday, unit="D")
    W = F.groupby(wk).agg(H=("H", "max"), L=("L", "min"), C=("C", "last"))
    Wp = W.shift(1)
    F["wH"] = Wp.H.reindex(wk).to_numpy()
    F["wL"] = Wp.L.reindex(wk).to_numpy()
    F["wC"] = Wp.C.reindex(wk).to_numpy()
    for col in ("atr", "pH", "pL", "pC", "wH", "wL", "wC"):
        D[col] = F[col].reindex(D.index)
    D.loc[~D.full, ["atr", "pH", "pL", "pC", "wH", "wL", "wC"]] = np.nan
    c["D"] = D
    _CTX[key] = c
    return c


def family_levels(c, family):
    """(names, array [n_days, n_levels]) of the day's levels (NaN where unknown)."""
    D = c["D"]
    H, L, C = D.pH.to_numpy(), D.pL.to_numpy(), D.pC.to_numpy()
    if family == "floor":
        P = (H + L + C) / 3
        lv = {"S3": L - 2 * (H - P), "S2": P - (H - L), "S1": 2 * P - H, "P": P,
              "R1": 2 * P - L, "R2": P + (H - L), "R3": H + 2 * (P - L)}
    elif family == "cam":
        r = (H - L) * 1.1
        lv = {"L4": C - r / 2, "L3": C - r / 4, "L2": C - r / 6, "L1": C - r / 12,
              "H1": C + r / 12, "H2": C + r / 6, "H3": C + r / 4, "H4": C + r / 2}
    elif family == "pdhl":
        lv = {"PDL": L, "PDC": C, "PDH": H}
    elif family == "wfloor":
        wH, wL, wC = D.wH.to_numpy(), D.wL.to_numpy(), D.wC.to_numpy()
        P = (wH + wL + wC) / 3
        lv = {"WS2": P - (wH - wL), "WS1": 2 * P - wH, "WP": P, "WR1": 2 * P - wL, "WR2": P + (wH - wL)}
    else:
        raise ValueError(family)
    names = FAMILIES[family]
    return names, np.column_stack([lv[n] for n in names])


def floor_P(c):
    D = c["D"]
    return (D.pH.to_numpy() + D.pL.to_numpy() + D.pC.to_numpy()) / 3


def window_indices(c, win, eod, hold_days=0):
    """Per day: ws, we (window [ws, we) in M1 indices; -1 if none) and the forced-exit index."""
    D = c["D"]
    tz0, m0, tz1, m1_ = win
    a0, a1, an = c["tdmin_" + tz0], c["tdmin_" + tz1], c["tdmin_NY"]
    nd = len(D)
    ws = np.full(nd, -1, np.int64)
    we = np.full(nd, -1, np.int64)
    ex = np.full(nd, -1, np.int64)
    s, e, full = D.s.to_numpy(), D.e.to_numpy(), D.full.to_numpy()
    for k in range(nd):
        if not full[k]:
            continue
        a, b = s[k], e[k]
        i0 = a + np.searchsorted(a0[a:b], m0, side="left")
        i1 = a + np.searchsorted(a1[a:b], m1_, side="left")
        ix = a + np.searchsorted(an[a:b], eod, side="left")
        ex[k] = min(ix, b - 1)
        if i0 < i1 and i0 < b:
            ws[k], we[k] = i0, min(i1, ex[k])
    if hold_days:
        fk = np.flatnonzero(full)
        pos = np.searchsorted(fk, np.arange(nd))
        tgt = np.minimum(pos + hold_days, len(fk) - 1)
        ex2 = ex[fk[tgt]]
        ex = np.where(full, ex2, -1)
    return ws, we, ex


# ----------------------------------------------------------------------------------------------
# numba kernels
# ----------------------------------------------------------------------------------------------
@nb.njit(cache=True)
def _first_touch(lo, hi, p_open, ws, we, lv):
    """role +1: level below window-open price (support, touched when lo<=L);
    role -1: level above (resistance, touched when hi>=L). touch = first bar index or -1."""
    nd, nl = lv.shape
    role = np.zeros((nd, nl), np.int8)
    touch = np.full((nd, nl), -1, np.int64)
    for k in range(nd):
        a = ws[k]
        b = we[k]
        if a < 0 or a >= b:
            continue
        p0 = p_open[a]
        for j in range(nl):
            L = lv[k, j]
            if np.isnan(L):
                continue
            if L < p0:
                role[k, j] = 1
                for i in range(a, b):
                    if lo[i] <= L:
                        touch[k, j] = i
                        break
            elif L > p0:
                role[k, j] = -1
                for i in range(a, b):
                    if hi[i] >= L:
                        touch[k, j] = i
                        break
    return role, touch


@nb.njit(cache=True)
def _first_close_beyond(close, is_last, p_open, ws, we, lv):
    """role -1: level above window-open (break UP when a confirmation bar closes above it);
    role +1: level below (break DOWN on a close below).  brk = M1 index of the last minute of the
    first confirmation bar closing beyond (decision known at the end of that minute) or -1."""
    nd, nl = lv.shape
    role = np.zeros((nd, nl), np.int8)
    brk = np.full((nd, nl), -1, np.int64)
    for k in range(nd):
        a = ws[k]
        b = we[k]
        if a < 0 or a >= b:
            continue
        p0 = p_open[a]
        for j in range(nl):
            L = lv[k, j]
            if np.isnan(L):
                continue
            if L > p0:
                role[k, j] = -1
                for i in range(a, b):
                    if is_last[i] and close[i] > L:
                        brk[k, j] = i
                        break
            elif L < p0:
                role[k, j] = 1
                for i in range(a, b):
                    if is_last[i] and close[i] < L:
                        brk[k, j] = i
                        break
    return role, brk


@nb.njit(cache=True)
def _reject_after_touch(bl, bh, bc, is_last, p_open, ws, we, lv, sd):
    """Rejection entry: after the first touch of a level (bid prices), the first confirmation-bar
    close back on the arming side, provided price never went `sd` beyond the level in between
    (that would have been the stop).  Returns role and decision bar index (entry = next bar)."""
    nd, nl = lv.shape
    role = np.zeros((nd, nl), np.int8)
    dec = np.full((nd, nl), -1, np.int64)
    for k in range(nd):
        a = ws[k]
        b = we[k]
        if a < 0 or a >= b:
            continue
        p0 = p_open[a]
        for j in range(nl):
            L = lv[k, j]
            if np.isnan(L) or np.isnan(sd[k]):
                continue
            if L < p0:
                role[k, j] = 1
                touched = False
                for i in range(a, b):
                    if not touched and bl[i] <= L:
                        touched = True
                    if touched:
                        if bl[i] <= L - sd[k]:
                            break
                        if is_last[i] and bc[i] > L:
                            dec[k, j] = i
                            break
            elif L > p0:
                role[k, j] = -1
                touched = False
                for i in range(a, b):
                    if not touched and bh[i] >= L:
                        touched = True
                    if touched:
                        if bh[i] >= L + sd[k]:
                            break
                        if is_last[i] and bc[i] < L:
                            dec[k, j] = i
                            break
    return role, dec


@nb.njit(cache=True)
def _cum_day_range(bh, bl, s, e):
    hi = np.empty(len(bh))
    lo = np.empty(len(bl))
    for k in range(len(s)):
        h = -np.inf
        q = np.inf
        for i in range(s[k], e[k]):
            if bh[i] > h:
                h = bh[i]
            if bl[i] < q:
                q = bl[i]
            hi[i] = h
            lo[i] = q
    return hi, lo


def _bar_last_flags(c, tf):
    g = c["umin"] // tf
    last = np.empty(len(g), np.bool_)
    last[:-1] = g[1:] != g[:-1]
    last[-1] = True
    return last


def _placebo_shift(c, seed):
    D = c["D"]
    rng = np.random.default_rng(seed)
    nd = len(D)
    sgn = rng.choice([-1.0, 1.0], nd)
    u = rng.uniform(0.2, 0.4, nd)
    return sgn * u * D.atr.to_numpy()


def _round_levels(c, ws, grid, phase=None):
    """Nearest grid level below / above the window-open price (bid)."""
    p0 = np.where(ws >= 0, c["bo"][np.maximum(ws, 0)], np.nan)
    ph = np.zeros(len(ws)) if phase is None else phase
    rb = np.floor((p0 - ph) / grid) * grid + ph
    ra = rb + grid
    return np.column_stack([rb, ra])


# ----------------------------------------------------------------------------------------------
# orders
# ----------------------------------------------------------------------------------------------
def make_orders(m1, **params):
    p = dict(DEFAULTS)
    unknown = set(params) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown params {unknown}")
    p.update(params)
    c = context(m1)
    D = c["D"]
    atr = D.atr.to_numpy()
    ws, we, ex = window_indices(c, p["win"], p["eod"], p["hold_days"])
    ws_trade = ws
    if p["fresh"]:                                     # arm at the first bar of the trading day
        ws = np.where(ws >= 0, D.s.to_numpy(), -1).astype(np.int64)
    fam = p["family"]
    grid = float(p["grid"])
    if fam == "round":
        phase = None
        if p["placebo"] is not None:
            rng = np.random.default_rng(p["placebo"])
            phase = rng.uniform(0.2, 0.8, len(D)) * grid
        names = FAMILIES["round"]
        lv = _round_levels(c, ws, grid, phase)
        lv[np.isnan(atr)] = np.nan
        Pref = np.full(len(D), np.nan)
    else:
        names, lv = family_levels(c, fam)
        Pref = floor_P(c)
        if p["placebo"] is not None:
            sh = _placebo_shift(c, p["placebo"])
            lv = lv + sh[:, None]
            Pref = Pref + sh
        lv = np.where(np.isnan(atr)[:, None], np.nan, lv)
    sel = [names.index(n) for n in p["levels"]]
    lv_all = lv
    lv_tr = np.ascontiguousarray(lv[:, sel])
    role0 = None
    if p["mode"] == "tbreak" and p["offset_atr"]:
        p0w = np.where(ws >= 0, c["bo"][np.maximum(ws, 0)], np.nan)
        role0 = np.sign(p0w[:, None] - lv_tr)          # +1 support, -1 resistance (raw level)
        lv_tr = np.ascontiguousarray(lv_tr - role0 * p["offset_atr"] * atr[:, None])

    if p["mode"] == "fade":
        # supports are touched by the ASK low (buy limit), resistances by the BID high (sell limit)
        role, hit = _first_touch(c["al"], c["bh"], c["bo"], ws, we, lv_tr)
    elif p["mode"] == "tbreak":
        # break-through at first touch: resting STOP order at the level (sell-stop under a support
        # fills when BID low <= level, buy-stop over a resistance when ASK high >= level)
        role, hit = _first_touch(c["bl"], c["ah"], c["bo"], ws, we, lv_tr)
    elif p["mode"] == "break":
        last = _bar_last_flags(c, int(p["tf"]))
        role, hit = _first_close_beyond(c["bc"], last, c["bo"], ws, we, lv_tr)
    elif p["mode"] == "reject":
        last = _bar_last_flags(c, int(p["tf"]))
        role, hit = _reject_after_touch(c["bl"], c["bh"], c["bc"], last, c["bo"], ws, we, lv_tr,
                                        p["stop_atr"] * atr)
    else:
        raise ValueError(p["mode"])

    if role0 is not None:                              # offset pushed the level across the price: skip
        hit = np.where(role == role0, hit, -1)
    if p["fresh"]:                                     # first touch of the day must be in the active window
        hit = np.where(hit >= ws_trade[:, None], hit, -1)
    kk, jj = np.nonzero(hit >= 0)
    if len(kk) == 0:
        return pd.DataFrame(columns=["entry_i", "side", "etype", "level", "expiry_i", "stop",
                                     "target", "exit_i"])
    i_hit = hit[kk, jj]
    rl = role[kk, jj].astype(np.int64)
    L = lv_tr[kk, jj]
    A = atr[kk]
    sd = p["stop_atr"] * A
    if p["mode"] == "fade":
        side = rl                              # support -> long, resistance -> short
        entry_i = i_hit
        etype = np.full(len(kk), 2)
        level = L
        ref = L
        stop = L - side * sd
    elif p["mode"] == "tbreak":
        side = -rl                             # resistance -> buy-stop (long), support -> sell-stop
        entry_i = i_hit
        etype = np.ones(len(kk), np.int64)
        level = L
        ref = L
        stop = L - side * sd
    elif p["mode"] == "reject":
        side = rl                              # rejection of a support -> long
        entry_i = i_hit + 1
        etype = np.zeros(len(kk), np.int64)
        level = np.full(len(kk), np.nan)
        ref = c["bc"][i_hit]
        stop = L - side * sd
    else:
        side = -rl                             # level above broken upward -> long
        entry_i = i_hit + 1
        etype = np.zeros(len(kk), np.int64)
        level = np.full(len(kk), np.nan)
        ref = c["bc"][i_hit]
        stop = L - side * sd
    risk = np.abs(ref - stop)
    # target
    if p["tgt"] is None:
        target = np.full(len(kk), np.inf)      # no target: stop or forced exit only (NaN set below)
    elif p["tgt"] == "next":
        allv = lv_all[kk]                      # all the family's levels that day
        if fam == "round":
            nxt = L + side * grid
        else:
            up = np.where(allv > (ref + 1e-9)[:, None], allv, np.inf).min(axis=1)
            dn = np.where(allv < (ref - 1e-9)[:, None], allv, -np.inf).max(axis=1)
            nxt = np.where(side > 0, up, dn)
        target = np.where(np.isfinite(nxt), nxt, np.nan)
    else:
        target = ref + side * float(p["tgt"]) * risk
    no_tgt = np.isinf(target) & (p["tgt"] is None)
    ok = (np.isfinite(target) | no_tgt) & np.isfinite(stop) & (risk > 0) & (entry_i < c["N"])
    tdist = np.where(no_tgt, np.inf, side * (target - ref))
    target = np.where(no_tgt, np.nan, target)
    ok &= tdist > 0
    if p["min_rr"] > 0:
        ok &= tdist >= p["min_rr"] * risk
    # entry must happen before the forced exit
    xi = ex[kk]
    ok &= entry_i < xi
    if p["side"]:
        ok &= side == p["side"]
    if p["roles"] == "classic":
        nm = np.array(p["levels"], dtype=object)[jj]
        sup = np.isin(nm, list(SUPPORT_NAMES))
        res = np.isin(nm, list(RESIST_NAMES))
        ok &= ~(sup & (rl != 1)) & ~(res & (rl != -1))
    if p["bias"] is not None and fam != "round":
        p0 = c["bo"][ws_trade[kk]]
        b = np.sign(p0 - Pref[kk])
        ok &= (side == b) if p["bias"] == "with" else (side == -b)
    if p["rng"] is not None:
        if "cumhi" not in c:
            c["cumhi"], c["cumlo"] = _cum_day_range(c["bh"], c["bl"], D.s.to_numpy(), D.e.to_numpy())
        if p["mode"] in ("fade", "tbreak"):      # resting order: range before the touch bar + the level
            ib = np.maximum(i_hit - 1, 0)
            r_so_far = np.maximum(c["cumhi"][ib], L) - np.minimum(c["cumlo"][ib], L)
        else:                                    # bar-close decision: range through the decision bar
            r_so_far = c["cumhi"][i_hit] - c["cumlo"][i_hit]
        rr = r_so_far / A
        ok &= (rr >= p["rng"][0]) & (rr < p["rng"][1])
    o = pd.DataFrame({
        "entry_i": entry_i, "side": side, "etype": etype, "level": level,
        "expiry_i": np.where(etype > 0, we[kk] - 1, -1),
        "stop": stop, "target": target, "exit_i": xi,
        "lvl": np.array(p["levels"], dtype=object)[jj], "day": D.index.to_numpy()[kk],
        "atr_d": A, "dec_i": i_hit,
    })[ok]
    return o.sort_values("entry_i", kind="stable").reset_index(drop=True)


FINALISTS = {}
