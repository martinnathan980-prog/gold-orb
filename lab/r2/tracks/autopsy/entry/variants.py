"""Addendum H, lens `entry` -- the entry decisions of the declared variants and the legs they produce.

Every decision is made by a small function that only reads the price arrays it is given, bar by bar from the bar
where the order is placed; the truncation test (s4_truncation.py) calls the SAME functions on arrays cut right after
the decision bar.  Bars are labelled by their start; a bar is known at its close; a decision taken on the close of
bar c is executed at the open of bar c+1 (market slippage), a resting limit fills inside the bar that reaches it
(lab rule: buy when the ask low <= level, at min(level, ask open); sell when the bid high >= level, at
max(level, bid open)).
"""
import numpy as np

from common import MIN_NS, nb, pd

BIG = np.iinfo(np.int64).max // 4


# ------------------------------------------------------------------------------------------- single-signal decisions
@nb.njit(cache=True)
def lim_touch(al, bh, side, level, a, b):
    """First bar j in [a, b] where a resting limit fills (buy: ask low <= level; sell: bid high >= level), else -1."""
    n = len(al)
    hi = min(b, n - 1)
    for j in range(a, hi + 1):
        if side > 0:
            if al[j] <= level:
                return j
        else:
            if bh[j] >= level:
                return j
    return -1


@nb.njit(cache=True)
def stop_touch(bl, ah, side, stop, a, b):
    """First bar j in [a, b] where the rule's stop price is touched (long: bid low <= stop; short: ask high >= stop)."""
    n = len(bl)
    hi = min(b, n - 1)
    for j in range(a, hi + 1):
        if side > 0:
            if bl[j] <= stop:
                return j
        else:
            if ah[j] >= stop:
                return j
    return -1


@nb.njit(cache=True)
def conf1(mo, mc, side, a, b):
    """First M1 bar j in [a, b] whose mid close is beyond its mid open in the trade's direction, else -1."""
    n = len(mo)
    hi = min(b, n - 1)
    for j in range(a, hi + 1):
        if side * (mc[j] - mo[j]) > 0:
            return j
    return -1


@nb.njit(cache=True)
def conf_block(ns, mo, mc, side, a, t0, tf_ns, t_end, t_now):
    """First block [t0 + m tf, t0 + (m+1) tf) lying inside [t0, t_end) and complete by the clock t_now, whose mid close
    (close of its last bar) is beyond its mid open (open of its first bar) in the trade's direction.  Blocks without
    bars are skipped.  Returns (first bar, last bar, block end time) or (-1, -1, 0)."""
    n = len(ns)
    j = a
    m = 0
    while True:
        bs = t0 + m * tf_ns
        be = bs + tf_ns
        if be > t_end or be > t_now:
            return -1, -1, 0
        while j < n and ns[j] < bs:
            j += 1
        if j >= n:
            return -1, -1, 0
        if ns[j] >= be:
            m += 1
            continue
        f = j
        k = j
        while k + 1 < n and ns[k + 1] < be:
            k += 1
        if side * (mc[k] - mo[f]) > 0:
            return f, k, be
        j = k + 1
        m += 1


# ------------------------------------------------------------------------------------------- vectorised over signals
@nb.njit(cache=True)
def k_lim(al, bh, side, level, a, b):
    out = np.full(len(side), -1, np.int64)
    for s in range(len(side)):
        if a[s] >= 0 and b[s] >= a[s]:
            out[s] = lim_touch(al, bh, side[s], level[s], a[s], b[s])
    return out


@nb.njit(cache=True)
def k_stop(bl, ah, side, stop, a, b):
    out = np.full(len(side), -1, np.int64)
    for s in range(len(side)):
        if a[s] >= 0 and b[s] >= a[s]:
            out[s] = stop_touch(bl, ah, side[s], stop[s], a[s], b[s])
    return out


@nb.njit(cache=True)
def k_conf1(mo, mc, side, a, b):
    out = np.full(len(side), -1, np.int64)
    for s in range(len(side)):
        if a[s] >= 0 and b[s] >= a[s]:
            out[s] = conf1(mo, mc, side[s], a[s], b[s])
    return out


@nb.njit(cache=True)
def k_conf_block(ns, mo, mc, side, a, t0, tf_ns, t_end):
    f = np.full(len(side), -1, np.int64)
    k = np.full(len(side), -1, np.int64)
    be = np.zeros(len(side), np.int64)
    for s in range(len(side)):
        if a[s] >= 0 and t_end[s] > t0[s]:
            f[s], k[s], be[s] = conf_block(ns, mo, mc, side[s], a[s], t0[s], tf_ns, t_end[s], BIG)
    return f, k, be


