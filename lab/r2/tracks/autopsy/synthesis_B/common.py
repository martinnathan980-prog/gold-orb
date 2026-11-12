"""synthesis_B (PROTOCOL_V3 Addendum H, lenses context / cluster / breadth): shared helpers. IN SAMPLE ONLY.

Every price frame is read with a pyarrow row filter ts < 2022-01-01 00:00 UTC (no 2022+ row ever enters the process)
and that slice is passed explicitly to every rule and every simulation. Every official trades file is read with the
row filter entry_time < 2022-01-01 in the read itself. The rules and frozen parameters come from
lab/r2/recalc.py::sleeves() (imported, nothing run) and lab/tracks/{orb,trend}/strategy.py through that registry.

Run with:  NUMBA_CACHE_DIR=/tmp/<dir> PYTHONDONTWRITEBYTECODE=1 python3 <script>.py
"""
import importlib.util
import json
import os
import sys

if not os.environ.get("NUMBA_CACHE_DIR", "").startswith("/tmp/"):
    raise SystemExit("set NUMBA_CACHE_DIR to a directory under /tmp before importing the lab")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(HERE, "out")
RESULT = os.path.join(LAB, "results", "r2", "autopsy", "synthesis_B.json")
TRIALS = os.path.join(HERE, "trials.jsonl")
if LAB not in sys.path:
    sys.path.insert(0, LAB)

import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

IS_END = pd.Timestamp("2022-01-01", tz="UTC")
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")
YEARS = (2018, 2019, 2020, 2021)
NY = "America/New_York"
OFFICIAL_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")

SLEEVES = [("ocm4", "us100"), ("noise30", "us100"),
           ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd"), ("GOLD_FRI_PM", "xauusd"),
           ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("nq_btc_follow", "btcusd")]
RULES = ["noise30", "ocm4", "donch4h_stop", "orb_asia_2d_buf10", "GOLD_FRI_PM", "brk72_24h_wd",
         "F1_brk_ridge_filter", "nq_btc_follow"]


def key(name, sym):
    return f"{name}__{sym}"


# --------------------------------------------------------------------------------------------- data
def load_is(sym):
    """FP-cost M1 frame of `sym`, rows with bar start < 2022-01-01 00:00 UTC only (filtered while reading)."""
    df = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), filters=[("ts", "<", IS_END)])
    assert df.index.is_monotonic_increasing and df.index.is_unique and df.index.max() < IS_END
    return df


def official(name, sym):
    """Official trades of a sleeve, rows with entry_time < 2022-01-01 only (the cut is in the read itself)."""
    t = pd.read_parquet(os.path.join(OFFICIAL_DIR, f"{name}__{sym}.parquet"), filters=[("entry_time", "<", IS_END)])
    assert (t.entry_time < IS_END).all()
    return t.sort_values("entry_time", kind="stable").reset_index(drop=True)


# --------------------------------------------------------------------------------------------- rules
_REG = None


