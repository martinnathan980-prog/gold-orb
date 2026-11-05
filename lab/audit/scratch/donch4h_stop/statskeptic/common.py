"""Shared helpers for the statistical-skeptic review of trend/donch4h_stop.
Run scripts from /home/user/gold-orb/lab.  Nothing here writes outside this scratch dir
(except gl.cut's own VAL access log)."""
import math
import os
import sys

LAB = "/home/user/gold-orb/lab"
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (LAB, os.path.join(LAB, "tracks", "trend")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goldlab as gl  # noqa: E402
from goldlab.evalkit import is_criteria, stressed_costs, val_criteria  # noqa: E402
import strategy as S  # noqa: E402

PARAMS = S.FINALISTS["donch4h_stop"]
LENS = "statskeptic"
IS_A, IS_B = pd.Timestamp("2013-01-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC")
VA_A, VA_B = pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC")


def label(what):
    return f"{LENS}:donch4h_stop:{what}"


def pf(R):
    R = np.asarray(R, float)
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return float(g / l) if l > 0 else (float("inf") if g > 0 else float("nan"))


def tstat(R):
    R = np.asarray(R, float)
    if len(R) < 3:
        return float("nan")
    return float(R.mean() / (R.std(ddof=1) / math.sqrt(len(R))))


def is_part(t):
    return gl.cut(t, "is")


def summarize(t):
    """compact stats used everywhere (works on any trades frame)."""
    R = t["R"].to_numpy()
    R = R[np.isfinite(R)]
    if len(R) == 0:
        return {"n": 0}
    side = t["side"].to_numpy()
    return {"n": int(len(R)), "pf": round(pf(R), 3), "exp": round(float(R.mean()), 4),
            "t": round(tstat(R), 2), "sumR": round(float(R.sum()), 1),
            "long_n": int((side > 0).sum()), "long_pf": round(pf(t.R[t.side > 0]), 3),
            "long_R": round(float(t.R[t.side > 0].sum()), 1),
            "short_n": int((side < 0).sum()), "short_pf": round(pf(t.R[t.side < 0]), 3),
            "short_R": round(float(t.R[t.side < 0].sum()), 1)}


def criteria_from(rep, rep_stress):
    c = is_criteria(rep, rep_stress)
    return c


# ----------------------------------------------------------------- random-entry grid
def h4_grid(m1):
    """Decision grid identical to the candidate: UTC 4h bars, ATR14 Wilder (mid), exit at
    decision + 5 NY trading days - 5 min (last bar before a closure)."""
    b = S.bars_cached(m1, "4h")
    a = gl.atr(b, 14).to_numpy()
    tc = pd.DatetimeIndex(b["t_close"])
    ei = gl.entry_index(m1, tc)
    nxt = np.r_[gl.entry_index(m1, tc[1:]), len(m1)] - 1     # last M1 bar of the window
    xi = S.exit_index(m1, S.add_trading_days(tc, 5) - pd.Timedelta(minutes=5))
    ok = np.isfinite(a) & (np.arange(len(b)) >= 60) & (ei < len(m1)) & (xi > ei) & (nxt >= ei)
    return {"b": b, "atr": a, "tc": tc, "ei": ei, "i1": nxt, "xi": xi, "ok": ok}


def random_orders(g, rng, p_place, p_long=0.5, uniform_in_window=True):
    pick = g["ok"] & (rng.random(len(g["ok"])) < p_place)
    idx = np.flatnonzero(pick)
    ei, i1 = g["ei"][idx], g["i1"][idx]
    if uniform_in_window:
        span = np.maximum(i1 - ei + 1, 1)
        ent = ei + (rng.random(len(idx)) * span).astype(np.int64)
    else:
        ent = ei
    xi = g["xi"][idx]
    keep = xi > ent
    idx, ent, xi = idx[keep], ent[keep], xi[keep]
    side = np.where(rng.random(len(idx)) < p_long, 1, -1)
    a = g["atr"][idx]
    return pd.DataFrame({"entry_i": ent, "side": side, "etype": 0, "stop_dist": 2.0 * a,
                         "trail": 2.0 * a, "exit_i": xi, "dec_i": idx})


def rep_pair(t, ts):
    """IS report, IS stress report."""
    return gl.report(gl.cut(t, "is")), gl.report(gl.cut(ts, "is"))
