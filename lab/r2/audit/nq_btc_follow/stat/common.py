"""Statistical-skeptic audit of nq_btc_follow - shared helpers (read-only use of the lab toolkit)."""
import gc
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd

LAB = "/home/user/gold-orb/lab"
if LAB not in sys.path:
    sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import simulate, apply_spread_mult  # noqa: E402
from goldlab.metrics import report  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("leadlag_strategy", os.path.join(LAB, "r2", "tracks", "leadlag", "strategy.py"))
strategy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(strategy)

F = dict(strategy.FINALISTS["nq_btc_follow"]["params"])
SYM = "btcusd"
LENS = "stat"
NAME = "nq_btc_follow"
UTC = "UTC"
IS_END = pd.Timestamp("2022-01-01", tz="UTC")
VAL_END = pd.Timestamp("2026-01-01", tz="UTC")


def val_cut(trades, what):
    """Logged validation access (PROTOCOL_V2): track='review'."""
    return gl.cut(trades, "val", track="review", label=f"{LENS}:{NAME}:{what}")


def is_cut(trades):
    return gl.cut(trades, "is")


def pf(R):
    R = np.asarray(R, float)
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return float(g / l) if l > 0 else float("nan")


def tstat(R):
    R = np.asarray(R, float)
    return float(R.mean() / (R.std(ddof=1) / np.sqrt(len(R)))) if len(R) > 2 else float("nan")


def cluster_t(R, keys):
    """t of the total with clusters summed (sum / sqrt(sum of squared cluster sums))."""
    s = pd.Series(np.asarray(R, float)).groupby(np.asarray(keys)).sum()
    return float(s.sum() / np.sqrt((s ** 2).sum()))


def cluster_t_centered(R, keys):
    """Cluster-robust t of the MEAN per trade (CR0 sandwich: residuals around the mean, summed by cluster)."""
    R = np.asarray(R, float)
    m = R.mean()
    e = pd.Series(R - m).groupby(np.asarray(keys)).sum().to_numpy()
    G = len(e)
    se = np.sqrt((e ** 2).sum() * G / (G - 1)) / len(R)
    return float(m / se)


def week_key(ts):
    return pd.DatetimeIndex(ts).tz_convert(None).to_period("W").astype(str)


def day_key(ts):
    return pd.DatetimeIndex(ts).tz_convert("America/New_York").strftime("%Y-%m-%d")


def bps(t):
    return float((t["pnl"] / t["entry"]).mean() * 1e4) if len(t) else float("nan")


def save(obj, name):
    with open(os.path.join(HERE, name), "w") as f:
        json.dump(obj, f, indent=1, default=str)


def load_json(name):
    return json.load(open(os.path.join(HERE, name)))
