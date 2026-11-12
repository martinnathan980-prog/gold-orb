"""Sleeve-specific part of the descriptors: decision time, risk, trigger size and own volatility unit.

decisions(k, mk, o, es)    -> DataFrame (one row per order): t_dec (ns), side, extra fields of the signal itself
features(k, mk, own, dec)  -> dict of arrays: risk, trig, vol_cur, vol (ratio to the 60-day median)
`features` only reads bars that start before each t_dec, so it gives the same values on a frame cut at t_dec
(causality.py runs it on cut frames)."""
import sys

import numpy as np
import pandas as pd

import common as C
import descr as D
from descr import H_NS, M_NS, cm, ns_of

import goldlab as gl  # noqa: E402


def mod(name):
    return sys.modules[name]


# ------------------------------------------------------------------------------------------- helpers
def med_at(tk, val, t, days=60):
    """rolling `days`-day median of a series (t_known, val) at its last point known at t"""
    tk = np.asarray(tk, np.int64)
    val = np.asarray(val, np.float64)
    ok = np.isfinite(val)
    tk, val = tk[ok], val[ok]
    s = pd.Series(val, index=pd.DatetimeIndex(tk.astype("datetime64[ns]")))
    med = s.rolling(f"{days}D").median().to_numpy()
    j = np.searchsorted(tk, np.asarray(t, np.int64), side="right") - 1
    return np.where(j >= 0, med[np.maximum(j, 0)], np.nan)


def ny_date_t(t_ns, hhmm_min, tz=C.NY):
    """UTC ns of the wall clock `hhmm_min` (minutes after midnight, zone tz) on the local date of each t"""
    loc = D.to_ts(t_ns).tz_convert(tz).tz_localize(None).normalize()
    x = (loc + pd.to_timedelta(hhmm_min, unit="m")).tz_localize(tz, ambiguous=True, nonexistent="shift_forward")
    return ns_of(x.tz_convert("UTC"))


def mid_hourly(mk):
    """hourly mid bars (UTC grid) over every hour with at least one bar: start ns, h, l, c (crypto convention:
    h = max of the minute mid highs, c = last minute mid close)"""
    ns = ns_of(mk.index)
    hid = ns // H_NS
    st = np.flatnonzero(np.r_[True, hid[1:] != hid[:-1]])
    last = np.r_[st[1:] - 1, len(ns) - 1]
    mh = (mk["bh"].to_numpy(np.float64) + mk["ah"].to_numpy(np.float64)) / 2
    ml = (mk["bl"].to_numpy(np.float64) + mk["al"].to_numpy(np.float64)) / 2
    mc = (mk["bc"].to_numpy(np.float64) + mk["ac"].to_numpy(np.float64)) / 2
    return pd.DataFrame({"start": hid[st] * H_NS, "h": np.maximum.reduceat(mh, st),
                         "l": np.minimum.reduceat(ml, st), "c": mc[last]})


# ------------------------------------------------------------------------------------------- us100
def _noise_arrays(mk):
    g = cm.grid(mk)
    P, O = g["P"], g["O"]
    checks = np.arange(30, 361, 30)
    absmove = np.abs(P[:, checks] / O[:, None] - 1)
    sig = pd.DataFrame(absmove).rolling(14, min_periods=9).mean().shift(1).to_numpy()
    cl = P[:, 390]
    pc = np.r_[np.nan, cl[:-1]]
    hi_ref = np.where(np.isfinite(pc), np.fmax(O, pc), O)
    lo_ref = np.where(np.isfinite(pc), np.fmin(O, pc), O)
    t0 = np.asarray(g["t0"]).astype("datetime64[ns]").astype(np.int64)
    return g, P, checks, sig, hi_ref, lo_ref, t0


def noise_decisions(mk, o):
    et = ns_of(mk.index[o.entry_i.to_numpy()])
    ny = D.to_ts(et).tz_convert(C.NY)
    T = ny.floor("30min").tz_convert("UTC")
    return pd.DataFrame({"t_dec": ns_of(T), "side": o.side.to_numpy(), "stop": o.stop.to_numpy()})


