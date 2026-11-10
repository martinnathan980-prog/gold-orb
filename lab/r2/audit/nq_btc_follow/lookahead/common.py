"""Shared helpers for the look-ahead / simulation-fidelity audit of nq_btc_follow (read-only on lab code)."""
import gc
import json
import os
import sys
import time

import numpy as np
import pandas as pd

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
TRK = os.path.join(LAB, "r2", "tracks", "leadlag")
if TRK not in sys.path:
    sys.path.insert(0, TRK)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = HERE

import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.metrics import report  # noqa: E402
import strategy  # noqa: E402

LENS = "lookahead"
NAME = "nq_btc_follow"
P = dict(strategy.FINALISTS[NAME]["params"])
IS_END = pd.Timestamp("2022-01-01", tz="UTC")


def vcut(trades, what):
    """Logged validation access for this review."""
    return gl.cut(trades, "val", track="review", label=f"{LENS}:{NAME}:{what}")


def pf(R):
    R = np.asarray(R, float)
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return float(g / l) if l > 0 else float("nan")


def brief(t):
    if len(t) == 0:
        return {"n": 0}
    R = t["R"].to_numpy()
    return {"n": int(len(R)), "pf": round(pf(R), 3), "expR": round(float(R.mean()), 4),
            "t": round(float(R.mean() / (R.std(ddof=1) / np.sqrt(len(R)))), 2), "totR": round(float(R.sum()), 1),
            "win": round(float((R > 0).mean()), 3), "bps": round(float((t.pnl / t.entry).mean() * 1e4), 2),
            "stops": int((t.reason == "stop").sum()),
            "by_year": {int(k): round(float(v), 1) for k, v in t.groupby(t.entry_time.dt.year)["R"].sum().items()}}


def dump(obj, name):
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, indent=1, default=str)
