"""Generalised version of refimpl (verified identical to the engine at default settings) with probe
options: activation delay / early activation, stale levels, channel excluding the current bin,
grid offset, level source (mid / bid / ask / true per-minute mid), level noise, random delays,
trail noise, blocked fill windows, and a fast-market fill model (fraction of the fill bar's range
beyond the trigger paid as extra slippage on stop entries and stop exits)."""
import numba as nb
import numpy as np
import pandas as pd

from refimpl import H4, MIN, exit_bar, ny_exit_times, swap_nights, wilder_atr

_xcache = {}


def bins(t, c, offset_ns=0, src="mid"):
    b = (t - offset_ns) // H4
    starts = np.r_[0, np.nonzero(np.diff(b))[0] + 1]
    ends = np.r_[starts[1:], len(t)] - 1
    if src == "mid":
        h = (np.maximum.reduceat(c["bh"], starts) + np.maximum.reduceat(c["ah"], starts)) / 2
        l = (np.minimum.reduceat(c["bl"], starts) + np.minimum.reduceat(c["al"], starts)) / 2
        cl = (c["bc"][ends] + c["ac"][ends]) / 2
    elif src == "bid":
        h, l, cl = np.maximum.reduceat(c["bh"], starts), np.minimum.reduceat(c["bl"], starts), c["bc"][ends]
    elif src == "ask":
        h, l, cl = np.maximum.reduceat(c["ah"], starts), np.minimum.reduceat(c["al"], starts), c["ac"][ends]
    elif src == "minmid":        # mid of each M1 bar first, then max/min (true mid extremes)
        h = np.maximum.reduceat((c["bh"] + c["ah"]) / 2, starts)
        l = np.minimum.reduceat((c["bl"] + c["al"]) / 2, starts)
        cl = (c["bc"][ends] + c["ac"][ends]) / 2
    else:
        raise ValueError(src)
    return {"bin": b[starts], "first": starts, "last": ends, "h": h, "l": l, "c": cl}


