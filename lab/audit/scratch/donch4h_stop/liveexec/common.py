"""Live-execution lens (donch4h_stop): shared helpers.  Run from /home/user/gold-orb/lab.

Nothing here modifies goldlab / tracks / results/<track>.  VAL access only via gl.cut(...,"val",
track="review", label="liveexec:donch4h_stop:<what>").
"""
import importlib.util
import math
import os
import sys

import numba as nb
import numpy as np
import pandas as pd

LAB = "/home/user/gold-orb/lab"
HERE = os.path.dirname(os.path.abspath(__file__))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab.data import trading_day  # noqa: E402
from goldlab.sim import COSTS  # noqa: E402

PARIS = "Europe/Paris"


def load_strategy():
    d = os.path.join(LAB, "tracks", "trend")
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location("strategy_trend_liveexec", os.path.join(d, "strategy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = load_strategy()
PARAMS = dict(S.FINALISTS["donch4h_stop"])


def baseline(m1=None):
    m1 = gl.load_m1("xauusd") if m1 is None else m1
    o = S.make_orders(m1, **PARAMS).reset_index(drop=True)
    t = gl.simulate(m1, o, no_overlap=True)
    return m1, o, t


def stats(t, col="R"):
    if len(t) == 0:
        return {"n": 0}
    R = t[col].to_numpy(float)
    R = R[np.isfinite(R)]
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    yrs = t.entry_time.dt.year.to_numpy()
    by = pd.Series(t[col].to_numpy(float)).groupby(yrs).sum()
    lo = t.side.to_numpy() > 0
    def _pf(x):
        x = x[np.isfinite(x)]
        gg, ll = x[x > 0].sum(), -x[x < 0].sum()
        return round(float(gg / ll), 3) if ll > 0 else None
    return {"n": int(len(R)), "pf": round(float(g / l), 3) if l > 0 else None,
            "exp": round(float(R.mean()), 4),
            "t": round(float(R.mean() / (R.std(ddof=1) / math.sqrt(len(R)))), 2) if len(R) > 2 else None,
            "totR": round(float(R.sum()), 1),
            "yrs_pos": f"{int((by > 0).sum())}/{len(by)}",
            "long_R": round(float(t[col].to_numpy(float)[lo].sum()), 1),
            "short_R": round(float(t[col].to_numpy(float)[~lo].sum()), 1),
            "pf_long": _pf(t[col].to_numpy(float)[lo]), "pf_short": _pf(t[col].to_numpy(float)[~lo])}


def is_part(t):
    return gl.cut(t, "is")


def val_part(t, what):
    return gl.cut(t, "val", track="review", label=f"liveexec:donch4h_stop:{what}")


# --------------------------------------------------------------------------------------------
# Custom simulator = copy of goldlab.sim._run logic, extended with:
#   arm_i     : M1 index used for the one-position rule (order skipped if arm_i <= last_exit).
#               Equal to entry_i reproduces the engine exactly.
#   trail_mode: 0 engine (trail updated with each M1 bar extreme at bar close)
#               1 trail moved only at bars where upd[i] is True (best price tracked continuously)
#               2 MT5 terminal built-in trailing: SL starts trailing only once the open profit
#                 (best bid - fill for longs, fill - best ask for shorts) >= trail distance;
#                 updated at each M1 close afterwards
#               3 = 1 and 2 combined (built-in style activation, but only at upd bars)
# --------------------------------------------------------------------------------------------
STOP, TARGET, TIME, TRAIL, EOD, NOFILL, SKIP, GAP = 0, 1, 2, 3, 4, 5, 6, 7
REASONS = {0: "stop", 1: "target", 2: "time", 3: "trail", 4: "eod", 5: "nofill", 6: "skip", 7: "gap"}


@nb.njit(cache=True)
def _run2(bo, bh, bl, bc, ao, ah, al, ac, arm_i, entry_i, side, etype, level, expiry_i, stop_abs,
          stop_dist, exit_i, trail, slip, no_overlap, trail_mode, upd,
          fill_i, fill_px, x_i, x_px, reason, init_stop, nmod):
    N = len(bo)
    last_exit = -1
    for k in range(len(entry_i)):
        i0 = entry_i[k]
        if i0 >= N or i0 < 0:
            reason[k] = NOFILL
            continue
        if no_overlap and arm_i[k] <= last_exit:
            reason[k] = SKIP
            continue
        s = side[k]
        fi = -1
        fp = np.nan
        et = etype[k]
        if et == 0:
            fi = i0
            fp = ao[i0] * (1 + slip) if s > 0 else bo[i0] * (1 - slip)
        else:
            lv = level[k]
            jmax = min(expiry_i[k], N - 1)
            for i in range(i0, jmax + 1):
                if s > 0 and ah[i] >= lv:
                    fi = i
                    fp = max(lv, ao[i]) * (1 + slip)
                    break
                if s < 0 and bl[i] <= lv:
                    fi = i
                    fp = min(lv, bo[i]) * (1 - slip)
                    break
        if fi < 0:
            reason[k] = NOFILL
            continue
        fill_i[k] = fi
        fill_px[k] = fp
        st = stop_abs[k] if not np.isnan(stop_abs[k]) else fp - s * stop_dist[k]
        init_stop[k] = st
        if (s > 0 and st >= fp) or (s < 0 and st <= fp):
            x_i[k] = fi
            x_px[k] = bo[fi] * (1 - slip) if s > 0 else ao[fi] * (1 + slip)
            reason[k] = GAP
            last_exit = fi
            continue
        cur = st
        best = fp
        moved = False
        xe = exit_i[k]
        done = False
        i = fi
        tr = trail[k]
        nm = 0
        while i < N:
            if xe >= 0 and i >= xe and i > fi:
                x_i[k] = i
                x_px[k] = bo[i] * (1 - slip) if s > 0 else ao[i] * (1 + slip)
                reason[k] = TIME
                done = True
                break
            first = i == fi
            if s > 0:
                if bl[i] <= cur:
                    px = cur if first else min(cur, bo[i])
                    x_i[k] = i
                    x_px[k] = px * (1 - slip)
                    reason[k] = TRAIL if moved else STOP
                    done = True
                    break
                if bh[i] > best:
                    best = bh[i]
                if not np.isnan(tr):
                    ok = True
                    if trail_mode == 1 or trail_mode == 3:
                        ok = upd[i]
                    if trail_mode == 2 or trail_mode == 3:
                        ok = ok and (best - fp >= tr)
                    if ok and best - tr > cur:
                        cur = best - tr
                        moved = True
                        nm += 1
            else:
                if ah[i] >= cur:
                    px = cur if first else max(cur, ao[i])
                    x_i[k] = i
                    x_px[k] = px * (1 + slip)
                    reason[k] = TRAIL if moved else STOP
                    done = True
                    break
                if al[i] < best:
                    best = al[i]
                if not np.isnan(tr):
                    ok = True
                    if trail_mode == 1 or trail_mode == 3:
                        ok = upd[i]
                    if trail_mode == 2 or trail_mode == 3:
                        ok = ok and (fp - best >= tr)
                    if ok and best + tr < cur:
                        cur = best + tr
                        moved = True
                        nm += 1
            i += 1
        if not done:
            x_i[k] = N - 1
            x_px[k] = bc[N - 1] if s > 0 else ac[N - 1]
            reason[k] = EOD
        nmod[k] = nm
        last_exit = x_i[k]


def simulate2(m1, o, no_overlap=True, trail_mode=0, upd=None, costs=None, arrays=None):
    """o: DataFrame with entry_i, side, etype, level, expiry_i, stop_dist (or stop), exit_i, trail
    and optionally arm_i.  Returns a trades frame with the same cost post-processing as gl.simulate."""
    c = costs or COSTS["xauusd"]
    o = o.reset_index(drop=True).copy()
    for k, v in {"etype": 0, "level": np.nan, "expiry_i": -1, "stop": np.nan, "stop_dist": np.nan,
                 "exit_i": -1, "trail": np.nan}.items():
        if k not in o:
            o[k] = v
    if "arm_i" not in o:
        o["arm_i"] = o["entry_i"]
    o = o.sort_values("arm_i", kind="stable")
    n = len(o)
    if arrays is None:
        arrays = tuple(m1[k].to_numpy(np.float64) for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))
    bo, bh, bl, bc, ao, ah, al, ac = arrays
    if upd is None:
        upd = np.zeros(len(bo), np.bool_)
    fill_i = np.full(n, -1, np.int64)
    x_i = np.full(n, -1, np.int64)
    fill_px, x_px, init_stop = (np.full(n, np.nan) for _ in range(3))
    reason = np.full(n, -1, np.int64)
    nmod = np.zeros(n, np.int64)
    _run2(bo, bh, bl, bc, ao, ah, al, ac,
          o["arm_i"].to_numpy(np.int64), o["entry_i"].to_numpy(np.int64), o["side"].to_numpy(np.int64),
          o["etype"].to_numpy(np.int64), o["level"].to_numpy(np.float64), o["expiry_i"].to_numpy(np.int64),
          o["stop"].to_numpy(np.float64), o["stop_dist"].to_numpy(np.float64), o["exit_i"].to_numpy(np.int64),
          o["trail"].to_numpy(np.float64), c.slip_bps * 1e-4, bool(no_overlap), int(trail_mode),
          np.asarray(upd, np.bool_), fill_i, fill_px, x_i, x_px, reason, init_stop, nmod)
    ok = fill_i >= 0
    idx = m1.index
    t = pd.DataFrame({
        "side": o["side"].to_numpy()[ok],
        "entry_time": idx[fill_i[ok]],
        "exit_time": idx[x_i[ok]] + pd.Timedelta(minutes=1) * (reason[ok] != TIME),
        "entry": fill_px[ok], "exit": x_px[ok], "stop": init_stop[ok],
        "reason": pd.Series(reason[ok]).map(REASONS).to_numpy(),
        "nmod": nmod[ok], "fill_i": fill_i[ok], "x_i": x_i[ok],
    }, index=o.index[ok])
    for extra in [col for col in o.columns if col not in ("entry_i", "side", "etype", "level", "expiry_i",
                                                          "stop", "stop_dist", "exit_i", "trail")]:
        t[extra] = o.loc[t.index, extra].to_numpy()
    gross = t.side * (t.exit - t.entry)
    d0 = trading_day(t.entry_time).values.astype("datetime64[D]")
    d1 = trading_day(t.exit_time - pd.Timedelta(seconds=1)).values.astype("datetime64[D]")
    nights = np.busday_count(d0, d1) + 2 * np.busday_count(d0, d1, weekmask="Wed")
    rate = np.where(t.side > 0, c.swap_long, c.swap_short)
    t["swap"] = t.entry * rate / 360.0 * nights
    t["commission"] = c.commission
    t["pnl"] = gross - t["swap"] - t["commission"]
    t["risk"] = (t.entry - t.stop).abs()
    t["R"] = t.pnl / t.risk.where(t.risk > 0)
    t["hold_min"] = (t.exit_time - t.entry_time).dt.total_seconds() / 60
    t.attrs.update(skipped=int((reason == SKIP).sum()), nofill=int((reason == NOFILL).sum()))
    return t.sort_values("entry_time")


def fmt(d):
    keys = ("n", "pf", "exp", "t", "totR", "yrs_pos", "long_R", "short_R", "pf_long", "pf_short")
    return " ".join(f"{k}={d.get(k)}" for k in keys if k in d)
