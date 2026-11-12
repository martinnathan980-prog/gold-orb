"""Lens `clock` of PROTOCOL_V3 Addendum I: stakes or skips by hour band and weekday. IN SAMPLE ONLY.

Data rule. Every price frame is read with a pyarrow row filter `ts < 2022-01-01 00:00 UTC` (no 2022+ row ever
enters the process) and that slice is passed explicitly to every rule and every simulation. Every official trades
file is read with the row filter `entry_time < 2022-01-01` in the read itself (and, for the R comparison, also
`exit_time < 2022-01-01`, so that no result realised in 2022 is read). The rules and frozen parameters come from
lab/r2/recalc.py::sleeves() (imported under a private module name, nothing in it is run). nq_btc_follow always gets
the in-sample us100 slice as its leader (never the module's default loader).

Account used throughout: the PLAIN SUM of the ten sleeves' one-position chains (each sleeve one position at a time,
no cap across sleeves), stake 1 R per trade times the variant's multiplier: the convention of synthesis_B's P0.

Run with:  NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 <script>.py
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
OUT = os.path.join(LAB, "results", "r2", "sizing", "clock")
BASE = os.path.join(OUT, "base")          # per-sleeve signal tables and reference chains (fp, stress)
VAR = os.path.join(OUT, "variants")       # re-simulated chains of the skip variants
TRIALS = os.path.join(OUT, "trials.jsonl")
DECLARED = os.path.join(OUT, "declared.json")
for d in (OUT, BASE, VAR):
    os.makedirs(d, exist_ok=True)
if LAB not in sys.path:
    sys.path.insert(0, LAB)

import goldlab as gl  # noqa: E402,F401
from goldlab import r2  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

IS_END = pd.Timestamp("2022-01-01", tz="UTC")
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")
NY = "America/New_York"
LDN = "Europe/London"
OFFICIAL_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")
PURGE = pd.Timedelta(days=7)
OOF = (2019, 2020, 2021)                  # out-of-fold years that judge
EARLY = (2018,)                           # reported apart, judge nothing
MODES = ("fp", "stress")

SLEEVES = [("ocm4", "us100"), ("noise30", "us100"),
           ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd"), ("GOLD_FRI_PM", "xauusd"),
           ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("nq_btc_follow", "btcusd")]
RULES = ["noise30", "ocm4", "donch4h_stop", "orb_asia_2d_buf10", "GOLD_FRI_PM", "brk72_24h_wd",
         "F1_brk_ridge_filter", "nq_btc_follow"]
KEYS = [f"{n}__{s}" for n, s in SLEEVES]
FAMILY = {"ocm4__us100": "us100", "noise30__us100": "us100",
          "donch4h_stop__xauusd": "gold", "orb_asia_2d_buf10__xauusd": "gold", "GOLD_FRI_PM__xauusd": "gold_fri",
          "brk72_24h_wd__btcusd": "crypto", "brk72_24h_wd__ethusd": "crypto", "F1_brk_ridge_filter__btcusd": "crypto",
          "F1_brk_ridge_filter__ethusd": "crypto", "nq_btc_follow__btcusd": "crypto"}


def key(name, sym):
    return f"{name}__{sym}"


# ============================================================================================ hour bands
# Declared in declared.json BEFORE any band statistic was computed. Clock time of a signal = start of its FILL
# bar (for the market-entry sleeves this is the decision minute, 0-5 minutes later at most; for the two gold
# stop-entry sleeves it is the touch, known when it happens). Bands are equal-length parts of the sleeve's own
# window of decision (or fill) times, in New York wall-clock time (London for orb_asia_2d_buf10, whose window is
# set on the London clock). Lower bound included, upper bound excluded; hours as decimal hours.
BANDS = {
    "ocm4__us100": None,                                         # one decision time (09:34 NY): no hour band
    "noise30__us100": ("NY", [(10.0, 12.0), (12.0, 14.0), (14.0, 16.0)]),        # checks 10:00-11:30 / 12:00-13:30 / 14:00-15:30
    "donch4h_stop__xauusd": ("NY", [(0.0, 6.0), (6.0, 12.0), (12.0, 18.0), (18.0, 24.0)]),
    "orb_asia_2d_buf10__xauusd": ("LDN", [(7.0, 7.0 + 100 / 60), (7.0 + 100 / 60, 7.0 + 200 / 60), (7.0 + 200 / 60, 12.0 + 1.5 / 60)]),
    "GOLD_FRI_PM__xauusd": None,                                 # one decision time (Friday 13:30 NY): untouched
    "brk72_24h_wd__btcusd": ("NY", [(0.0, 6.0), (6.0, 12.0), (12.0, 18.0), (18.0, 24.0)]),
    "brk72_24h_wd__ethusd": ("NY", [(0.0, 6.0), (6.0, 12.0), (12.0, 18.0), (18.0, 24.0)]),
    "F1_brk_ridge_filter__btcusd": ("NY", [(3.0, 7.0), (7.0, 11.0), (11.0, 16.0)]),   # decisions 03-06 / 07-10 / 11-15 NY
    "F1_brk_ridge_filter__ethusd": ("NY", [(3.0, 7.0), (7.0, 11.0), (11.0, 16.0)]),
    "nq_btc_follow__btcusd": ("NY", [(9.5, 11.5), (11.5, 13.5), (13.5, 16.0 + 6 / 60)]),
}
NO_WEEKDAY = ("GOLD_FRI_PM__xauusd",)                            # Fridays only: untouched


def local_hours(ts, tz):
    """decimal wall-clock hours of UTC timestamps in zone tz"""
    x = pd.DatetimeIndex(ts).tz_convert(tz)
    return (x.hour + x.minute / 60.0 + x.second / 3600.0).to_numpy(np.float64)


def server_weekday(ts):
    """weekday (0 = Monday) of the FP server clock (New York + 7 h): the trading day of the 17:00 NY roll"""
    x = pd.DatetimeIndex(ts).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)
    return x.dayofweek.to_numpy()


def hour_band(k, ts):
    """band number (0..) of each fill time for sleeve k, -1 outside every band, None if the sleeve has no bands"""
    spec = BANDS[k]
    if spec is None:
        return None
    clock, bands = spec
    h = local_hours(ts, NY if clock == "NY" else LDN)
    out = np.full(len(h), -1, np.int64)
    for j, (a, b) in enumerate(bands):
        out[(h >= a) & (h < b)] = j
    return out


# ============================================================================================ data
def load_is(sym):
    """FP-cost M1 frame of `sym`, rows with bar start < 2022-01-01 00:00 UTC only (filtered while reading)."""
    df = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), filters=[("ts", "<", IS_END)])
    assert df.index.is_monotonic_increasing and df.index.is_unique and df.index.max() < IS_END
    return df


def official_count(name, sym):
    """Official rows of a sleeve entered before 2022: (n entered, n of them closed in 2022). Reads entry_time and
    exit_time only, with the entry filter in the read (no result of a 2022 exit is read)."""
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
        spec = importlib.util.spec_from_file_location("r2_recalc_clock", os.path.join(LAB, "r2", "recalc.py"))
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
    """Rule modules cache bar frames keyed on id(frame): cleared before every call."""
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
    """Orders of the frozen rule on the frame given (an in-sample slice, fp or stressed), with oid = row number."""
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


# ============================================================================================ weeks and metrics
def server_day(ts):
    return (pd.DatetimeIndex(ts).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)).values.astype("datetime64[D]").astype(np.int64)


def week_id(ts):
    """FP server week (Monday-Sunday, server clock = New York + 7 h); 1970-01-01 is a Thursday"""
    return (server_day(ts) + 3) // 7


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


def weekly(book, years, col="pnl"):
    """weekly sums of book[col] (trades booked at their exit week) over every week of `years` (empty weeks = 0);
    book must contain only trades entered in `years` (the caller selects)"""
    ws = weeks_of_years(years)
    s = pd.Series(book[col].to_numpy(float)).groupby(week_id(book.exit_time)).sum()
    return s.reindex(ws, fill_value=0.0)


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
    sd = float(np.std(ws, ddof=1))
    return float(np.mean(ws) / sd * np.sqrt(52)) if sd > 0 else float("nan")


def sstats(R):
    R = np.asarray(R, float)
    R = R[np.isfinite(R)]
    n = len(R)
    if n == 0:
        return {"n": 0}
    w, l = R[R > 0], R[R < 0]
    return {"n": int(n), "exp": round(float(R.mean()), 4), "total": round(float(R.sum()), 2),
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


def jdump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=_js)


def jload(path):
    with open(path) as f:
        return json.load(f)


def append_trial(row):
    with open(TRIALS, "a") as f:
        f.write(json.dumps(row, default=_js) + "\n")
