"""Tick-by-tick re-simulation of orders, to measure how much the M1-bar simulator flatters
(or penalises) a given strategy.  Uses the Dukascopy XAUUSD tick files (Jun-Dec 2025, days
1-27 of each month).  Same order semantics as goldlab.sim, evaluated tick by tick:

  * market: first tick >= activation, long at ask / short at bid
  * stop entry: first tick in [activation, expiry) with ask >= level (long) / bid <= level (short),
    filled at that tick's quote (so gaps through the level are paid)
  * limit entry: ask <= level (long) / bid >= level (short), filled at that tick's quote
  * exits: stop at the triggering tick's quote; target at the target price; time exit at the
    first tick >= exit time; trailing / break-even updated at each MINUTE boundary with the
    minute's extreme (same rule as the M1 simulator).
No slippage / commission / swap here: compare like with like (M1 run with zero costs).
"""
import glob
import os

import numba as nb
import numpy as np
import pandas as pd

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "download")


def load_ticks():
    fr = []
    for f in sorted(glob.glob(os.path.join(RAW, "xauusd-tick-2025-*.csv.gz"))):
        fr.append(pd.read_csv(f))
    t = pd.concat(fr).drop_duplicates("timestamp").sort_values("timestamp")
    ts = t.timestamp.to_numpy(np.int64) * 1_000_000
    return ts, t.bidPrice.to_numpy(np.float64), t.askPrice.to_numpy(np.float64)


def covered_span(t0_ns, t1_ns, ts, max_gap_h=60):
    """True where [t0, t1] lies inside the tick data and contains no hole > max_gap_h hours
    (weekends are ~49 h; the tick files stop on the 28th of each month)."""
    t0_ns, t1_ns = np.asarray(t0_ns, np.int64), np.asarray(t1_ns, np.int64)
    d = np.diff(ts)
    holes = np.where(d > max_gap_h * 3600 * 10**9)[0]
    hole_start, hole_end = ts[holes], ts[holes + 1]
    ok = (t0_ns >= ts[0]) & (t1_ns <= ts[-1])
    for a, b in zip(hole_start, hole_end):
        ok &= ~((t0_ns < b) & (t1_ns > a))
    return ok


@nb.njit(cache=True)
def _run(ts, bid, ask, t_act, side, etype, level, t_exp, stop, stop_dist, target, target_dist,
         t_exit, trail, be, out_fill_t, out_fill, out_x_t, out_x, out_reason):
    MIN = 60 * 10**9
    for k in range(len(t_act)):
        s = side[k]
        i = np.searchsorted(ts, t_act[k])
        fi = -1
        fp = np.nan
        while i < len(ts):
            if etype[k] != 0 and ts[i] >= t_exp[k]:
                break
            if etype[k] == 0:
                fi = i
                fp = ask[i] if s > 0 else bid[i]
                break
            if etype[k] == 1:
                if s > 0 and ask[i] >= level[k]:
                    fi = i
                    fp = ask[i]
                    break
                if s < 0 and bid[i] <= level[k]:
                    fi = i
                    fp = bid[i]
                    break
            else:
                if s > 0 and ask[i] <= level[k]:
                    fi = i
                    fp = ask[i]
                    break
                if s < 0 and bid[i] >= level[k]:
                    fi = i
                    fp = bid[i]
                    break
            i += 1
        if fi < 0:
            out_reason[k] = 5
            continue
        out_fill_t[k] = ts[fi]
        out_fill[k] = fp
        st = stop[k] if not np.isnan(stop[k]) else fp - s * stop_dist[k]
        tg = target[k] if not np.isnan(target[k]) else (
            fp + s * target_dist[k] if not np.isnan(target_dist[k]) else np.nan)
        cur = st
        best = fp
        mbest = fp
        minute = ts[fi] // MIN
        moved = False
        j = fi
        done = False
        while j < len(ts):
            m = ts[j] // MIN
            if m != minute:
                # apply the finished minute's extreme (like the M1 rule: update after bar close)
                if s > 0:
                    if mbest > best:
                        best = mbest
                    if not np.isnan(trail[k]) and best - trail[k] > cur:
                        cur = best - trail[k]
                        moved = True
                    if not np.isnan(be[k]) and best - fp >= be[k] and fp > cur:
                        cur = fp
                        moved = True
                else:
                    if mbest < best:
                        best = mbest
                    if not np.isnan(trail[k]) and best + trail[k] < cur:
                        cur = best + trail[k]
                        moved = True
                    if not np.isnan(be[k]) and fp - best >= be[k] and fp < cur:
                        cur = fp
                        moved = True
                minute = m
                mbest = best
            if t_exit[k] > 0 and ts[j] >= t_exit[k] and j > fi:
                out_x_t[k] = ts[j]
                out_x[k] = bid[j] if s > 0 else ask[j]
                out_reason[k] = 2
                done = True
                break
            if s > 0:
                if bid[j] <= cur:
                    out_x_t[k] = ts[j]
                    out_x[k] = bid[j]
                    out_reason[k] = 3 if moved else 0
                    done = True
                    break
                if not np.isnan(tg) and bid[j] >= tg:
                    out_x_t[k] = ts[j]
                    out_x[k] = tg
                    out_reason[k] = 1
                    done = True
                    break
                if bid[j] > mbest:
                    mbest = bid[j]
            else:
                if ask[j] >= cur:
                    out_x_t[k] = ts[j]
                    out_x[k] = ask[j]
                    out_reason[k] = 3 if moved else 0
                    done = True
                    break
                if not np.isnan(tg) and ask[j] <= tg:
                    out_x_t[k] = ts[j]
                    out_x[k] = tg
                    out_reason[k] = 1
                    done = True
                    break
                if ask[j] < mbest:
                    mbest = ask[j]
            j += 1
        if not done:
            out_reason[k] = 4