@nb.njit(cache=False)
def loop(bo, bh, bl, bc, ao, ah, al, ac, act, exp_, up, dn, atr, xbar, slip, stop_k, trail_mult,
         nofill, ffrac_in, ffrac_out, trail_mode, dmask, upd, out):
    N = len(bo)
    nt = 0
    last_exit = -1
    for k in range(len(act)):
        a0 = act[k]
        if a0 >= N or a0 < 0 or not np.isfinite(up[k]) or not np.isfinite(dn[k]) or not np.isfinite(atr[k]):
            continue
        if a0 <= last_exit or not dmask[k]:
            continue
        e = min(exp_[k], N - 1)
        fi = -1
        s = 0
        for i in range(a0, e + 1):
            if nofill[i]:
                continue
            hu = ah[i] >= up[k]
            hd = bl[i] <= dn[k]
            if hu and hd:
                s = -1 if bc[i] >= bo[i] else 1
                fi = i
                break
            if hu:
                s = 1
                fi = i
                break
            if hd:
                s = -1
                fi = i
                break
        if fi < 0:
            continue
        if xbar[k] <= fi:
            continue
        if s > 0:
            base = max(up[k], ao[fi])
            fp = (base + ffrac_in * max(0.0, ah[fi] - base)) * (1 + slip)
        else:
            base = min(dn[k], bo[fi])
            fp = (base - ffrac_in * max(0.0, base - bl[fi])) * (1 - slip)
        sd = atr[k] * stop_k
        tr = atr[k] * 2.0 * trail_mult[k]
        cur = fp - s * sd
        best = fp
        moved = False
        xi = -1
        xp = np.nan
        rs = 4
        i = fi
        while i < N:
            if i >= xbar[k] and i > fi:
                xi = i
                xp = bo[i] * (1 - slip) if s > 0 else ao[i] * (1 + slip)
                rs = 2
                break
            if s > 0:
                if trail_mode == 1 or (trail_mode == 3 and bc[i] < bo[i]):   # intrabar (tick-like) trailing, high first then low
                    if i != fi and bo[i] <= cur:          # gap through the stop in force at the open
                        xi = i
                        xp = bo[i] * (1 - slip)
                        rs = 3 if moved else 0
                        break
                    if bh[i] > best:
                        best = bh[i]
                    if best - tr > cur:
                        cur = best - tr
                        moved = True
                    if bl[i] <= cur:
                        xi = i
                        xp = (cur - ffrac_out * max(0.0, cur - bl[i])) * (1 - slip)
                        rs = 3 if moved else 0
                        break
                    i += 1
                    continue
                if bl[i] <= cur:
                    px = cur if i == fi else min(cur, bo[i])
                    px = px - ffrac_out * max(0.0, px - bl[i])
                    xi = i
                    xp = px * (1 - slip)
                    rs = 3 if moved else 0
                    break
                if bh[i] > best:
                    best = bh[i]
                if best - tr > cur and (trail_mode != 2 or best - fp >= tr) and (trail_mode != 4 or upd[i]):
                    cur = best - tr
                    moved = True
            else:
                if trail_mode == 1 or (trail_mode == 3 and ac[i] > ao[i]):
                    if i != fi and ao[i] >= cur:
                        xi = i
                        xp = ao[i] * (1 + slip)
                        rs = 3 if moved else 0
                        break
                    if al[i] < best:
                        best = al[i]
                    if best + tr < cur:
                        cur = best + tr
                        moved = True
                    if ah[i] >= cur:
                        xi = i
                        xp = (cur + ffrac_out * max(0.0, ah[i] - cur)) * (1 + slip)
                        rs = 3 if moved else 0
                        break
                    i += 1
                    continue
                if ah[i] >= cur:
                    px = cur if i == fi else max(cur, ao[i])
                    px = px + ffrac_out * max(0.0, ah[i] - px)
                    xi = i
                    xp = px * (1 + slip)
                    rs = 3 if moved else 0
                    break
                if al[i] < best:
                    best = al[i]
                if best + tr < cur and (trail_mode != 2 or fp - best >= tr) and (trail_mode != 4 or upd[i]):
                    cur = best + tr
                    moved = True
            i += 1
        if xi < 0:
            xi = N - 1
            xp = bc[N - 1] if s > 0 else ac[N - 1]
        out[nt, 0] = k
        out[nt, 1] = s
        out[nt, 2] = fi
        out[nt, 3] = fp
        out[nt, 4] = xi
        out[nt, 5] = xp
        out[nt, 6] = rs
        out[nt, 7] = sd
        nt += 1
        last_exit = xi
    return nt


