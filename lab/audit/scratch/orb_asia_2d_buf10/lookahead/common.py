"""Shared helpers for the look-ahead / simulation-fidelity audit of orb/orb_asia_2d_buf10.
Run scripts from /home/user/gold-orb/lab (sys.path insert '.')."""
import os
import sys
import time

import numpy as np
import pandas as pd

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
ORB = os.path.join(LAB, "tracks", "orb")
if ORB not in sys.path:
    sys.path.insert(0, ORB)
import goldlab as gl  # noqa: E402
import strategy as S  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "orb_asia_2d_buf10"
P = dict(S.FINALISTS[NAME])
LENS = "lookahead"


def vlabel(what):
    return f"{LENS}:{NAME}:{what}"


def load(unpatched=False):
    if unpatched:
        return pd.read_parquet(os.path.join(LAB, "data", "xauusd_m1_unpatched.parquet"))
    return gl.load_m1("xauusd")


def pf(R):
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return g / l if l > 0 else np.nan


def tstat(R):
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    return R.mean() / (R.std(ddof=1) / np.sqrt(len(R))) if len(R) > 2 else np.nan


def summ(t):
    """Compact stats of a trades frame."""
    if len(t) == 0:
        return {"n": 0}
    R = t.R.to_numpy()
    yrs = t.groupby(t.entry_time.dt.year).R.sum()
    return {"n": int(len(t)), "pf": round(pf(R), 3), "t": round(tstat(R), 2), "exp": round(float(np.nanmean(R)), 4),
            "totR": round(float(np.nansum(R)), 1), "yrs+": f"{int((yrs > 0).sum())}/{len(yrs)}",
            "L_pf": round(pf(t.R[t.side > 0]), 3), "S_pf": round(pf(t.R[t.side < 0]), 3)}


def is_part(t):
    return gl.cut(t, "is")


def val_part(t, what):
    return gl.cut(t, "val", track="review", label=vlabel(what))


class Timer:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        self.t0 = time.time()

    def __exit__(self, *a):
        print(f"[{self.msg}] {time.time() - self.t0:.1f}s", flush=True)
