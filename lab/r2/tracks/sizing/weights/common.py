"""Lens `weights` of PROTOCOL_V3 Addendum I: ONE STAKE PER SLEEVE. IN SAMPLE ONLY. Shared helpers.

Data rule (task rule 1). Every price frame is read with a pyarrow row filter `ts < 2022-01-01 00:00 UTC` (no 2022+
row ever enters the process) and that slice is passed explicitly to every rule and every simulation. Every official
trades file is read with the row filter `entry_time < 2022-01-01` in the read itself; the rows whose R is compared
are read with `entry_time < 2022-01-01` AND `exit_time < 2022-01-01` (no result realised in 2022 is read). The rules
and frozen parameters come from lab/r2/recalc.py::sleeves() (imported under a private module name; nothing in it is
run on a full frame). nq_btc_follow always gets the in-sample us100 slice as its leader (never the module default).

Account used THROUGHOUT this lens: the PLAIN SUM of the ten sleeves' one-position chains (each sleeve one position at
a time as in the official runs, no cap across sleeves). A trade's result is stake x R, stake = 1 base x the variant's
multiplier. This is synthesis_B's reference portfolio P0 (5,205 trades, +788.6 R, entries 2018-02..2021-12, FP).
A multiplier of 0 means the trade is followed on paper only: the sleeve's chain is never changed by a stake.

Clock: FP server time = New York local time + 7 h. A server week runs Monday 00:00 - Sunday 24:00 (server). A trade's
result is booked in the server week of its EXIT time. The year of a week is the year of its Thursday (ISO style).
Every calendar week of the period is counted, an empty week counts 0.

Run with:  NUMBA_CACHE_DIR=/tmp/numba_weights PYTHONDONTWRITEBYTECODE=1 python3 <script>.py
"""
import importlib.util
import json
import os
import sys

if not os.environ.get("NUMBA_CACHE_DIR", "").startswith("/tmp/"):
    raise SystemExit("set NUMBA_CACHE_DIR to a directory under /tmp before importing the lab")
if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
    raise SystemExit("set PYTHONDONTWRITEBYTECODE=1")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(LAB, "results", "r2", "sizing", "weights")
CHAINS = os.path.join(OUT, "chains")       # reference chains of the ten sleeves, fp and stress
TRIALS = os.path.join(OUT, "trials.jsonl")
DECLARED = os.path.join(OUT, "declared.json")
for _d in (OUT, CHAINS):
    os.makedirs(_d, exist_ok=True)
if LAB not in sys.path:
    sys.path.insert(0, LAB)

import goldlab as gl  # noqa: E402,F401
from goldlab import r2  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

IS_END = pd.Timestamp("2022-01-01", tz="UTC")
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")
NY = "America/New_York"
OFFICIAL_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")
PURGE = pd.Timedelta(days=7)
OOF = (2019, 2020, 2021)                  # out-of-fold years that judge
MODES = ("fp", "stress")

SLEEVES = [("ocm4", "us100"), ("noise30", "us100"),
           ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd"), ("GOLD_FRI_PM", "xauusd"),
           ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("nq_btc_follow", "btcusd")]
RULES = ["noise30", "ocm4", "donch4h_stop", "orb_asia_2d_buf10", "GOLD_FRI_PM", "brk72_24h_wd",
         "F1_brk_ridge_filter", "nq_btc_follow"]
KEYS = [f"{n}__{s}" for n, s in SLEEVES]
F1_KEYS = ("F1_brk_ridge_filter__btcusd", "F1_brk_ridge_filter__ethusd")
UNIVERSES = {"U10": KEYS, "U8_noF1": [k for k in KEYS if k not in F1_KEYS]}
SHORT = {"ocm4__us100": "ocm4", "noise30__us100": "noise30", "donch4h_stop__xauusd": "donch4h",
         "orb_asia_2d_buf10__xauusd": "orb_gold", "GOLD_FRI_PM__xauusd": "gold_fri",
         "brk72_24h_wd__btcusd": "brk72_btc", "brk72_24h_wd__ethusd": "brk72_eth",
         "F1_brk_ridge_filter__btcusd": "F1_btc", "F1_brk_ridge_filter__ethusd": "F1_eth",
         "nq_btc_follow__btcusd": "nq_btc"}