# ------------------------------------------------------------------------------------------- the signals of a rule
def signal_table(name, sym, o, lo, A, c):
    """Per signal (one row of the rule's order table): side, activation bar, exit bar, trail, P0, D, S0, and the
    reference bars of each family.  `c` = the run's costs (slippages)."""
    n = len(A["ns"])
    side = lo.side.to_numpy(np.int64)
    act = lo.entry_i.to_numpy(np.int64)
    exit_i = lo.exit_i.to_numpy(np.int64)
    exit_c = np.where(exit_i >= 0, exit_i, n)
    sm, ss = c.slip_mkt_bps * 1e-4, c.slip_bps * 1e-4
    ok = act < n
    ac = np.minimum(act, n - 1)
    S = pd.DataFrame({"side": side, "act": act, "exit_i": exit_i, "exit_c": exit_c, "ok": ok,
                      "trail": lo.trail.to_numpy(float)}, index=np.arange(len(lo)))
    if name in ("donch4h_stop", "orb_asia_2d_buf10"):
        trig = (o["trig_i"] if name == "donch4h_stop" else o["entry_i"]).to_numpy(np.int64)
        lv = lo.level.to_numpy(float)
        tc = np.minimum(trig, n - 1)
        F = np.where(side > 0, np.maximum(lv, A["ao"][tc]) * (1 + ss), np.minimum(lv, A["bo"][tc]) * (1 - ss))
        D = np.where(np.isfinite(lo.stop_dist.to_numpy(float)), lo.stop_dist.to_numpy(float),
                     np.abs(F - lo.stop.to_numpy(float)))
        S["trig"] = trig
        S["level"] = lv
        S["P0"] = F
        S["D"] = D
        S["S0"] = F - side * D
        S["ok"] = ok & (trig < n)
    elif name == "GOLD_FRI_PM":
        L0 = lo.level.to_numpy(float)
        D = lo.stop_dist.to_numpy(float)
        S["level"] = L0
        S["P0"] = L0
        S["D"] = D
        S["S0"] = L0 - side * D
        S["expiry_i"] = lo.expiry_i.to_numpy(np.int64)
    else:
        P0 = np.where(side > 0, A["ao"][ac] * (1 + sm), A["bo"][ac] * (1 - sm))
        sd = lo.stop_dist.to_numpy(float)
        D = np.where(np.isfinite(sd), sd, np.abs(P0 - lo.stop.to_numpy(float)))
        S["P0"] = P0
        S["D"] = D
        S["S0"] = P0 - side * D
    return S


def window_end(ns, t_start, minutes, exit_c):
    """Last bar starting in [t_start, t_start + minutes) and before the exit bar; and the first bar at or after the
    window's end (the fallback bar)."""
    t_end = t_start + np.int64(minutes) * MIN_NS
    w_end = np.searchsorted(ns, t_end, side="left").astype(np.int64) - 1
    fb = np.searchsorted(ns, t_end, side="left").astype(np.int64)
    return np.minimum(w_end, exit_c - 1), fb, t_end


def entry_side_open(A, side, j, c):
    n = len(A["ns"])
    jc = np.minimum(np.maximum(j, 0), n - 1)
    sm = c.slip_mkt_bps * 1e-4
    return np.where(side > 0, A["ao"][jc] * (1 + sm), A["bo"][jc] * (1 - sm))


def _legs(sig, entry_i, side, etype, level, expiry_i, stop, stop_dist, exit_i, trail, leg, w):
    n = len(sig)
    f = lambda x, dt=float: np.broadcast_to(np.asarray(x, dtype=dt), (n,)).copy()  # noqa: E731
    return pd.DataFrame({"entry_i": f(entry_i, np.int64), "side": f(side, np.int64), "etype": f(etype, np.int64),
                         "level": f(level), "expiry_i": f(expiry_i, np.int64), "stop": f(stop),
                         "stop_dist": f(stop_dist), "target": np.nan, "target_dist": np.nan,
                         "exit_i": f(exit_i, np.int64), "trail": f(trail), "be": np.nan,
                         "sig": f(sig, np.int64), "leg": f(leg, np.int64), "w": f(w)})


def stop_cols(mode, S0, D, idx):
    if mode == "price":
        return S0[idx], np.nan
    return np.nan, D[idx]