def registry():
    """{rule name: (track, make_orders, params)} from lab/r2/recalc.py::sleeves(); brk72_24h_wd comes with its FP-hours
    exit wrapper exactly as recalculated. F2_brk_unfiltered (not one of the ten) is left out."""
    global _REG
    if _REG is None:
        spec = importlib.util.spec_from_file_location("r2_recalc_synthesis_B", os.path.join(LAB, "r2", "recalc.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        reg = {}
        for track, name, sym, mo, params in m.sleeves():
            if name == "F2_brk_unfiltered" or name in reg:
                continue
            reg[name] = (track, mo, dict(params))
        assert set(reg) == set(RULES), sorted(reg)
        _REG = reg
    return _REG


def clear_rule_caches():
    """Rule modules cache bar frames keyed on id(frame) + length + ends: cleared before every call."""
    for modname, attr in (("r2_ml_strategy", "_cache"), ("strategy_trend", "_bar_cache"), ("strategy_orb", "_daily_cache")):
        mod = sys.modules.get(modname)
        if mod is not None and hasattr(mod, attr):
            getattr(mod, attr).clear()
    mod = sys.modules.get("r2_idx_us_strategy")
    if mod is not None and hasattr(mod, "cm"):
        mod.cm._grid_cache.clear()
        mod.cm._atr_cache.clear()


def leader_series(m1_us100):
    """us100 mid closes of the in-sample slice: the leader of nq_btc_follow."""
    return ((m1_us100["bc"] + m1_us100["ac"]) / 2).astype("float64")


def build_orders(rule, mk, leader=None):
    """Orders of the frozen rule on the frame given (the in-sample slice, fp or stressed)."""
    track, mo, params = registry()[rule]
    clear_rule_caches()
    if rule == "nq_btc_follow":
        if leader is None:
            raise ValueError("nq_btc_follow needs the in-sample us100 leader")
        mod = sys.modules["r2_leadlag_strategy"]
        mod.clear_leaders()
        mod.set_leader("us100", leader)
    return mo(mk, **params).reset_index(drop=True)


def mode_frame(m1, mode):
    if mode == "fp":
        return m1
    if mode == "stress":
        return apply_spread_mult(m1, 1.5)
    raise ValueError(mode)


def mode_costs(sym, mode):
    if mode == "fp":
        return r2.costs(sym)
    if mode == "stress":
        return r2.costs(sym, 1.5)
    raise ValueError(mode)


def refused_mask(mk, t, min_spreads=3.0):
    """Trades whose initial stop is closer than `min_spreads` spreads of their fill bar (or crossed at the fill)."""
    if not len(t):
        return np.zeros(0, bool)
    spr = (mk["ao"].to_numpy() - mk["bo"].to_numpy())
    fi = mk.index.searchsorted(t.entry_time)
    bad = t["risk"].to_numpy() < min_spreads * spr[fi]
    bad |= t["reason"].to_numpy() == "gap"
    return bad


def simulate_filtered(mk, orders, sym, costs, min_spreads=3.0, no_overlap=True, max_iter=20):
    """simulate() with the broker's minimum stop distance: an order whose trade would have a stop closer than
    `min_spreads` spreads of its fill bar is removed (not taken, the sleeve stays flat) and the sleeve re-simulated,
    until no taken trade violates it. Orders carry an 'oid' column (their row number in the rule's table)."""
    o = orders.reset_index(drop=True).copy()
    if "oid" not in o:
        o["oid"] = np.arange(len(o), dtype=np.int64)
    refused = []
    t = None
    for _ in range(max_iter):
        t = simulate(mk, o, sym=sym, costs=costs, no_overlap=no_overlap)
        if not len(t) or min_spreads is None:
            break
        bad = refused_mask(mk, t, min_spreads)
        if not bad.any():
            break
        ids = t["oid"].to_numpy()[bad]
        refused.extend(int(i) for i in ids)
        o = o[~o["oid"].isin(ids)]
    t = t.copy()
    t.attrs["refused_3spreads"] = len(refused)
    t.attrs["refused_oids"] = refused
    return t


def drop_boundary(t, mk):
    """Trades entered before 2022 whose exit is not inside the slice (still open at its last bar) have no in-sample
    result: they are removed (time exit at the last bar, or 'eod')."""
    if not len(t):
        return t
    last_start = mk.index[-1]
    t = t[t.entry_time < IS_END]
    return t[t.exit_time < last_start]


# --------------------------------------------------------------------------------------------- stats
def window(t, start=COMMON_START, end=IS_END):
    if t is None or not len(t):
        return t
    return t[(t.entry_time >= start) & (t.entry_time < end)]


def sstats(R):
    """Plain statistics of a vector of trade results in R."""
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    n = len(R)
    if n == 0:
        return {"n": 0}
    w, l = R[R > 0], R[R < 0]
    return {"n": int(n), "exp": round(float(R.mean()), 4), "total": round(float(R.sum()), 2),
            "win": round(float((R > 0).mean()), 4), "avg_win": round(float(w.mean()), 4) if len(w) else 0.0,
            "avg_loss": round(float(l.mean()), 4) if len(l) else 0.0,
            "pf": round(float(w.sum() / -l.sum()), 3) if len(l) and l.sum() < 0 else None,
            "sd": round(float(R.std(ddof=1)), 4) if n > 1 else None,
            "mean_over_sd": round(float(R.mean() / R.std(ddof=1)), 4) if n > 1 and R.std(ddof=1) > 0 else None}


def by_year(t):
    if t is None or not len(t):
        return {}
    return {int(y): sstats(g.R) for y, g in t.groupby(t.entry_time.dt.year)}


# --------------------------------------------------------------------------------------------- io
def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def jdump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=_js)


def append_trial(row):
    with open(TRIALS, "a") as f:
        f.write(json.dumps(row, default=_js) + "\n")


TRADE_COLS = ["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "mfe", "mae", "swap", "pnl", "risk",
              "R", "ret", "hold_min"]


def save_trades(t, name):
    cols = [c for c in TRADE_COLS + ["oid"] if c in t.columns]
    t[cols].reset_index(drop=True).to_parquet(os.path.join(OUT, f"{name}.parquet"))


def load_trades(name):
    t = pd.read_parquet(os.path.join(OUT, f"{name}.parquet"))
    assert (t.entry_time < IS_END).all()
    return t
