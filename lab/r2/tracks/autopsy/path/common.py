"""Addendum H, lens `path` -- shared tools (IN SAMPLE ONLY).

Everything here works on price frames cut at 2021-12-31 23:59 UTC at read time (pyarrow filter on the bar
start `ts`, so no 2022+ row is ever materialised) and on official trades read with `entry_time < 2022-01-01`
in the same statement that reads them.  The ten frozen sleeves come from the lab registry
(`lab/r2/recalc.py::sleeves()`, F2_brk_unfiltered left out); every rule is called on the in-sample slice that is
passed to it explicitly (never `r2.run` / `recalc` on a full frame).

Conventions (lab simulator, `goldlab/sim.py`): bars are labelled by their START; a bar is known at its close;
an exit decided on the close of bar d is executed at the OPEN of bar d+1 (time exit `exit_i = d+1`, market
slippage, bid for a long / ask for a short).  R = net pnl / |fill - initial stop|.
"""
import importlib.util
import json
import os
import sys

SCR = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/autopsy_path"
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(SCR, "numba"))
sys.dont_write_bytecode = True

import numba as nb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RES = os.path.join(LAB, "results", "r2", "autopsy", "path")
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

IS_END = pd.Timestamp("2022-01-01", tz="UTC")          # nothing at or after this instant is ever read
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")    # common in-sample window of the ten sleeves
YEARS = (2018, 2019, 2020, 2021)
MIN_NS = 60_000_000_000
NY = "America/New_York"

ORDER = [("noise30", "us100"), ("ocm4", "us100"),
         ("brk72_24h_wd", "btcusd"), ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"),
         ("brk72_24h_wd", "ethusd"), ("F1_brk_ridge_filter", "ethusd"),
         ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]

BUCKET_EDGES = np.array([-0.75, -0.5, -0.25, 0.0, 0.25, 0.5])
BUCKETS = ["<=-0.75", "-0.75..-0.5", "-0.5..-0.25", "-0.25..0", "0..0.25", "0.25..0.5", ">0.5"]
CHECKPOINTS = [("5m", 5, None), ("15m", 15, None), ("30m", 30, None), ("60m", 60, None), ("120m", 120, None),
               ("10%", None, 0.10), ("25%", None, 0.25), ("50%", None, 0.50)]


# ------------------------------------------------------------------------------------------------ data
def load_is(sym, cols=None):
    """FP-cost M1 frame of `sym`, rows with bar start < 2022-01-01 00:00 UTC only (filtered while reading)."""
    path = os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet")
    df = pd.read_parquet(path, columns=cols, filters=[("ts", "<", IS_END)])
    assert df.index.name == "ts" and df.index.is_monotonic_increasing and df.index.max() < IS_END
    return df