def build(name, v, mode, S, lo, A, c):
    """Legs and signal holds of one declared variant (v: dict from declared.json) in one stop mode.
    Returns legs (lab orders + sig/leg/w), hold (per signal), info (per-signal decision bars for checks)."""
    ns = A["ns"]
    n = len(ns)
    mo = (A["bo"] + A["ao"]) / 2
    mc = (A["bc"] + A["ac"]) / 2
    side = S.side.to_numpy(np.int64)
    act = S.act.to_numpy(np.int64)
    exit_c = S.exit_c.to_numpy(np.int64)
    exit_i = S.exit_i.to_numpy(np.int64)
    trail = S.trail.to_numpy(float)
    P0, D, S0 = S.P0.to_numpy(float), S.D.to_numpy(float), S.S0.to_numpy(float)
    ok = S.ok.to_numpy(bool)
    nsg = len(S)
    sig = np.arange(nsg, dtype=np.int64)
    hold = np.full(nsg, -1, np.int64)
    info = {}
    fam = v["family"]
    gold = name == "GOLD_FRI_PM"
    rt = fam in ("RT", "HALFRT")

    # placement bar a and window
    if rt:
        trig = S.trig.to_numpy(np.int64)
        a = np.where(ok, trig + 1, n)
        t_start = ns[np.minimum(trig, n - 1)] + MIN_NS
        w_end, fb, t_end = window_end(ns, t_start, v["N_min"], exit_c)
    elif gold:
        a = np.where(ok, act, n)
        exp_i = S.expiry_i.to_numpy(np.int64)
        w_end = np.minimum(exp_i, exit_c - 1)
        t_end = ns[np.minimum(exp_i, n - 1)] + MIN_NS
        fb = np.searchsorted(ns, t_end, side="left").astype(np.int64)
        t_start = ns[np.minimum(act, n - 1)]
    else:
        a = np.where(ok, act, n)
        t_start = ns[np.minimum(act, n - 1)]
        w_end, fb, t_end = window_end(ns, t_start, v["N_min"], exit_c)
    valid = ok & (a < n) & (w_end >= a)
    info.update(a=a, w_end=w_end, fb=fb, t_end=t_end, valid=valid)

    parts = []
    if fam in ("LIM", "HALF", "RT", "HALFRT"):
        if rt:
            level = S.level.to_numpy(float)
        elif gold:
            k = v["k"]
            level = S.level.to_numpy(float) - side * k * D
        else:
            k = v["k"]
            level = P0 - side * k * D
        j = k_lim(A["al"], A["bh"], side, level, np.where(valid, a, -1), w_end)
        info.update(level=level, fill_bar=j)
        hold = np.where(valid, w_end, -1)
        filled = valid & (j >= 0)
        idx = np.where(filled)[0]
        st, sd = stop_cols(mode, S0, D, idx)
        parts.append(_legs(sig[idx], a[idx], side[idx], 2, level[idx], w_end[idx], st, sd, exit_i[idx], trail[idx],
                           1, 0.5 if fam in ("HALF", "HALFRT") else 1.0))
        if v.get("fallback") == "market":
            miss = valid & (j < 0) & (fb < exit_c) & (fb < n)
            pf = entry_side_open(A, side, fb, c)
            if mode == "price":
                miss &= side * (pf - S0) > 0
            idx = np.where(miss)[0]
            st, sd = stop_cols(mode, S0, D, idx)
            parts.append(_legs(sig[idx], fb[idx], side[idx], 0, np.nan, -1, st, sd, exit_i[idx], trail[idx], 2, 1.0))
            info["fallback"] = miss
        if fam in ("HALF", "HALFRT"):
            idx = np.where(ok)[0]
            rl = lo.iloc[idx]
            parts.append(_legs(sig[idx], rl.entry_i.to_numpy(), rl.side.to_numpy(), rl.etype.to_numpy(),
                               rl.level.to_numpy(float), rl.expiry_i.to_numpy(), rl.stop.to_numpy(float),
                               rl.stop_dist.to_numpy(float), rl.exit_i.to_numpy(), rl.trail.to_numpy(float), 0, 0.5))
    elif fam == "CONF":
        if v["tf_min"] == 1:
            cb = k_conf1(mo, mc, side, np.where(valid, a, -1), w_end)
            c_last = cb
            e = np.where(cb >= 0, cb + 1, -1)
        else:
            tf_ns = np.int64(v["tf_min"]) * MIN_NS
            t_end_c = np.minimum(t_end, ns[np.minimum(np.maximum(exit_c - 1, 0), n - 1)] + MIN_NS)
            f5, k5, be5 = k_conf_block(ns, mo, mc, side, np.where(valid, a, -1), t_start, tf_ns,
                                       np.where(valid, t_end_c, 0))
            c_last = k5
            e = np.where(k5 >= 0, np.searchsorted(ns, be5, side="left"), -1)
            info.update(block_first=f5, block_end=be5)
        v_full = k_stop(A["bl"], A["ah"], side, S0, np.where(valid, a, -1), w_end)
        conf = valid & (c_last >= 0)
        cancel = conf & (v_full >= 0) & (v_full <= c_last)
        go = conf & ~cancel & (e < exit_c) & (e < n)
        pe = entry_side_open(A, side, e, c)
        if mode == "price":
            go &= side * (pe - S0) > 0
        hold = np.where(~valid, -1, np.where(conf & ~cancel, c_last,
                        np.where(cancel, v_full, np.where(v_full >= 0, v_full, w_end))))
        info.update(conf_bar=c_last, entry_bar=e, stop_bar=v_full, go=go, cancel=cancel)
        idx = np.where(go)[0]
        st, sd = stop_cols(mode, S0, D, idx)
        parts.append(_legs(sig[idx], e[idx], side[idx], 0, np.nan, -1, st, sd, exit_i[idx], trail[idx], 1, 1.0))
    else:
        raise ValueError(fam)
    legs = pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else \
        _legs(np.zeros(0, np.int64), 0, 0, 0, np.nan, -1, np.nan, np.nan, -1, np.nan, 0, 1.0)
    return legs, hold, info
