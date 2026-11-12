"""Order transformations of the payoff lens (see declared.json for the definitions).

info(name, sym, m1, O, stress, params) -> DataFrame aligned with the base orders O (one row per order):
    fb, fp      fill bar / fill price, exactly as the simulator computes them (-1 / NaN: never fills)
    r0          the rule's initial risk |fp - stop| (stop_dist for distance stops)
    spread      ask - bid of the fill bar (the broker's minimum stop is 3 x this)
    unit        the rule's own volatility unit (price)
    clock       True if the order's exit_i is the rule's clock exit
    x_clock     UTC time of the scheduled clock exit
    ext1, ext2  exit bar after holding 1 / 2 more sessions (H)
    cap         time-cap bar of the trailing variants (T)
"""
import numpy as np
import pandas as pd

import common as C
import goldlab as gl

ABS_STOP = {"noise30", "orb_asia_2d_buf10"}      # rules whose stop is an absolute price


def _bday(dates, j):
    return pd.DatetimeIndex(dates).normalize() + pd.offsets.BDay(int(j))


def _xi(m1, times):
    return gl.exit_index(m1, pd.DatetimeIndex(times))


def noise_detail(mo, m1, params):
    """Re-run the noise30 state machine (same code path as idx_us/strategy.py::_noise) to recover, for every order,
    the band half-width at its entry check and whether its exit is the 15:55 clock exit.  Asserted equal to the
    rule's own orders."""
    g_ = mo.__globals__
    cm = g_["cm"]
    p = g_["resolve"](params)
    p.pop("rule")
    lookback, first_min, step, last_min, exit_min, vm = (p[k] for k in ("lookback", "first_min", "step", "last_min",
                                                                        "exit_min", "vm"))
    g = cm.grid(m1)
    EI, P, O = g["EI"], g["P"], g["O"]
    checks = np.arange(first_min - 570, last_min - 570 + 1, step)
    absmove = np.abs(P[:, checks] / O[:, None] - 1)
    sig = pd.DataFrame(absmove).rolling(lookback, min_periods=max(int(0.7 * lookback), 1)).mean().shift(1).to_numpy()
    cl = P[:, 390]
    pc = np.r_[np.nan, cl[:-1]]
    hi_ref = np.where(np.isfinite(pc), np.fmax(O, pc), O)
    lo_ref = np.where(np.isfinite(pc), np.fmin(O, pc), O)
    xi = g_["_exit_index"](m1, g, exit_min)
    ok = g_["_session_ok"](g) & np.isfinite(O)
    rows = []
    for d in np.flatnonzero(ok):
        pos, open_k = 0, -1
        for j, m in enumerate(checks):
            pp, s, ei = P[d, m], sig[d, j], EI[d, m]
            if not (np.isfinite(pp) and np.isfinite(s)) or ei < 0 or ei >= xi[d]:
                continue
            ub, lb = hi_ref[d] * (1 + vm * s), lo_ref[d] * (1 - vm * s)
            if pos != 0 and ((pos > 0 and pp < ub) or (pos < 0 and pp > lb)):
                rows[open_k][3] = ei
                pos = 0
                ei += 1
            if pos == 0 and ei < xi[d]:
                if pp > ub or pp < lb:
                    pos = 1 if pp > ub else -1
                    unit = hi_ref[d] * vm * s if pos > 0 else lo_ref[d] * vm * s
                    rows.append([ei, pos, hi_ref[d] if pos > 0 else lo_ref[d], xi[d], unit, xi[d], d])
                    open_k = len(rows) - 1
    r = pd.DataFrame(rows, columns=["entry_i", "side", "stop", "exit_i", "unit", "x1555", "d"])
    r = r.sort_values("entry_i", kind="stable").reset_index(drop=True)
    dl = np.asarray(g["dates"])[r["d"].to_numpy()]
    r["date"] = pd.to_datetime([pd.Timestamp(x) for x in dl]) if len(dl) else pd.DatetimeIndex([])
    return r


