"""Independent re-implementation of trend/donch4h_stop as a bar-by-bar EA (no goldlab code used
except for loading the parquet).  Written from the textual rule, then compared with the engine.

EA logic (one position at a time):
  * 4h bins on the UTC grid; a bin is "closed" when the first M1 bar of the next non-empty bin
    arrives (activation bar a_k).  Mid H/L/C of a bin: (max bid-high + max ask-high)/2 etc.
  * at activation of bin k (if flat): up = max mid-high of bins k-59..k, dn = min mid-low,
    ATR = Wilder(14) on mid bins up to k.  OCO buy-stop up (trigger ask-high >= up) /
    sell-stop dn (trigger bid-low <= dn), valid through the last bar of bin k+1.
  * fill: max(up, ask-open)*(1+slip) / min(dn, bid-open)*(1-slip).  Both inside one M1 bar ->
    adverse side (as documented).  Initial stop fp -/+ 2 ATR, trail 2 ATR from best bid-high /
    ask-low, updated after each M1 bar.  Stop exit: at stop on the fill bar, else worse of
    stop / open, slip paid.
  * time exit: decision NY wall clock + 5 NY trading days - 5 min, at the OPEN of the first M1
    bar >= that time (or the last bar before a closure if the next bar is > 30 min later).
  * decision time used for the time stop: DEC="engine" -> last M1 bar of bin + 1 min (engine
    convention); DEC="boundary" -> the bin's nominal end (what an EA clock would use).
"""
import datetime as dt
import sys
from zoneinfo import ZoneInfo

import numba as nb
import numpy as np
import pandas as pd

NYZ = ZoneInfo("America/New_York")
UTCZ = dt.timezone.utc
H4 = 4 * 3600 * 10**9
MIN = 60 * 10**9


