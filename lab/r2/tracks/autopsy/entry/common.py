"""Addendum H, lens `entry` (getting in better) -- shared tools.  IN SAMPLE ONLY.

Data discipline (PROTOCOL_V3 Addendum H, hard rule 1):
  * price frames are read with a pyarrow filter on the bar start `ts` < 2022-01-01 00:00 UTC, so no 2022+ row is
    ever materialised; that slice is the frame passed to every rule and every simulation;
  * official trades are read with the filter entry_time < 2022-01-01 in the same statement that reads them;
  * the rules come from the lab registry (lab/r2/recalc.py::sleeves(), F2_brk_unfiltered left out) and are called
    on the in-sample slice (never r2.run / recalc on a full frame).

Simulation: every leg (one order of the lab simulator) is simulated ALONE with the lab engine
(goldlab.sim.simulate, no_overlap=False, FP costs r2.costs(sym) or x1.5); the one-position-per-sleeve rule is then
applied by `chain()` on the signals' activation bars, exactly as the engine does (an order is skipped when its
activation bar <= the exit bar of the sleeve's previous trade).  With the original orders this reproduces
simulate(no_overlap=True) trade for trade (checked in s0_baseline.py).  A signal that keeps a pending order working
also keeps the sleeve busy until its window ends (live-implementable; never binds on the original orders).
"""
import importlib.util
import json
import os
import sys

SCR = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/autopsy_entry"
os.makedirs(SCR, exist_ok=True)
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(SCR, "numba"))
sys.dont_write_bytecode = True

import numba as nb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RES = os.path.join(LAB, "results", "r2", "autopsy", "entry")
os.makedirs(RES, exist_ok=True)
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

IS_END = pd.Timestamp("2022-01-01", tz="UTC")          # nothing at or after this instant is ever read
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")    # common in-sample window of the ten sleeves
YEARS = (2018, 2019, 2020, 2021)
MIN_NS = 60_000_000_000
NY = "America/New_York"