def info(name, sym, m1, O, stress, params, mo):
    n = len(O)
    fb, fp = C.fills(m1, O, sym, stress)
    side = O["side"].to_numpy()
    ao, bo = m1["ao"].to_numpy(), m1["bo"].to_numpy()
    spread = np.where(fb >= 0, ao[np.clip(fb, 0, len(m1) - 1)] - bo[np.clip(fb, 0, len(m1) - 1)], np.nan)
    if name in ABS_STOP:
        r0 = side * (fp - O["stop"].to_numpy())
    else:
        r0 = O["stop_dist"].to_numpy(float).copy()
    df = pd.DataFrame({"fb": fb, "fp": fp, "r0": r0, "spread": spread}, index=O.index)
    idx = m1.index
    ent_t = idx[np.clip(O["entry_i"].to_numpy(), 0, len(m1) - 1)]
    clock = np.ones(n, bool)
    if name == "noise30":
        nd = noise_detail(mo, m1, params)
        assert len(nd) == n
        for c_ in ("entry_i", "side", "exit_i"):
            assert (nd[c_].to_numpy() == O[c_].to_numpy()).all(), c_
        assert np.allclose(nd["stop"].to_numpy(), O["stop"].to_numpy(), rtol=0, atol=0)
        df["unit"] = nd["unit"].to_numpy()
        clock = nd["exit_i"].to_numpy() == nd["x1555"].to_numpy()
        date = nd["date"]
        df["x_clock"] = C.ny_clock(date, 15, 55)
        times = [C.ny_clock(_bday(date, j), 15, 55) for j in (1, 2, 4)]
        ext = [_xi(m1, C.ny_clock(_bday(date, j), 15, 55)) for j in (1, 2)]
        cap = _xi(m1, C.ny_clock(_bday(date, 4), 15, 55))
    elif name == "ocm4":
        df["unit"] = O["stop_dist"].to_numpy() / 0.3
        date = ent_t.tz_convert(C.NY).tz_localize(None).normalize()
        df["x_clock"] = C.ny_clock(date, 15, 55)
        times = [C.ny_clock(_bday(date, j), 15, 55) for j in (1, 2, 4)]
        ext = [_xi(m1, C.ny_clock(_bday(date, j), 15, 55)) for j in (1, 2)]
        cap = _xi(m1, C.ny_clock(_bday(date, 4), 15, 55))
    elif name == "brk72_24h_wd":
        df["unit"] = O["atr"].to_numpy()
        sx = pd.DatetimeIndex(O["sched_exit"])
        df["x_clock"] = sx
        fri = C.friday_close_bar(m1, ent_t)
        times = [sx + pd.Timedelta(hours=24 * j) for j in (1, 2)] + [C.friday_close_time(ent_t)]
        ext = [np.minimum(_xi(m1, sx + pd.Timedelta(hours=24 * j)), fri) for j in (1, 2)]
        cap = fri
    elif name == "F1_brk_ridge_filter":
        df["unit"] = O["stop_dist"].to_numpy() / 2.0
        tdec = pd.DatetimeIndex(pd.to_datetime(O["cid"].to_numpy(), utc=True))
        date = tdec.tz_convert(C.NY).tz_localize(None).normalize()
        df["x_clock"] = C.ny_clock(date, 15, 55)
        fri = C.friday_close_bar(m1, ent_t)
        times = [C.ny_clock(_bday(date, j), 15, 55) for j in (1, 2)] + [C.friday_close_time(ent_t)]
        ext = [np.minimum(_xi(m1, C.ny_clock(_bday(date, j), 15, 55)), fri) for j in (1, 2)]
        cap = fri
    elif name == "nq_btc_follow":
        df["unit"] = O["stop_dist"].to_numpy() / 2.0
        df["x_clock"] = ent_t + pd.Timedelta(minutes=60)
        fri = C.friday_close_bar(m1, ent_t)
        times = [ent_t + pd.Timedelta(minutes=60 * (1 + j)) for j in (1, 2)] + [C.friday_close_time(ent_t)]
        ext = [np.minimum(_xi(m1, ent_t + pd.Timedelta(minutes=60 * (1 + j))), fri) for j in (1, 2)]
        cap = fri
    elif name == "GOLD_FRI_PM":
        df["unit"] = O["stop_dist"].to_numpy() / 3.0
        date = ent_t.tz_convert(C.NY).tz_localize(None).normalize()
        df["x_clock"] = C.ny_clock(date, 16, 45)
        times = [C.ny_clock(_bday(date, j), 16, 45) for j in (1, 2, 4)]
        ext = [_xi(m1, C.ny_clock(_bday(date, j), 16, 45)) for j in (1, 2)]
        cap = _xi(m1, C.ny_clock(_bday(date, 4), 16, 45))
    elif name == "orb_asia_2d_buf10":
        df["unit"] = O["width"].to_numpy()
        date = pd.DatetimeIndex(O["date"])
        df["x_clock"] = C.ny_clock(_bday(date, 2), 16, 0)
        times = [C.ny_clock(_bday(date, j), 16, 0) for j in (3, 4, 4)]
        ext = [_xi(m1, C.ny_clock(_bday(date, 2 + j), 16, 0)) for j in (1, 2)]
        cap = _xi(m1, C.ny_clock(_bday(date, 4), 16, 0))
    elif name == "donch4h_stop":
        df["unit"] = O["atr"].to_numpy()
        clock = np.zeros(n, bool)
        df["x_clock"] = pd.NaT
        times = [pd.DatetimeIndex([pd.NaT] * n, tz="UTC")] * 3
        ext = [O["exit_i"].to_numpy(), O["exit_i"].to_numpy()]
        cap = O["exit_i"].to_numpy()
    else:
        raise ValueError(name)
    df["clock"] = clock
    df["ext1_t"], df["ext2_t"], df["cap_t"] = (pd.DatetimeIndex(x) for x in times)
    df["ext1"], df["ext2"] = (np.asarray(e, np.int64) for e in ext)
    df["cap"] = np.asarray(cap, np.int64)
    # an extension / cap can only lengthen a clock exit, never shorten it (guards against a closure mapping back)
    xi0 = O["exit_i"].to_numpy()
    for c_ in ("ext1", "ext2", "cap"):
        df[c_] = np.where(df["clock"], np.maximum(df[c_].to_numpy(), xi0), xi0)
    return df