def key(name, sym):
    return f"{name}__{sym}"


# ============================================================================================ data
def load_is(sym):
    """FP-cost M1 frame of `sym`, rows with bar start < 2022-01-01 00:00 UTC only (filtered while reading)."""
    df = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), filters=[("ts", "<", IS_END)])
    assert df.index.is_monotonic_increasing and df.index.is_unique and df.index.max() < IS_END
    return df


def official_count(name, sym):
    """Official rows of a sleeve entered before 2022: (n entered, n of them closed in 2022, total R of the rows
    closed before 2022). Reads entry_time and exit_time with the entry filter in the read; R only for the rows also
    closed before 2022 (second read, both filters in it)."""
    t = pd.read_parquet(os.path.join(OFFICIAL_DIR, f"{name}__{sym}.parquet"), columns=["entry_time", "exit_time"],
                        filters=[("entry_time", "<", IS_END)])
    assert (t.entry_time < IS_END).all()
    return int(len(t)), int((t.exit_time >= IS_END).sum())


def official_closed(name, sym):
    """Official rows entered AND closed before 2022 (both filters in the read)."""
    t = pd.read_parquet(os.path.join(OFFICIAL_DIR, f"{name}__{sym}.parquet"),
                        filters=[("entry_time", "<", IS_END), ("exit_time", "<", IS_END)])
    assert (t.entry_time < IS_END).all() and (t.exit_time < IS_END).all()
    return t.sort_values("entry_time", kind="stable").reset_index(drop=True)


# ============================================================================================ rules
_REG = None


def registry():
    """{rule name: (track, make_orders, params)} from lab/r2/recalc.py::sleeves() (F2_brk_unfiltered left out)."""
    global _REG
    if _REG is None:
        spec = importlib.util.spec_from_file_location("r2_recalc_weights", os.path.join(LAB, "r2", "recalc.py"))
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


def build_orders(rule, mk, leader=None):
    """Orders of the frozen rule on the frame given (an in-sample slice, fp or stressed), with oid = row number.
    `leader`: the in-sample us100 frame (bo, ao, bc, ac) for nq_btc_follow."""
    track, mo, params = registry()[rule]
    clear_rule_caches()
    if rule == "nq_btc_follow":
        if leader is None:
            raise ValueError("nq_btc_follow needs the in-sample us100 leader")
        mod = sys.modules["r2_leadlag_strategy"]
        mod.clear_leaders()
        mod.set_leader("us100", leader)
    o = mo(mk, **params).reset_index(drop=True)
    o["oid"] = np.arange(len(o), dtype=np.int64)
    return o


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
    """Trades whose initial stop is closer than 3 spreads of their fill bar, or crossed at the fill ('gap')."""
    if not len(t):
        return np.zeros(0, bool)
    spr = (mk["ao"].to_numpy() - mk["bo"].to_numpy())
    fi = mk.index.searchsorted(t.entry_time)
    bad = t["risk"].to_numpy() < min_spreads * spr[fi]
    bad |= t["reason"].to_numpy() == "gap"
    return bad


def simulate_filtered(mk, orders, sym, costs, no_overlap=True, max_iter=20):
    """simulate() with the broker's minimum stop distance (3 spreads): an order whose trade would violate it is
    removed (the sleeve stays flat) and the sleeve re-simulated until no taken trade violates it."""
    o = orders.reset_index(drop=True).copy()
    refused = []
    t = None
    for _ in range(max_iter):
        t = simulate(mk, o, sym=sym, costs=costs, no_overlap=no_overlap)
        if not len(t):
            break
        bad = refused_mask(mk, t)
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
    """Trades entered before 2022 that are still open at the last bar of the slice have no in-sample result."""
    if not len(t):
        return t
    last_start = mk.index[-1]
    t = t[t.entry_time < IS_END]
    return t[t.exit_time < last_start]


CHAIN_COLS = ["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk", "R",
              "hold_min", "oid"]


def chain_path(k, mode):
    return os.path.join(CHAINS, f"{k}__{mode}.parquet")


def load_chain(k, mode):
    t = pd.read_parquet(chain_path(k, mode))
    assert (t.entry_time < IS_END).all() and (t.exit_time < IS_END).all()
    return t