def official(name, sym):
    """Official trades of a sleeve, rows with entry_time < 2022-01-01 only (filtered while reading)."""
    path = os.path.join(LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet")
    t = pd.read_parquet(path, filters=[("entry_time", "<", IS_END)])
    assert (t.entry_time < IS_END).all()
    return t.sort_values("entry_time", kind="stable").reset_index(drop=True)


_RC = None


def registry():
    """{(name, sym): (track, make_orders, params)} for the ten sleeves, from lab/r2/recalc.py::sleeves()."""
    global _RC
    if _RC is None:
        spec = importlib.util.spec_from_file_location("r2_recalc_autopsy_path", os.path.join(LAB, "r2", "recalc.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _RC = {(name, sym): (track, mo, params) for track, name, sym, mo, params in m.sleeves()
               if name != "F2_brk_unfiltered"}
        assert len(_RC) == 10 and set(_RC) == set(ORDER)
    return _RC


def clear_rule_caches():
    """Rule modules cache bar frames keyed on id(frame) + length + ends: clear them before every call so that a
    new frame (stress copy) can never be served stale bars of a freed one."""
    for modname, attr in (("r2_ml_strategy", "_cache"), ("strategy_trend", "_bar_cache"), ("strategy_orb", "_daily_cache")):
        mod = sys.modules.get(modname)
        if mod is not None and hasattr(mod, attr):
            getattr(mod, attr).clear()


def build_orders(name, sym, m1, leader=None):
    """Orders of the frozen rule on the frame given (the frame IS the in-sample slice, fp or stressed)."""
    track, mo, params = registry()[(name, sym)]
    clear_rule_caches()
    if name == "nq_btc_follow":
        if leader is None:
            raise ValueError("nq_btc_follow needs the in-sample us100 leader frame")
        mod = sys.modules["r2_leadlag_strategy"]
        mod.clear_leaders()
        mod.set_leader("us100", leader)
    o = mo(m1, **params)
    return o.reset_index(drop=True)


def costs(sym, stress=False):
    return r2.costs(sym, 1.5 if stress else 1.0)


def frame_for(m1, stress):
    return apply_spread_mult(m1, 1.5) if stress else m1


def sim(m1, orders, sym, stress=False, no_overlap=True):
    return simulate(m1, orders, sym=sym, costs=costs(sym, stress), no_overlap=no_overlap)


# ------------------------------------------------------------------------------------------------ bars
def ns_index(m1):
    return m1.index.as_unit("ns").asi8


def to_ns(times):
    return pd.DatetimeIndex(times).as_unit("ns").asi8


def fill_exit_bars(m1, t):
    """Fill bar fi and exit bar x of every trade of a simulate() output (exact timestamp match)."""
    ns = ns_index(m1)
    e = to_ns(t.entry_time)
    fi = np.searchsorted(ns, e)
    assert (ns[np.minimum(fi, len(ns) - 1)] == e).all()
    x_ns = to_ns(t.exit_time) - np.where(t.reason.to_numpy() == "time", 0, MIN_NS)
    xi = np.searchsorted(ns, x_ns)
    assert (ns[np.minimum(xi, len(ns) - 1)] == x_ns).all()
    return fi.astype(np.int64), xi.astype(np.int64)


def planned_end_ns(name, m1, orders_rows, fill_ns):
    """Scheduled time exit of each order (the rule's planned end of life), as UTC ns.
    noise30: 15:55 New York of the session (its band exits are signal exits, not the planned life);
    every other sleeve: the bar of the order's own exit_i (frame end when the exit lies beyond the slice)."""
    ns = ns_index(m1)
    n = len(ns)
    if name == "noise30":
        ny = pd.DatetimeIndex(pd.to_datetime(fill_ns, utc=True)).tz_convert(NY)
        t1555 = (ny.normalize() + pd.Timedelta(hours=15, minutes=55)).tz_convert("UTC")
        xi = gl.exit_index(m1, t1555)
        return ns[np.clip(xi, 0, n - 1)]
    xi = orders_rows["exit_i"].to_numpy(np.int64)
    out = np.where(xi >= 0, ns[np.clip(xi, 0, n - 1)], ns[-1])
    return np.where(xi >= n, ns[-1], out)


def checkpoint_bars(ns, fill_ns, plan_ns, minutes=None, frac=None):
    """Decision bar d of each trade at a checkpoint: the last bar that STARTED before fill + t (so it is closed at
    fill + t).  The exit it decides is executed at the open of d + 1."""
    if minutes is not None:
        tc = fill_ns + np.int64(minutes) * MIN_NS
    else:
        tc = fill_ns + np.round(frac * (plan_ns - fill_ns)).astype(np.int64)
    return (np.searchsorted(ns, tc, side="left") - 1).astype(np.int64), tc


def open_result(m1_arrays, d, side, entry, risk):
    """Open result in R at the CLOSE of bar d on the quote that would close the trade (bid long / ask short),
    before exit slippage and swap."""
    bc, ac = m1_arrays["bc"], m1_arrays["ac"]
    q = np.where(side > 0, bc[d], ac[d])
    return side * (q - entry) / risk


def arrays(m1):
    return {k: m1[k].to_numpy(np.float64) for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")}


@nb.njit(cache=True)
def _path_stats(bh, bl, ah, al, fi, xi, side, entry, risk, exit_px):
    n = len(fi)
    mae = np.empty(n)
    mfe = np.empty(n)
    imae = np.empty(n, np.int64)
    imfe = np.empty(n, np.int64)
    for k in range(n):
        s = side[k]
        e = entry[k]
        r = risk[k]
        g = s * (exit_px[k] - e) / r
        lo = g
        hi = g
        ilo = xi[k]
        ihi = xi[k]
        for j in range(fi[k], xi[k]):          # bars held from open to close (the exit bar is left out)
            if s > 0:
                a = (bl[j] - e) / r
                f = (bh[j] - e) / r
            else:
                a = (e - ah[j]) / r
                f = (e - al[j]) / r
            if a < lo:
                lo = a
                ilo = j
            if f > hi:
                hi = f
                ihi = j
        mae[k] = lo
        mfe[k] = hi
        imae[k] = ilo
        imfe[k] = ihi
    return mae, mfe, imae, imfe


def path_stats(A, fi, xi, t):
    """MAE / MFE in R over the life of each trade, on the closing quote (bid for a long, ask for a short),
    and the bar where each occurs (the exit price counts as the last point of the path)."""
    side = t.side.to_numpy(np.int64)
    return _path_stats(A["bh"], A["bl"], A["ah"], A["al"], fi, xi, side, t.entry.to_numpy(float),
                       t.risk.to_numpy(float), t.exit.to_numpy(float))


# ------------------------------------------------------------------------------------------------ stats
def window(t, which="common"):
    if which == "common":
        return t[(t.entry_time >= COMMON_START) & (t.entry_time < IS_END)]
    if which == "pre":
        return t[t.entry_time < COMMON_START]
    if which == "all":
        return t[t.entry_time < IS_END]
    raise ValueError(which)


def stats(t, years=YEARS):
    R = t["R"].to_numpy(float)
    n = len(R)
    if n == 0:
        return {"n": 0}
    w, l = R[R > 0], R[R <= 0]
    yr = t.entry_time.dt.year.to_numpy()
    out = {"n": int(n), "win_rate": round(float((R > 0).mean()), 4),
           "avg_win_R": round(float(w.mean()), 4) if len(w) else 0.0,
           "avg_loss_R": round(float(l.mean()), 4) if len(l) else 0.0,
           "exp_R": round(float(R.mean()), 4), "total_R": round(float(R.sum()), 2),
           "pf": round(float(w.sum() / -l.sum()), 3) if l.sum() < 0 else None,
           "t_stat": round(float(R.mean() / (R.std(ddof=1) / np.sqrt(n))), 2) if n > 2 else None,
           "by_year": {}}
    for y in (years if years is not None else sorted(set(yr))):
        r = R[yr == y]
        lo = r[r <= 0]
        out["by_year"][int(y)] = {"n": int(len(r)), "total_R": round(float(r.sum()), 2),
                                  "exp_R": round(float(r.mean()), 4) if len(r) else None,
                                  "avg_loss_R": round(float(lo.mean()), 4) if len(lo) else None}
    return out


def jdump(obj, path):
    def conv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if not np.isfinite(o) else float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (pd.Timestamp,)):
            return o.isoformat()
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(type(o))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=conv)


def jline(obj):
    return json.dumps(obj, default=lambda o: (int(o) if isinstance(o, np.integer) else
                                              (float(o) if isinstance(o, np.floating) else
                                               (bool(o) if isinstance(o, np.bool_) else str(o)))))