def load_raw(path="data/xauusd_m1.parquet"):
    df = pd.read_parquet(path)
    t = df.index.as_unit("ns").asi8.astype(np.int64)
    cols = {c: df[c].to_numpy(np.float64) for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")}
    return t, cols


def h4_bins(t, c, offset_ns=0):
    """Non-empty 4h bins on the UTC grid (+offset). Returns dict of arrays per bin."""
    b = (t - offset_ns) // H4
    starts = np.r_[0, np.nonzero(np.diff(b))[0] + 1]
    ends = np.r_[starts[1:], len(t)] - 1           # last M1 index in the bin
    hb = np.maximum.reduceat(c["bh"], starts)
    ha = np.maximum.reduceat(c["ah"], starts)
    lb = np.minimum.reduceat(c["bl"], starts)
    la = np.minimum.reduceat(c["al"], starts)
    cl = (c["bc"][ends] + c["ac"][ends]) / 2
    return {"bin": b[starts], "first": starts, "last": ends, "h": (hb + ha) / 2,
            "l": (lb + la) / 2, "c": cl}


def wilder_atr(h, l, c, n=14):
    out = np.full(len(h), np.nan)
    a = np.nan
    for k in range(1, len(h)):
        tr = max(h[k] - l[k], abs(h[k] - c[k - 1]), abs(l[k] - c[k - 1]))
        a = tr if np.isnan(a) else a + (tr - a) / n
        out[k] = a
    return out


def channel(h, l, n=60):
    up = pd.Series(h).rolling(n).max().to_numpy()
    dn = pd.Series(l).rolling(n).min().to_numpy()
    return up, dn


def ny_exit_times(dec_ns, max_days=5):
    """decision instants (ns UTC) -> exit instants (ns UTC): same NY wall clock - 5 min after
    max_days NY trading days (trading date = date of NY wall clock + 7 h; weekdays only)."""
    out = np.empty(len(dec_ns), np.int64)
    for k, v in enumerate(dec_ns):
        u = dt.datetime.fromtimestamp(v / 1e9, tz=UTCZ)
        ny = u.astimezone(NYZ).replace(tzinfo=None)
        shifted = ny + dt.timedelta(hours=7)
        d = shifted.date()
        if d.weekday() >= 5:            # Sat/Sun trading date rolls to Monday first
            d = d + dt.timedelta(days=7 - d.weekday())
            m = max_days - 1
        else:
            m = max_days
        while m > 0:
            d = d + dt.timedelta(days=1)
            if d.weekday() < 5:
                m -= 1
        wall = dt.datetime.combine(d, shifted.time()) - dt.timedelta(hours=7) - dt.timedelta(minutes=5)
        # localize NY (fold=0 -> first occurrence for ambiguous; nonexistent shifted by zoneinfo)
        out[k] = int(wall.replace(tzinfo=NYZ).astimezone(UTCZ).timestamp()) * 10**9
    return out


def exit_bar(t, x_ns, max_gap_min=30):
    xi = np.searchsorted(t, x_ns, side="left")
    nxt = t[np.clip(xi, 0, len(t) - 1)]
    gap = (xi >= len(t)) | ((nxt - x_ns) > max_gap_min * MIN)
    return np.where(gap & (xi > 0), xi - 1, xi).astype(np.int64)


@nb.njit(cache=False)
def ea_loop(bo, bh, bl, bc, ao, ah, al, ac, act, exp_, up, dn, atr, xbar, slip, stop_k, trail_k,
            delay, out):
    """out columns: dec_k, side, fill_i, fill_px, exit_i, exit_px, reason(0 stop,3 trail,2 time,4 eod),
    tie flag, stop_dist."""
    N = len(bo)
    nt = 0
    last_exit = -1
    K = len(act)
    for k in range(K):
        a0 = act[k] + delay
        if a0 >= N or not np.isfinite(up[k]) or not np.isfinite(dn[k]) or not np.isfinite(atr[k]):
            continue
        if a0 <= last_exit:          # not flat at the decision
            continue
        e = min(exp_[k], N - 1)
        fi = -1
        s = 0
        tie = 0
        for i in range(a0, e + 1):
            hu = ah[i] >= up[k]
            hd = bl[i] <= dn[k]
            if hu and hd:
                tie = 1
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
            fp = max(up[k], ao[fi]) * (1 + slip)
        else:
            fp = min(dn[k], bo[fi]) * (1 - slip)
        sd = atr[k] * stop_k
        tr = atr[k] * trail_k
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
                if bl[i] <= cur:
                    px = cur if i == fi else min(cur, bo[i])
                    xi = i
                    xp = px * (1 - slip)
                    rs = 3 if moved else 0
                    break
                if bh[i] > best:
                    best = bh[i]
                if best - tr > cur:
                    cur = best - tr
                    moved = True
            else:
                if ah[i] >= cur:
                    px = cur if i == fi else max(cur, ao[i])
                    xi = i
                    xp = px * (1 + slip)
                    rs = 3 if moved else 0
                    break
                if al[i] < best:
                    best = al[i]
                if best + tr < cur:
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
        out[nt, 7] = tie
        out[nt, 8] = sd
        nt += 1
        last_exit = xi
    return nt


def swap_nights(entry_ns, exit_ns, exit_is_time):
    """Count 17:00 NY rollovers strictly inside (entry, exit); Wednesday counts 3."""
    out = np.zeros(len(entry_ns))
    for k in range(len(entry_ns)):
        a = dt.datetime.fromtimestamp(entry_ns[k] / 1e9, tz=UTCZ).astimezone(NYZ)
        # exit instant: TIME exits happen at the bar open, others at the end of the bar
        xe = exit_ns[k] + (0 if exit_is_time[k] else MIN)
        b = dt.datetime.fromtimestamp(xe / 1e9, tz=UTCZ).astimezone(NYZ)
        d = a.date()
        n = 0.0
        while True:
            ro = dt.datetime.combine(d, dt.time(17, 0)).replace(tzinfo=NYZ)
            if ro >= b:
                break
            if ro > a and d.weekday() < 5:
                n += 3 if d.weekday() == 2 else 1
            d = d + dt.timedelta(days=1)
        out[k] = n
    return out


def run(t, c, n=60, atr_n=14, stop_k=2.0, trail_k=2.0, slip_bps=1.5, comm=0.07, swl=0.05, sws=0.02,
        dec="engine", delay=0, offset_ns=0, level_src="mid"):
    b = h4_bins(t, c, offset_ns)
    if level_src == "mid":
        hh, ll = b["h"], b["l"]
    else:
        raise ValueError(level_src)
    up, dn = channel(hh, ll, n)
    atr = wilder_atr(b["h"], b["l"], b["c"], atr_n)
    act = b["last"] + 1                         # first M1 bar of the next non-empty bin
    exp_ = np.r_[b["last"][1:], len(t) - 1]     # last M1 bar of the next bin
    if dec == "engine":
        dec_ns = t[b["last"]] + MIN
    else:
        dec_ns = (b["bin"] + 1) * H4 + offset_ns
    x_ns = ny_exit_times(dec_ns)
    xbar = exit_bar(t, x_ns)
    out = np.zeros((len(act), 9))
    nt = ea_loop(c["bo"], c["bh"], c["bl"], c["bc"], c["ao"], c["ah"], c["al"], c["ac"],
                 act.astype(np.int64), exp_.astype(np.int64), up, dn, atr, xbar,
                 slip_bps * 1e-4, stop_k, trail_k, delay, out)
    o = out[:nt]
    tr = pd.DataFrame({"k": o[:, 0].astype(int), "side": o[:, 1].astype(int),
                       "fill_i": o[:, 2].astype(int), "entry": o[:, 3], "exit_i": o[:, 4].astype(int),
                       "exit": o[:, 5], "reason": o[:, 6].astype(int), "tie": o[:, 7].astype(int),
                       "stop_dist": o[:, 8]})
    tr["entry_time"] = pd.to_datetime(t[tr.fill_i], utc=True)
    is_time = (tr.reason == 2).to_numpy()
    tr["exit_time"] = pd.to_datetime(t[tr.exit_i] + np.where(is_time, 0, MIN), utc=True)
    nights = swap_nights(t[tr.fill_i], t[tr.exit_i], is_time)
    rate = np.where(tr.side > 0, swl, sws)
    tr["swap"] = tr.entry * rate / 360.0 * nights
    tr["pnl"] = tr.side * (tr.exit - tr.entry) - tr.swap - comm
    tr["R"] = tr.pnl / tr.stop_dist
    tr["dec_ns"] = dec_ns[tr.k]
    tr["up"] = up[tr.k]
    tr["dn"] = dn[tr.k]
    tr["atr"] = atr[tr.k]
    return tr


def pf(R):
    R = np.asarray(R)
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return g / l if l > 0 else np.nan


def tstat(R):
    R = np.asarray(R)
    return R.mean() / (R.std(ddof=1) / np.sqrt(len(R)))