def load_book(mode, keys=None):
    """All reference trades of the sleeves `keys` (default the ten), one row per trade, sorted by entry time then
    sleeve order: columns k (sleeve key), t_in, t_out (UTC ns), R, side, wk_out (server week of the exit),
    year_in (UTC year of the entry)."""
    keys = KEYS if keys is None else keys
    fr = []
    for k in keys:
        t = load_chain(k, mode)
        fr.append(pd.DataFrame({"k": k, "t_in": pd.DatetimeIndex(t.entry_time).as_unit("ns"),
                                "t_out": pd.DatetimeIndex(t.exit_time).as_unit("ns"),
                                "R": t.R.to_numpy(float), "side": t.side.to_numpy(np.int64)}))
    b = pd.concat(fr, ignore_index=True)
    b["ko"] = b.k.map({k: i for i, k in enumerate(KEYS)}).astype(np.int64)
    b = b.sort_values(["t_in", "ko"], kind="stable").reset_index(drop=True)
    b["wk_out"] = week_id(b.t_out)
    b["year_in"] = b.t_in.dt.year.to_numpy()
    return b


# ============================================================================================ weeks and metrics
def server_naive(ts):
    return pd.DatetimeIndex(ts).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)


def server_day(ts):
    return server_naive(ts).values.astype("datetime64[D]").astype(np.int64)


def week_id(ts):
    """FP server week (Monday-Sunday, server clock = New York + 7 h); 1970-01-01 is a Thursday"""
    return (server_day(ts) + 3) // 7


def week_start_server(w):
    """server-clock Monday 00:00 (naive) of week id w"""
    return pd.Timestamp("1970-01-01") + pd.Timedelta(days=int(w) * 7 - 3)


def week_year(w):
    """ISO-style year of a server week: the year of its Thursday"""
    return pd.DatetimeIndex((np.asarray(w, np.int64) * 7).astype("datetime64[D]")).year.to_numpy()


def weeks_of_years(years):
    """every server week whose Thursday falls in one of `years`"""
    lo = pd.Timestamp(f"{min(years)}-01-01")
    hi = pd.Timestamp(f"{max(years)}-12-31")
    d0 = (lo - pd.Timestamp("1970-01-01")).days
    d1 = (hi - pd.Timestamp("1970-01-01")).days
    ws = np.arange((d0 - 7) // 7, d1 // 7 + 2)
    yy = week_year(ws)
    return ws[np.isin(yy, list(years))]


def longest_run(neg):
    best = cur = 0
    for v in neg:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return int(best)


def max_dd(x):
    c = np.r_[0.0, np.cumsum(np.asarray(x, float))]
    return float((np.maximum.accumulate(c) - c).max())


def sharpe(ws):
    ws = np.asarray(ws, float)
    sd = float(np.std(ws, ddof=1)) if len(ws) > 1 else 0.0
    return float(np.mean(ws) / sd * np.sqrt(52)) if sd > 0 else float("nan")


def sstats(R):
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    n = len(R)
    if n == 0:
        return {"n": 0}
    w, l = R[R > 0], R[R < 0]
    sd = float(R.std(ddof=1)) if n > 1 else float("nan")
    return {"n": int(n), "exp": round(float(R.mean()), 4), "total": round(float(R.sum()), 2),
            "sd": round(sd, 4), "mean_over_sd": round(float(R.mean()) / sd, 4) if n > 1 and sd > 0 else None,
            "win": round(float((R > 0).mean()), 4), "avg_loss": round(float(l.mean()), 4) if len(l) else 0.0,
            "pf": round(float(w.sum() / -l.sum()), 3) if len(l) and l.sum() < 0 else None}


# ============================================================================================ io
def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _clean(o):
    """NaN / inf -> None recursively (strict JSON)."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, np.floating):
        return None if not np.isfinite(o) else float(o)
    return o


def jdump(obj, path):
    with open(path, "w") as f:
        json.dump(_clean(obj), f, indent=1, default=_js)


def append_trial(row):
    with open(TRIALS, "a") as f:
        f.write(json.dumps(_clean(row), default=_js) + "\n")
