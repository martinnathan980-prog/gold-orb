"""Shared helpers for the look-ahead / simulation-fidelity audit of crypto:brk72_24h_wd.
Nothing here writes outside this folder; validation access only through valcut() (logged)."""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/gold-orb/lab")
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.metrics import report  # noqa: E402

import strategy as S  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "brk72_24h_wd"
LENS = "lookahead"
PARAMS = dict(S.FINALISTS[NAME]["params"])
SYMS = ("btcusd", "ethusd")
IS_END = pd.Timestamp("2022-01-01", tz="UTC")


def valcut(t, what):
    """Logged validation access (PROTOCOL_V2): label '<lens>:brk72_24h_wd:<what>'."""
    return gl.cut(t, "val", track="review", label=f"{LENS}:{NAME}:{what}")


def pf(x):
    x = np.asarray(x, float)
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else float("nan")


def stats(t, col="R"):
    """Compact stats of a trades frame."""
    if len(t) == 0:
        return {"n": 0}
    R = t[col].to_numpy(float)
    R = R[np.isfinite(R)]
    out = {"n": int(len(R)), "pf": round(pf(R), 3), "exp_R": round(float(R.mean()), 4),
           "t": round(float(R.mean() / (R.std(ddof=1) / np.sqrt(len(R)))), 2) if len(R) > 2 else 0.0,
           "sum_R": round(float(R.sum()), 1), "win": round(float((R > 0).mean()), 3)}
    if "pnl" in t and "entry" in t:
        out["bps"] = round(float((t["pnl"] / t["entry"]).mean() * 1e4), 2)
    return out


def by_year(t, col="R"):
    return {int(k): round(float(v), 1) for k, v in t.groupby(t.entry_time.dt.year)[col].sum().items()}


def dump(obj, name):
    with open(os.path.join(HERE, name), "w") as f:
        json.dump(obj, f, indent=1, default=str)