def run(t, c, n=60, atr_n=14, stop_k=2.0, slip_bps=1.5, comm=0.07, swl=0.05, sws=0.02,
        delay=0, offset_ns=0, src="mid", lag=0, excl_current=False, level_noise=0.0,
        delay_rand=0, trail_noise=0.0, seed=0, nofill=None, ffrac=0.0, atr_src=None,
        spread_add=0.0, ffrac_in=None, ffrac_out=None, trail_mode=0, dec_filter=None, exp_fn=None,
        spread_mult=1.0, upd=None):
    rng = np.random.default_rng(seed)
    b = bins(t, c, offset_ns, src)
    ba = b if (atr_src is None or atr_src == src) else bins(t, c, offset_ns, atr_src)
    hser, lser = pd.Series(b["h"]), pd.Series(b["l"])
    up, dn = hser.rolling(n).max().to_numpy(), lser.rolling(n).min().to_numpy()
    if excl_current:
        up, dn = np.r_[np.nan, up[:-1]], np.r_[np.nan, dn[:-1]]
    atr = wilder_atr(ba["h"], ba["l"], ba["c"], atr_n)
    if lag:
        up, dn, atr = (np.r_[np.full(lag, np.nan), x[:-lag]] for x in (up, dn, atr))
    K = len(up)
    if level_noise:
        up = up + rng.uniform(-level_noise, level_noise, K)
        dn = dn + rng.uniform(-level_noise, level_noise, K)
    act = b["last"] + 1 + delay
    if delay_rand:
        act = act + rng.integers(0, delay_rand + 1, K)
    exp_ = np.r_[b["last"][1:], len(t) - 1]
    if exp_fn is not None:
        ov = exp_fn(t, t[b["last"]] + MIN)
        exp_ = np.where(ov >= 0, ov, exp_)
    key = (offset_ns, src, len(t))
    if key not in _xcache:
        _xcache[key] = exit_bar(t, ny_exit_times(t[b["last"]] + MIN))
    xbar = _xcache[key]
    tm = np.ones(K) if not trail_noise else 1 + rng.uniform(-trail_noise, trail_noise, K)
    nf = np.zeros(len(t), np.bool_) if nofill is None else nofill
    cc = c
    if spread_mult != 1.0:          # same transformation as goldlab.sim's cost stress
        half = (c["ac"] - c["bc"]) * (spread_mult - 1) / 2
        cc = {k_: (c[k_] - half if k_[0] == "b" else c[k_] + half) for k_ in c}
    if spread_add:
        cc = dict(c)
        for k_ in ("ao", "ah", "al", "ac"):
            cc[k_] = c[k_] + spread_add / 2
        for k_ in ("bo", "bh", "bl", "bc"):
            cc[k_] = c[k_] - spread_add / 2
    fin = ffrac if ffrac_in is None else ffrac_in
    fout = ffrac if ffrac_out is None else ffrac_out
    dmask = np.ones(K, np.bool_) if dec_filter is None else dec_filter(t[b["last"]] + MIN)
    upd_arr = np.zeros(len(t), np.bool_)
    if upd == "bin_last":
        upd_arr[b["last"]] = True
    out = np.zeros((K, 8))
    nt = loop(cc["bo"], cc["bh"], cc["bl"], cc["bc"], cc["ao"], cc["ah"], cc["al"], cc["ac"],
              act.astype(np.int64), exp_.astype(np.int64), up, dn, atr, xbar, slip_bps * 1e-4,
              stop_k, tm, nf, fin, fout, trail_mode, dmask, upd_arr, out)
    o = out[:nt]
    tr = pd.DataFrame({"k": o[:, 0].astype(int), "side": o[:, 1].astype(int), "fill_i": o[:, 2].astype(int),
                       "entry": o[:, 3], "exit_i": o[:, 4].astype(int), "exit": o[:, 5],
                       "reason": o[:, 6].astype(int), "stop_dist": o[:, 7]})
    tr["entry_time"] = pd.to_datetime(t[tr.fill_i], utc=True)
    is_time = (tr.reason == 2).to_numpy()
    tr["exit_time"] = pd.to_datetime(t[tr.exit_i] + np.where(is_time, 0, MIN), utc=True)
    nights = swap_nights(t[tr.fill_i], t[tr.exit_i], is_time)
    tr["swap"] = tr.entry * np.where(tr.side > 0, swl, sws) / 360.0 * nights
    tr["pnl"] = tr.side * (tr.exit - tr.entry) - tr.swap - comm
    tr["R"] = tr.pnl / tr.stop_dist
    return tr


def stats(tr):
    R = tr.R.to_numpy()
    if len(R) < 3:
        return {"n": len(R)}
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return {"n": int(len(R)), "pf": round(float(g / l), 3), "exp": round(float(R.mean()), 4),
            "t": round(float(R.mean() / (R.std(ddof=1) / np.sqrt(len(R)))), 2),
            "long_R": round(float(R[tr.side.to_numpy() > 0].sum()), 1),
            "short_R": round(float(R[tr.side.to_numpy() < 0].sum()), 1)}


def split(tr):
    is_ = tr[(tr.entry_time >= "2013-01-01") & (tr.entry_time < "2022-01-01")]
    return is_