# grouped by market so that each in-sample frame is loaded once
ORDER = [("noise30", "us100"), ("ocm4", "us100"),
         ("brk72_24h_wd", "btcusd"), ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"),
         ("brk72_24h_wd", "ethusd"), ("F1_brk_ridge_filter", "ethusd"),
         ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
A_COLS_LEADER = ["bo", "ao", "bc", "ac"]               # columns of the us100 leader frame (nq_btc_follow)
STOP_ENTRY = ("donch4h_stop", "orb_asia_2d_buf10")     # enter on a stop order (buffers frozen: retest only)
LIMIT_ENTRY = ("GOLD_FRI_PM",)                         # the rule itself enters with a limit order


def key(name, sym):
    return f"{name}:{sym}"


# ------------------------------------------------------------------------------------------------ data
def load_is(sym, cols=None):
    """FP-cost M1 frame of `sym`, rows with bar start < 2022-01-01 00:00 UTC only (filtered while reading)."""
    path = os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet")
    df = pd.read_parquet(path, columns=cols, filters=[("ts", "<", IS_END)])
    assert df.index.name == "ts" and df.index.is_monotonic_increasing and df.index.is_unique
    assert df.index.max() < IS_END
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
        spec = importlib.util.spec_from_file_location("r2_recalc_autopsy_entry", os.path.join(LAB, "r2", "recalc.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _RC = {(name, sym): (track, mo, params) for track, name, sym, mo, params in m.sleeves()
               if name != "F2_brk_unfiltered"}
        assert len(_RC) == 10 and set(_RC) == set(ORDER)
    return _RC


def clear_rule_caches():
    """Rule modules cache bar frames keyed on id(frame) + length + ends: clear them before every call so that a new
    frame (the x1.5 copy) can never be served stale bars of a freed one."""
    for modname, attr in (("r2_ml_strategy", "_cache"), ("strategy_trend", "_bar_cache"),
                          ("strategy_orb", "_daily_cache")):
        mod = sys.modules.get(modname)
        if mod is not None and hasattr(mod, attr):
            getattr(mod, attr).clear()


def build_orders(name, sym, m1, leader=None):
    """Orders of the frozen rule on the frame given (the frame IS the in-sample slice, fp or x1.5)."""
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


def arrays(m1):
    A = {k: m1[k].to_numpy(np.float64) for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")}
    A["ns"] = m1.index.as_unit("ns").asi8
    return A


def to_ns(times):
    return pd.DatetimeIndex(times).as_unit("ns").asi8


# ------------------------------------------------------------------------------------------------ legs -> trades
LAB_COLS = ("entry_i", "side", "etype", "level", "expiry_i", "stop", "stop_dist", "target", "target_dist",
            "exit_i", "trail", "be")
_DEF = {"etype": 0, "level": np.nan, "expiry_i": -1, "stop": np.nan, "stop_dist": np.nan, "target": np.nan,
        "target_dist": np.nan, "exit_i": -1, "trail": np.nan, "be": np.nan}


def lab_orders(o):
    """The lab order columns of a rule's order table (defaults filled), nothing else."""
    out = pd.DataFrame(index=o.index)
    for c in LAB_COLS:
        out[c] = o[c].to_numpy() if c in o else _DEF[c]
    out["entry_i"] = out["entry_i"].astype(np.int64)
    out["side"] = out["side"].astype(np.int64)
    out["etype"] = out["etype"].astype(np.int64)
    out["expiry_i"] = out["expiry_i"].astype(np.int64)
    out["exit_i"] = out["exit_i"].astype(np.int64)
    return out


def sim_legs(m1, A, legs, sym, stress):
    """Simulate every leg alone with the lab engine.  Returns a frame aligned on legs.index with columns
    filled, fi (fill bar), xi (exit bar as the engine's last_exit), entry, exit, stop, risk, R, reason, pnl,
    entry_time, exit_time, spread_fill (ask-bid at the fill bar), refused (stop closer than 3 spreads)."""
    L = legs.reset_index(drop=True)
    orders = L[list(LAB_COLS)]
    n = len(L)
    filled = np.zeros(n, bool)
    refused = np.zeros(n, bool)
    fi_a = np.full(n, -1, np.int64)
    xi_a = np.full(n, -1, np.int64)
    num = {c: np.full(n, np.nan) for c in ("entry", "exit", "stop", "risk", "R", "pnl", "spread_fill")}
    reason = np.full(n, "", dtype=object)
    e_t = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    x_t = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    if n:
        t = simulate(m1, orders, sym=sym, costs=costs(sym, stress), no_overlap=False)
        ns = A["ns"]
        if len(t):
            k = t.index.to_numpy()
            e = to_ns(t.entry_time)
            fi = np.searchsorted(ns, e)
            assert (ns[np.minimum(fi, len(ns) - 1)] == e).all()
            x_ns = to_ns(t.exit_time) - np.where(t.reason.to_numpy() == "time", 0, MIN_NS)
            xi = np.searchsorted(ns, x_ns)
            assert (ns[np.minimum(xi, len(ns) - 1)] == x_ns).all()
            filled[k] = True
            fi_a[k] = fi
            xi_a[k] = xi
            for c in ("entry", "exit", "stop", "risk", "R", "pnl"):
                num[c][k] = t[c].to_numpy(float)
            reason[k] = t["reason"].to_numpy(object)
            e_t[k] = e.astype("datetime64[ns]")
            x_t[k] = to_ns(t.exit_time).astype("datetime64[ns]")
            spr = A["ao"][fi] - A["bo"][fi]
            num["spread_fill"][k] = spr
            refused[k] = t["risk"].to_numpy(float) < 3.0 * spr      # broker: stop closer than 3 spreads
    out = pd.DataFrame({"filled": filled, "refused": refused, "fi": fi_a, "xi": xi_a, **num, "reason": reason,
                        "entry_time": pd.DatetimeIndex(e_t).tz_localize("UTC"),
                        "exit_time": pd.DatetimeIndex(x_t).tz_localize("UTC")})
    out.index = legs.index
    return out


def chain(sig_act, sig_hold, leg_sig, leg_ok, leg_xi):
    """One position per sleeve on signals.

    sig_act[s]  activation bar of signal s (the rule's entry_i);  sig_hold[s] last bar the signal keeps the sleeve busy
    when none of its legs is filled (pending window end, cancellation bar; -1 = nothing working);  leg_sig[l] signal
    of leg l;  leg_ok[l] the leg was filled and accepted;  leg_xi[l] its exit bar.
    Signals are processed by activation bar (stable on their order); a signal is skipped when its activation bar is
    <= the bar until which the sleeve is busy.  Returns taken (bool per signal) and busy_until per signal."""
    ns_ = len(sig_act)
    order = np.argsort(sig_act, kind="stable")
    legs_of = [[] for _ in range(ns_)]
    for l, s in enumerate(leg_sig):
        legs_of[s].append(l)
    taken = np.zeros(ns_, bool)
    busy = -1
    for s in order:
        if sig_act[s] <= busy:
            continue
        taken[s] = True
        end = sig_hold[s]
        for l in legs_of[s]:
            if leg_ok[l]:
                end = max(end, leg_xi[l])
        busy = max(busy, end) if end >= 0 else busy
    return taken


def signal_trades(sigs, legs, res, n_bars=None):
    """Signal-level trades of a variant: taken signals with at least one filled & accepted leg.
    R of a signal = sum over its legs of w x R(leg) (each leg sized to w of the trade's money risk).
    `censored` marks a trade with a leg still open at the end of the frame (exit on its last bar)."""
    ok = (res["filled"] & ~res["refused"]).to_numpy()
    leg_sig = legs["sig"].to_numpy(np.int64)
    taken = chain(sigs["act"].to_numpy(np.int64), sigs["hold"].to_numpy(np.int64), leg_sig, ok,
                  res["xi"].to_numpy(np.int64))
    sigs = sigs.copy()
    sigs["taken"] = taken
    L = pd.DataFrame({"sig": leg_sig, "leg": legs["leg"].to_numpy(np.int64), "w": legs["w"].to_numpy(float),
                      "ok": ok, "R": res["R"].to_numpy(float),
                      "entry_time": res["entry_time"].to_numpy(), "exit_time": res["exit_time"].to_numpy(),
                      "risk": res["risk"].to_numpy(float), "entry": res["entry"].to_numpy(float),
                      "reason": res["reason"].to_numpy(), "refused": res["refused"].to_numpy(),
                      "filled": res["filled"].to_numpy(), "xi": res["xi"].to_numpy(np.int64)})
    L = L[taken[L.sig.to_numpy()]]
    Lok = L[L.ok].copy()
    Lok["wR"] = Lok.w * Lok.R
    g = Lok.groupby("sig")
    tr = pd.DataFrame({"R": g["wR"].sum(), "entry_time": g["entry_time"].min(), "exit_time": g["exit_time"].max(),
                       "n_legs": g.size(), "last_xi": g["xi"].max()})
    tr["censored"] = (tr.last_xi == n_bars - 1) if n_bars is not None else False
    tr = tr.join(sigs[["act", "side"]], how="left")
    tr = tr.sort_values("entry_time", kind="stable")
    sigs["filled"] = sigs.index.isin(tr.index)
    sigs["n_refused"] = L.groupby("sig")["refused"].sum().reindex(sigs.index).fillna(0).astype(int)
    return tr, sigs


# ------------------------------------------------------------------------------------------------ stats
def window(t, which="common", col="entry_time"):
    tt = pd.DatetimeIndex(t[col])
    if which == "common":
        return t[(tt >= COMMON_START) & (tt < IS_END)]
    if which == "pre":
        return t[tt < COMMON_START]
    if which == "all":
        return t[tt < IS_END]
    raise ValueError(which)


def stats(t, years=YEARS):
    R = t["R"].to_numpy(float)
    n = len(R)
    if n == 0:
        return {"n": 0, "total_R": 0.0, "exp_R": None, "by_year": {}}
    w, l = R[R > 0], R[R <= 0]
    yr = pd.DatetimeIndex(t.entry_time).year.to_numpy()
    out = {"n": int(n), "win_rate": round(float((R > 0).mean()), 4),
           "avg_win_R": round(float(w.mean()), 4) if len(w) else 0.0,
           "avg_loss_R": round(float(l.mean()), 4) if len(l) else 0.0,
           "exp_R": round(float(R.mean()), 4), "total_R": round(float(R.sum()), 2),
           "pf": round(float(w.sum() / -l.sum()), 3) if l.sum() < 0 else None,
           "t_stat": round(float(R.mean() / (R.std(ddof=1) / np.sqrt(n))), 2) if n > 2 and R.std() > 0 else None,
           "by_year": {}}
    for y in (years if years is not None else sorted(set(yr))):
        r = R[yr == y]
        lo = r[r <= 0]
        out["by_year"][int(y)] = {"n": int(len(r)), "total_R": round(float(r.sum()), 2),
                                  "exp_R": round(float(r.mean()), 4) if len(r) else None,
                                  "avg_loss_R": round(float(lo.mean()), 4) if len(lo) else None}
    return out


def jconv(o):
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


def jdump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=jconv)


def jline(obj):
    return json.dumps(obj, default=jconv)
