"""Shared helpers for the statistical-skeptic review of orb/orb_asia_2d_buf10.
Run scripts from /home/user/gold-orb/lab.  Nothing here writes outside this scratch dir
(except gl.cut's own VAL access log)."""
import math
import os
import sys

LAB = "/home/user/gold-orb/lab"
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (LAB, os.path.join(LAB, "tracks", "orb")):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goldlab as gl  # noqa: E402
from goldlab.evalkit import is_criteria, stressed_costs, val_criteria  # noqa: E402
import strategy as S  # noqa: E402

NAME = "orb_asia_2d_buf10"
PARAMS = S.FINALISTS[NAME]
LENS = "statskeptic"
IS_A, IS_B = pd.Timestamp("2013-01-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC")
VA_A, VA_B = pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC")
STRESS = stressed_costs("xauusd")


def label(what):
    return f"{LENS}:{NAME}:{what}"


def pf(R):
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return float(g / l) if l > 0 else (float("inf") if g > 0 else float("nan"))


def tstat(R):
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    if len(R) < 3:
        return float("nan")
    return float(R.mean() / (R.std(ddof=1) / math.sqrt(len(R))))


def summarize(t):
    R = t["R"].to_numpy()
    ok = np.isfinite(R)
    R = R[ok]
    if len(R) == 0:
        return {"n": 0}
    side = t["side"].to_numpy()[ok]
    return {"n": int(len(R)), "pf": round(pf(R), 4), "exp": round(float(R.mean()), 4),
            "t": round(tstat(R), 3), "sumR": round(float(R.sum()), 1),
            "long_n": int((side > 0).sum()), "long_pf": round(pf(R[side > 0]), 3),
            "long_R": round(float(R[side > 0].sum()), 1),
            "short_n": int((side < 0).sum()), "short_pf": round(pf(R[side < 0]), 3),
            "short_R": round(float(R[side < 0].sum()), 1)}


def in_is(t):
    return gl.cut(t, "is")
