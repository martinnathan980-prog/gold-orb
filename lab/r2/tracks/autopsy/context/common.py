"""Lens `context` of the loss autopsy (PROTOCOL_V3, Addendum H): shared helpers. IN SAMPLE ONLY.

Every price frame is read with a parquet row filter `ts < 2022-01-01 00:00 UTC`, so no row dated 2022 or later
ever enters this process; every trades file is read with the filter `entry_time < 2022-01-01` in the same
statement. Rules and simulations only ever see these in-sample slices (r2.run / recalc are never called on a
full frame: the registry below only takes the (make_orders, params) pairs of `r2/recalc.py::sleeves()`).

Run with:  NUMBA_CACHE_DIR=/tmp/ctx_numba_cache PYTHONDONTWRITEBYTECODE=1 python3 <script>.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd

if not os.environ.get("NUMBA_CACHE_DIR", "").startswith("/tmp"):
    raise SystemExit("set NUMBA_CACHE_DIR to a directory under /tmp before importing the lab")
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
if LAB not in sys.path:
    sys.path.insert(0, LAB)
R2DIR = os.path.join(LAB, "r2")
if R2DIR not in sys.path:
    sys.path.insert(0, R2DIR)

import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

OUT = os.path.join(LAB, "results", "r2", "autopsy", "context")
os.makedirs(OUT, exist_ok=True)
IS_END = pd.Timestamp("2022-01-01", tz="UTC")
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")
NY = "America/New_York"
OFFICIAL_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")

# the ten validated sleeves (Addendum H), in the order of the task text
SLEEVES = [("ocm4", "us100"), ("noise30", "us100"),
           ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd"), ("GOLD_FRI_PM", "xauusd"),
           ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("nq_btc_follow", "btcusd")]
KEYS = [f"{n}__{s}" for n, s in SLEEVES]


def key(name, sym):
    return f"{name}__{sym}"


# ------------------------------------------------------------------------------------------- data
def load_fp_is(sym, cols=None):
    """FP-cost M1 frame of `sym`, rows with ts < 2022-01-01 only (filtered at read time)."""
    path = os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet")
    df = pd.read_parquet(path, columns=cols, filters=[("ts", "<", IS_END)])
    assert df.index.is_monotonic_increasing and df.index.max() < IS_END
    return df


def load_raw_is(sym, cols=None):
    """Round-1 Dukascopy bid/ask M1 frame (eurusd, usdjpy), rows with ts < 2022-01-01 only."""
    path = os.path.join(LAB, "data", f"{sym}_m1.parquet")
    df = pd.read_parquet(path, columns=cols, filters=[("ts", "<", IS_END)])
    assert df.index.is_monotonic_increasing and df.index.max() < IS_END
    return df


def load_official(name, sym):
    """Official trades of a sleeve, entry_time < 2022-01-01 (the cut is in the read statement itself)."""
    t = pd.read_parquet(os.path.join(OFFICIAL_DIR, f"{name}__{sym}.parquet"), filters=[("entry_time", "<", IS_END)])
    assert (t.entry_time < IS_END).all()
    return t.sort_values("entry_time", kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------------------------------- registry
_REG = None


def registry():
    """{key: (track, name, sym, make_orders, params)} for the ten sleeves, from r2/recalc.py::sleeves()
    (same modules, same wrappers, same frozen parameters). Nothing is run here."""
    global _REG
    if _REG is None:
        import recalc  # noqa: E402  (lab/r2/recalc.py: importing it runs nothing)
        reg = {}
        for track, name, sym, mo, params in recalc.sleeves():
            if (name, sym) in SLEEVES:
                reg[key(name, sym)] = (track, name, sym, mo, dict(params))
        assert set(reg) == set(KEYS), set(KEYS) - set(reg)
        _REG = reg
    return _REG


def leadlag_module():
    return sys.modules["r2_leadlag_strategy"]


def set_leader_is(us100_is):
    """nq_btc_follow reads its leader from a registry; register the IN-SAMPLE us100 slice (never the default
    loader, which would read the research file to 2025)."""
    registry()
    m = leadlag_module()
    m.clear_leaders()
    m.set_leader("us100", us100_is)


def mode_frame(m1, mode):
    if mode == "fp":
        return m1
    if mode == "stress":
        return apply_spread_mult(m1, 1.5)
    raise ValueError(mode)


def mode_costs(sym, mode):
    return r2.costs(sym) if mode == "fp" else r2.costs(sym, 1.5)


def build_orders(k, mk):
    """Orders of sleeve k on the (already mode-transformed) in-sample frame mk."""
    track, name, sym, mo, params = registry()[k]
    if name == "nq_btc_follow":
        assert "us100" in leadlag_module()._LEADERS, "set_leader_is() first"
    return mo(mk, **params).reset_index(drop=True)


def sim(k, mk, orders, mode, no_overlap=True):
    sym = registry()[k][2]
    return simulate(mk, orders, sym=sym, costs=mode_costs(sym, mode), no_overlap=no_overlap)


# ------------------------------------------------------------------------------------------- metrics
def stats(R, years=None):
    """Plain statistics of a vector of trade results in R."""
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    n = len(R)
    if n == 0:
        return {"n": 0, "exp": None, "total": 0.0, "win": None, "avg_loss": None, "pf": None}
    los = R[R < 0]
    gain = R[R > 0].sum()
    out = {"n": int(n), "exp": round(float(R.mean()), 4), "total": round(float(R.sum()), 2),
           "win": round(float((R > 0).mean()), 3),
           "avg_loss": round(float(los.mean()), 4) if len(los) else 0.0,
           "pf": round(float(gain / -los.sum()), 3) if len(los) and los.sum() < 0 else None}
    return out


def by_year(t, col="R"):
    y = t.entry_time.dt.year
    return {int(k): stats(g[col]) for k, g in t.groupby(y)}


def dump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))


def append_trial(row):
    with open(os.path.join(OUT, "trials.jsonl"), "a") as f:
        f.write(json.dumps(row, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n")