# ----------------------------------------------------------------------------------------- transformations
def _set_stop(o, name, d0):
    if name in ABS_STOP:
        o["stop"] = np.nan
    o["stop_dist"] = d0
    return o


def refuse(d0, spread):
    """Broker minimum: stop closer than 3 spreads -> not taken (orders that never fill have no spread)."""
    return np.isfinite(spread) & (d0 < 3.0 * spread)


def S(O, I, name, k):
    o = O.copy()
    d0 = k * I["r0"].to_numpy()
    o = _set_stop(o, name, d0)
    if name == "donch4h_stop":
        o["trail"] = k * O["trail"].to_numpy()
    return o, d0


def T(O, I, name, m):
    o = O.copy()
    tr = m * I["unit"].to_numpy()
    d0 = np.minimum(I["r0"].to_numpy(), tr)
    o = _set_stop(o, name, d0)
    o["trail"] = tr
    o["exit_i"] = np.where(I["clock"].to_numpy(), I["cap"].to_numpy(), O["exit_i"].to_numpy()).astype(np.int64)
    return o, d0


def B(O, I, name, b):
    o = O.copy()
    o["be"] = b * I["r0"].to_numpy()
    return o, I["r0"].to_numpy().copy()


def hold_decision(m1, O, I, sym, stress):
    """For every order, simulated alone: still open at the close of the bar before its clock exit bar, and ahead by
    >= 1 R0 at that close on its exit side?  Returns a boolean array aligned with O."""
    t1 = C.sim(m1, O, sym, stress, no_overlap=False)
    ahead = np.zeros(len(O), bool)
    if not len(t1):
        return ahead
    rows = t1.index.to_numpy()
    xb = C.exit_bar(m1, t1)
    xi = O["exit_i"].to_numpy()[rows]
    at_clock = (t1["reason"].to_numpy() == "time") & (xb == xi) & I["clock"].to_numpy()[rows]
    c = np.clip(xb - 1, 0, len(m1) - 1)
    s = t1["side"].to_numpy()
    mark = np.where(s > 0, m1["bc"].to_numpy()[c], m1["ac"].to_numpy()[c])
    gain = s * (mark - t1["entry"].to_numpy())
    ok = at_clock & (gain >= 1.0 * t1["risk"].to_numpy())
    # the bar before the clock bar must be a bar of the trade (the trade was filled before it)
    fbar = np.searchsorted(m1.index.values, t1.entry_time.values.astype(m1.index.values.dtype))
    ok &= c >= fbar
    ahead[rows[ok]] = True
    return ahead


def H(O, I, name, j, ahead):
    o = O.copy()
    ext = I["ext1" if j == 1 else "ext2"].to_numpy()
    o["exit_i"] = np.where(ahead, ext, O["exit_i"].to_numpy()).astype(np.int64)
    return o, I["r0"].to_numpy().copy()
