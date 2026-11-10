"""Shared helpers for the statistical-skeptic audit of crypto/brk72_24h_wd (scratch only)."""
import os, sys, json, math
import numpy as np, pandas as pd
sys.path.insert(0, "/home/user/gold-orb/lab")
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
import goldlab as gl
from goldlab import r2
from goldlab.metrics import report
import strategy as S

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "brk72_24h_wd"
P = dict(S.FINALISTS[NAME]["params"])
SYMS = ("btcusd", "ethusd")
LENS = "stat_skeptic"
IS_END = pd.Timestamp("2022-01-01", tz="UTC")


def vcut(t, what):
    """Logged validation cut (track='review')."""
    return gl.cut(t, "val", track="review", label=f"{LENS}:{NAME}:{what}")


def pf(x):
    x = np.asarray(x, float)
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else float("nan")


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * math.sqrt(len(x))) if len(x) > 2 else float("nan")


def stats(t):
    if len(t) == 0:
        return {"n": 0}
    R = t.R.to_numpy()
    return {"n": int(len(t)), "exp_R": round(float(R.mean()), 4), "pf": round(pf(R), 3), "t": round(tstat(R), 2),
            "bps": round(float((t.pnl / t.entry).mean() * 1e4), 2), "sum_R": round(float(R.sum()), 1),
            "win": round(float((R > 0).mean()), 3)}


def load_trades(sym, kind, period):
    """kind: fp | gross | every | stress ; period: is | val (saved by step1)."""
    p = os.path.join(HERE, "trades", f"{kind}_{period}_{sym}.parquet")
    return pd.read_parquet(p)


def week_key(ts):
    return pd.DatetimeIndex(ts).tz_convert(None).to_period("W")