REASONS = {0: "stop", 1: "target", 2: "time", 3: "trail", 4: "eod", 5: "nofill"}


def tick_simulate(m1, orders, ticks):
    """Re-simulate `orders` (goldlab order frame, indices into `m1`) on ticks.
    Returns a frame aligned on orders.index with fill/exit times, prices, pnl and reason."""
    ts, bid, ask = ticks
    o = orders.copy()
    defaults = {"etype": 0, "level": np.nan, "expiry_i": -1, "stop": np.nan, "stop_dist": np.nan,
                "target": np.nan, "target_dist": np.nan, "exit_i": -1, "trail": np.nan, "be": np.nan}
    for k, v in defaults.items():
        if k not in o:
            o[k] = v
    idx_ns = m1.index.as_unit("ns").asi8
    n = len(m1)

    def at(i):
        i = np.asarray(i, dtype=np.int64)
        out = np.full(len(i), -1, np.int64)
        ok = (i >= 0) & (i < n)
        out[ok] = idx_ns[i[ok]]
        return out

    t_act = at(o.entry_i.to_numpy())
    exp_i = o.expiry_i.to_numpy(np.int64)
    t_exp = np.where(exp_i >= 0, at(np.minimum(exp_i, n - 1)) + 60 * 10**9, -1)
    t_exit = at(o.exit_i.to_numpy())
    k = len(o)
    fill_t, x_t = np.zeros(k, np.int64), np.zeros(k, np.int64)
    fill, x = np.full(k, np.nan), np.full(k, np.nan)
    reason = np.full(k, -1, np.int64)
    _run(ts, bid, ask, t_act, o.side.to_numpy(np.int64), o.etype.to_numpy(np.int64),
         o.level.to_numpy(np.float64), t_exp, o.stop.to_numpy(np.float64),
         o.stop_dist.to_numpy(np.float64), o.target.to_numpy(np.float64),
         o.target_dist.to_numpy(np.float64), t_exit, o.trail.to_numpy(np.float64),
         o.be.to_numpy(np.float64), fill_t, fill, x_t, x, reason)
    r = pd.DataFrame({"t_fill": pd.to_datetime(fill_t, utc=True), "fill": fill,
                      "t_exit": pd.to_datetime(x_t, utc=True), "exit": x,
                      "reason": pd.Series(reason).map(REASONS).to_numpy()}, index=o.index)
    r["pnl"] = o.side.to_numpy() * (r.exit - r.fill)
    return r