def noise_features(mk, own, dec):
    g, P, checks, sig, hi_ref, lo_ref, t0 = _noise_arrays(mk)
    t = dec.t_dec.to_numpy(np.int64)
    d = np.searchsorted(t0, t, side="right") - 1
    m = ((t - t0[d]) // M_NS).astype(np.int64)
    j = m // 30 - 1
    assert (m % 30 == 0).all() and (j >= 0).all() and (j < len(checks)).all()
    p = P[d, m]
    s = sig[d, j]
    side = dec.side.to_numpy()
    ref = np.where(side > 0, hi_ref[d], lo_ref[d])
    trig = np.abs(p / ref - 1) / s
    risk = np.abs(p - dec.stop.to_numpy())
    vol = np.full(len(t), np.nan)
    for jj in range(len(checks)):
        w = j == jj
        if w.any():
            tk = t0 + checks[jj] * M_NS
            vol[w] = s[w] / med_at(tk, sig[:, jj], t[w])
    return {"risk": risk, "trig": trig, "vol_cur": s, "vol": vol}


def ocm_decisions(mk, o):
    et = ns_of(mk.index[o.entry_i.to_numpy()])
    return pd.DataFrame({"t_dec": ny_date_t(et, 9 * 60 + 34), "side": o.side.to_numpy(),
                         "stop_dist": o.stop_dist.to_numpy()})


def ocm_features(mk, own, dec):
    g = cm.grid(mk)
    P, O = g["P"], g["O"]
    t0 = np.asarray(g["t0"]).astype("datetime64[ns]").astype(np.int64)
    move = P[:, 4] / O - 1
    amove = np.abs(move)
    med = pd.Series(amove).rolling(20, min_periods=10).median().shift(1).to_numpy()
    t = dec.t_dec.to_numpy(np.int64)
    d = np.searchsorted(t0, t, side="right") - 1
    assert (t - t0[d] == 4 * M_NS).all()
    tk, a = cm.daily_atr(mk, 14)
    tk = np.asarray(tk).astype("datetime64[ns]").astype(np.int64)
    cur = cm.atr_at(mk, t.astype("datetime64[ns]"), 14)
    return {"risk": dec.stop_dist.to_numpy(), "trig": amove[d] / med[d], "vol_cur": cur,
            "vol": cur / med_at(tk, a, t)}


# ------------------------------------------------------------------------------------------- crypto brk72
def brk_decisions(mk, o):
    return pd.DataFrame({"t_dec": ns_of(o.dec_time), "side": o.side.to_numpy(), "stop_dist": o.stop_dist.to_numpy(),
                         "over_atr_rule": o.over_atr.to_numpy()})


def brk_features(mk, own, dec):
    S = mod("r2_crypto_strategy")
    b = mid_hourly(mk)
    c = b["c"]
    hi = c.rolling(72).max().shift(1).to_numpy()
    lo = c.rolling(72).min().shift(1).to_numpy()
    atr = S.sma_atr(b, 24).to_numpy()
    t = dec.t_dec.to_numpy(np.int64)
    k = np.searchsorted(b["start"].to_numpy(), t - H_NS)
    assert (b["start"].to_numpy()[k] == t - H_NS).all()
    side = dec.side.to_numpy()
    cc = c.to_numpy()[k]
    trig = np.where(side > 0, cc - hi[k], lo[k] - cc) / atr[k]
    tk = b["start"].to_numpy() + H_NS
    return {"risk": dec.stop_dist.to_numpy(), "trig": trig, "vol_cur": atr[k], "vol": atr[k] / med_at(tk, atr, t)}


# ------------------------------------------------------------------------------------------- crypto F1
def f1_decisions(mk, o):
    return pd.DataFrame({"t_dec": o.cid.to_numpy(np.int64), "side": o.side.to_numpy(),
                         "stop_dist": o.stop_dist.to_numpy()})


def f1_features(mk, own, dec):
    S = mod("r2_ml_strategy")
    b = S._h1_bid(mk)                                  # no cache (S.session_bars caches on id(frame))
    ny = gl.local(b.index, C.NY)
    keep = (ny.hour >= 2) & (ny.hour < 16) & (ny.dayofweek < 5)
    b = b[keep]
    h, l, c = b["h"], b["l"], b["c"]
    A = (h - l).rolling(70).mean().to_numpy()
    hh = h.shift(1).rolling(14).max().to_numpy()
    ll = l.shift(1).rolling(14).min().to_numpy()
    st = ns_of(b.index)
    t = dec.t_dec.to_numpy(np.int64)
    k = np.searchsorted(st, t - H_NS)
    assert (st[k] == t - H_NS).all()
    side = dec.side.to_numpy()
    cc = c.to_numpy()[k]
    trig = np.where(side > 0, cc - hh[k], ll[k] - cc) / A[k]
    return {"risk": dec.stop_dist.to_numpy(), "trig": trig, "vol_cur": A[k], "vol": A[k] / med_at(st + H_NS, A, t)}


# ------------------------------------------------------------------------------------------- nq_btc_follow
def _nq_arrays(mk):
    L = C.leadlag_module()
    tm, t0, n = L._grid(mk)
    mid_c = ((mk["bc"] + mk["ac"]) / 2).to_numpy(np.float64)
    cF_raw = L._on_grid(tm, mid_c, t0, n)
    hasF = np.isfinite(cF_raw)
    cF = L._ffill(cF_raw)
    win = 20 * 1440
    minobs = win // 6
    rF1 = np.where(hasF, L._lret(cF, 1), np.nan)
    sigF1 = L._trail_rms(rF1, win, minobs)
    ltm, lc, _ = L._leader("us100")
    cL_raw = L._on_grid(ltm, lc, t0, n)
    hasL = np.isfinite(cL_raw)
    cL = L._ffill(cL_raw)
    x = np.where(hasL, L._lret(cL, 1), np.nan)
    sigX = L._trail_rms(x, win, minobs)
    return tm, t0, n, x, sigX, sigF1, hasF


def nq_decisions(mk, o):
    """decision bar g of every order, recovered with the rule's own arrays (xlead_orders)"""
    L = C.leadlag_module()
    tm, t0, n, x, sigX, sigF1, hasF = _nq_arrays(mk)
    nym, bem, wd = L._clock(t0, n)
    sig = L._sess_mask("uscash", nym, bem, wd, 60) & np.isfinite(x) & np.isfinite(sigX) & (np.abs(x) >= 6 * sigX) \
        & np.isfinite(sigF1) & hasF
    g = np.flatnonzero(sig)
    ei = np.searchsorted(tm, t0 + g + 1, side="left")
    ok = ei < len(tm)
    g, ei = g[ok], ei[ok]
    ok = (tm[ei] - (t0 + g + 1)) <= 1
    g, ei = g[ok], ei[ok]
    first = pd.Series(g).groupby(ei).first()             # drop_duplicates("entry_i") keeps the first
    gg = first.reindex(o.entry_i.to_numpy()).to_numpy()
    assert np.isfinite(gg).all()
    gg = gg.astype(np.int64)
    side_chk = np.sign(x[gg]).astype(np.int64)
    assert (side_chk == o.side.to_numpy()).all()
    return pd.DataFrame({"t_dec": (t0 + gg + 1) * M_NS, "side": o.side.to_numpy(), "stop_dist": o.stop_dist.to_numpy()})


def nq_features(mk, own, dec):
    tm, t0, n, x, sigX, sigF1, hasF = _nq_arrays(mk)
    t = dec.t_dec.to_numpy(np.int64)
    g = t // M_NS - t0 - 1
    trig = np.abs(x[g]) / sigX[g]
    hr = np.flatnonzero(((np.arange(n) + t0) % 60) == 0)
    tk = (hr + t0) * M_NS
    cur = sigF1[g]
    return {"risk": dec.stop_dist.to_numpy(), "trig": trig, "vol_cur": cur, "vol": cur / med_at(tk, sigF1[hr], t)}


# ------------------------------------------------------------------------------------------- gold
def fri_decisions(mk, o):
    et = ns_of(mk.index[o.entry_i.to_numpy()])
    return pd.DataFrame({"t_dec": ny_date_t(et, 13 * 60 + 30), "side": o.side.to_numpy(),
                         "stop_dist": o.stop_dist.to_numpy()})


def fri_features(mk, own, dec):
    OV = mod("r2_overnight_strategy")
    ns = ns_of(mk.index)
    done, atr = OV._atr(mk, ns, "1h", 14)
    t = dec.t_dec.to_numpy(np.int64)
    j = np.searchsorted(done, t, side="right") - 1
    a = np.where(j >= 0, atr[np.maximum(j, 0)], np.nan)
    trig = (own.P(t) - own.P(t - H_NS)) / a
    return {"risk": dec.stop_dist.to_numpy(), "trig": trig, "vol_cur": a, "vol": a / med_at(done, atr, t)}


def donch_decisions(mk, o):
    return pd.DataFrame({"t_dec": ns_of(o.dec_time), "side": o.side.to_numpy(), "stop_dist": o.stop_dist.to_numpy(),
                         "level_rule": o.level.to_numpy()})


def donch_features(mk, own, dec):
    b = gl.bars(mk, "4h")
    up = b["h"].rolling(60).max().to_numpy()
    dn = b["l"].rolling(60).min().to_numpy()
    a = gl.atr(b, 14).to_numpy()
    tc = ns_of(b["t_close"])
    t = dec.t_dec.to_numpy(np.int64)
    k = np.searchsorted(tc, t)
    assert (tc[k] == t).all()
    side = dec.side.to_numpy()
    level = np.where(side > 0, up[k], dn[k])
    trig = side * (level - own.P(t)) / a[k]
    return {"risk": dec.stop_dist.to_numpy(), "trig": trig, "vol_cur": a[k], "vol": a[k] / med_at(tc, a, t),
            "level": level}


def orb_decisions(mk, o):
    dates = pd.DatetimeIndex(o["date"])
    t07 = (dates + pd.Timedelta(hours=7)).tz_localize(gl.LDN, ambiguous="NaT", nonexistent="shift_forward")
    return pd.DataFrame({"t_dec": ns_of(t07.tz_convert("UTC")), "side": o.side.to_numpy(),
                         "risk_rule": np.abs(o.level.to_numpy() - o.stop.to_numpy()),
                         "width_rule": o.width.to_numpy()})


def _orb_widths(mk):
    """Asian range width W of every London weekday date of the frame (>= 210 range bars), known at 07:00 London"""
    ns = ns_of(mk.index)
    loc = mk.index[[0, -1]].tz_convert(gl.LDN)
    dates = pd.date_range(loc[0].tz_localize(None).normalize(), loc[1].tz_localize(None).normalize(), freq="D")
    dates = dates[dates.dayofweek < 5]
    t00 = ns_of((dates + pd.Timedelta(0)).tz_localize(gl.LDN, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC"))
    t07 = ns_of((dates + pd.Timedelta(hours=7)).tz_localize(gl.LDN, ambiguous="NaT", nonexistent="shift_forward").tz_convert("UTC"))
    i0 = np.searchsorted(ns, t00)
    i1 = np.searchsorted(ns, t07)
    ah = mk["ah"].to_numpy(np.float64)
    bl = mk["bl"].to_numpy(np.float64)
    W = np.full(len(dates), np.nan)
    for q in np.flatnonzero(i1 - i0 >= 210):
        W[q] = ah[i0[q]:i1[q]].max() - bl[i0[q]:i1[q]].min()
    return t07, W


def orb_features(mk, own, dec):
    t07, W = _orb_widths(mk)
    t = dec.t_dec.to_numpy(np.int64)
    k = np.searchsorted(t07, t)
    assert (t07[k] == t).all()
    w = W[k]
    return {"risk": dec.risk_rule.to_numpy(), "trig": w / own.atrd(t), "vol_cur": w,
            "vol": w / med_at(t07, W, t), "width": w}


FUNCS = {
    "noise30": (noise_decisions, noise_features),
    "ocm4": (ocm_decisions, ocm_features),
    "brk72_24h_wd": (brk_decisions, brk_features),
    "F1_brk_ridge_filter": (f1_decisions, f1_features),
    "nq_btc_follow": (nq_decisions, nq_features),
    "GOLD_FRI_PM": (fri_decisions, fri_features),
    "donch4h_stop": (donch_decisions, donch_features),
    "orb_asia_2d_buf10": (orb_decisions, orb_features),
}
