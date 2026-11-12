"""PROTOCOL_V3 Addendum I, lead synthesis: shared helpers. IN SAMPLE ONLY.

Data rules
- Price frames: read with the parquet row filter ts < 2022-01-01 00:00 UTC (no 2022+ row ever enters the process);
  only those slices are given to the rules and to the simulator.
- Official trades: read with entry_time < 2022-01-01 AND exit_time < 2022-01-01 in the read statement (the two gold
  trades entered on 2021-12-31 whose official exit is in 2022 are counted, never read).
- nq_btc_follow's leader is registered from the in-sample us100 slice before any of its orders is built (otherwise
  the rule would read the research file to 2025).
- Context-lens tables (signals with causal descriptors) are read with t_dec < 2022-01-01 in the read statement.
- Writes only in lab/r2/tracks/sizing/synthesis/ and lab/results/r2/sizing/synthesis.json.

The account: the PLAIN SUM of the sleeves' one-position chains (no 6 / 2 caps, no compounding), 1 R x stake.
Weeks: FP server weeks (New York + 7 h, Monday..Sunday), booked at the EXIT; empty weeks count as 0.
Out-of-fold window: the 157 server weeks whose Thursday falls in 2019, 2020 or 2021.

Run with:  NUMBA_CACHE_DIR=/tmp/synthI_numba PYTHONDONTWRITEBYTECODE=1 python3 <script>.py
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
TRIALS = os.path.join(HERE, "trials.jsonl")
RESULT = os.path.join(LAB, "results", "r2", "sizing", "synthesis.json")
OFFICIAL_DIR = os.path.join(LAB, "results", "r2", "recalc", "trades")
CTX_RES = os.path.join(LAB, "results", "r2", "autopsy", "context")
for p in (LAB, os.path.join(LAB, "r2")):
    if p not in sys.path:
        sys.path.insert(0, p)

import goldlab as gl  # noqa: E402,F401
from goldlab import r2  # noqa: E402
from goldlab.sim import apply_spread_mult, simulate  # noqa: E402

IS_END = pd.Timestamp("2022-01-01", tz="UTC")
IS_END_NS = int(IS_END.value)
NS_DAY = 86_400 * 10 ** 9
PURGE_NS = 7 * NS_DAY
MODES = ("fp", "stress")
OOF_YEARS = (2019, 2020, 2021)

SLEEVES = [("ocm4", "us100"), ("noise30", "us100"),
           ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd"), ("GOLD_FRI_PM", "xauusd"),
           ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("nq_btc_follow", "btcusd")]
KEYS = [f"{n}__{s}" for n, s in SLEEVES]
CRYPTO_BRK = ["brk72_24h_wd__btcusd", "brk72_24h_wd__ethusd", "F1_brk_ridge_filter__btcusd",
              "F1_brk_ridge_filter__ethusd"]
NEW_KEYS = ["new_orb_asia_2d_buf10__ethusd", "new_orb_asia_2d_buf10__btcusd"]
BY_SYM = {}
for _n, _s in SLEEVES:
    BY_SYM.setdefault(_s, []).append(_n)


def split_key(k):
    name, sym = k.split("__")
    return name.replace("new_", ""), sym


def year_start_ns(y):
    return int(pd.Timestamp(f"{y}-01-01", tz="UTC").value)


def train_cut_ns(y):
    return year_start_ns(y) - PURGE_NS


def ns_of(ts):
    x = pd.DatetimeIndex(ts)
    if x.tz is not None:
        x = x.tz_convert("UTC").tz_localize(None)
    return x.values.astype("datetime64[ns]").astype(np.int64)


# ------------------------------------------------------------------------------------------- data
def load_is(sym):
    """FP-cost M1 frame, rows with bar start < 2022-01-01 00:00 UTC only (cut inside the read)."""
    df = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), filters=[("ts", "<", IS_END)])
    assert df.index.is_monotonic_increasing and df.index.is_unique and df.index.max() < IS_END
    return df


def official_closed(name, sym):
    """Official rows entered AND closed before 2022 (both filters in the read)."""
    t = pd.read_parquet(os.path.join(OFFICIAL_DIR, f"{name}__{sym}.parquet"),
                        filters=[("entry_time", "<", IS_END), ("exit_time", "<", IS_END)])
    assert (t.entry_time < IS_END).all() and (t.exit_time < IS_END).all()
    return t.sort_values("entry_time", kind="stable").reset_index(drop=True)


def official_open_at_end_count(name, sym):
    """Number of official rows entered before 2022 whose exit is not before 2022: only their entry time is read."""
    t = pd.read_parquet(os.path.join(OFFICIAL_DIR, f"{name}__{sym}.parquet"), columns=["entry_time"],
                        filters=[("entry_time", "<", IS_END), ("exit_time", ">=", IS_END)])
    assert (t.entry_time < IS_END).all()
    return int(len(t)), [str(x) for x in t.entry_time]


def load_ctx_signals(k, mode):
    """Context lens signal table (every order of the rule, causal descriptors at the decision); riskbp added."""
    s = pd.read_parquet(os.path.join(CTX_RES, "signals", f"{k}__{mode}.parquet"), filters=[("t_dec", "<", IS_END_NS)])
    assert int(s.t_dec.max()) < IS_END_NS
    assert (s.oid.to_numpy() == np.arange(len(s))).all()
    s = s.copy()
    s["riskbp"] = s.risk / s.P * 1e4
    return s


def load_ctx_chain(k, mode):
    c = pd.read_parquet(os.path.join(CTX_RES, "chains", f"{k}__{mode}.parquet"), filters=[("entry_time", "<", IS_END)])
    assert (c.entry_time < IS_END).all() and (c.exit_time < IS_END).all()
    return c.sort_values("entry_time", kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------------------------------- rules
_REG = None


def registry():
    """{rule name: (track, make_orders, params)} from lab/r2/recalc.py::sleeves(), called ONCE per process (its loader
    registers the rule modules in sys.modules under fixed names; their caches are cleared before every call)."""
    global _REG
    if _REG is None:
        spec = importlib.util.spec_from_file_location("r2_recalc_synthI", os.path.join(LAB, "r2", "recalc.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        reg = {}
        for track, name, sym, mo, params in m.sleeves():
            if name == "F2_brk_unfiltered" or name in reg:
                continue
            reg[name] = (track, mo, dict(params))
        assert set(reg) == {n for n, _ in SLEEVES}, sorted(reg)
        _REG = reg
    return _REG


def clear_rule_caches():
    for modname, attr in (("r2_ml_strategy", "_cache"), ("strategy_trend", "_bar_cache"),
                          ("strategy_orb", "_daily_cache")):
        mod = sys.modules.get(modname)
        if mod is not None and hasattr(mod, attr):
            getattr(mod, attr).clear()
    mod = sys.modules.get("idxus_lib")
    if mod is not None:
        mod._grid_cache.clear()
        mod._atr_cache.clear()


def set_leader_is(us_is):
    registry()
    L = sys.modules["r2_leadlag_strategy"]
    L.clear_leaders()
    L.set_leader("us100", us_is)
    tmin = L._LEADERS["us100"][0]
    assert int(tmin.max()) * 60 * 10 ** 9 < IS_END_NS


def build_orders(name, mk):
    track, mo, params = registry()[name]
    clear_rule_caches()
    if name == "nq_btc_follow":
        assert "us100" in sys.modules["r2_leadlag_strategy"]._LEADERS, "set_leader_is() first"
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
    return r2.costs(sym) if mode == "fp" else r2.costs(sym, 1.5)


def refused_mask(mk, t, min_spreads=3.0):
    if not len(t):
        return np.zeros(0, bool)
    spr = mk["ao"].to_numpy() - mk["bo"].to_numpy()
    fi = mk.index.searchsorted(t.entry_time)
    bad = t["risk"].to_numpy() < min_spreads * spr[fi]
    bad |= t["reason"].to_numpy() == "gap"
    return bad


def chain(mk, orders, sym, mode, exclude=frozenset(), max_iter=20):
    """One-position chain of a sleeve: orders in `exclude` (oids) not sent; an order whose stop is closer than 3
    spreads of its fill bar is refused and the sleeve re-simulated; trades still open at the last bar dropped."""
    o = orders[~orders.oid.isin(set(exclude))]
    refused = []
    t = None
    for _ in range(max_iter):
        t = simulate(mk, o, sym=sym, costs=mode_costs(sym, mode), no_overlap=True)
        bad = refused_mask(mk, t)
        if not bad.any():
            break
        ids = t["oid"].to_numpy()[bad]
        refused.extend(int(i) for i in ids)
        o = o[~o.oid.isin(ids)]
    last_start = mk.index[-1]
    t = t[(t.entry_time < IS_END) & (t.exit_time < last_start)].reset_index(drop=True)
    t.attrs["refused"] = refused
    return t


def every_signal(mk, orders, sym, mode):
    return simulate(mk, orders, sym=sym, costs=mode_costs(sym, mode), no_overlap=False)


# ------------------------------------------------------------------------------------------- weeks and measures
def server_days(t_ns):
    loc = pd.DatetimeIndex(np.asarray(t_ns, np.int64).astype("datetime64[ns]")).tz_localize("UTC") \
        .tz_convert("America/New_York").tz_localize(None) + pd.Timedelta(hours=7)
    return (loc.values.astype("datetime64[D]") - np.datetime64("1970-01-01", "D")).astype(np.int64)


def server_week(t_ns):
    """Monday-based server week number; day 0 (1970-01-01) is a Thursday, so the Thursday of week w is day 7w."""
    return (server_days(t_ns) + 3) // 7


def week_thursday_year(w):
    d = np.datetime64("1970-01-01", "D") + (7 * np.asarray(w, np.int64)).astype("timedelta64[D]")
    return pd.DatetimeIndex(d).year.to_numpy()


def oof_weeks(years=OOF_YEARS):
    lo = int((np.datetime64(f"{min(years)}-01-01", "D") - np.datetime64("1970-01-01", "D")).astype(np.int64))
    hi = int((np.datetime64(f"{max(years)}-12-31", "D") - np.datetime64("1970-01-01", "D")).astype(np.int64))
    w = np.arange(-(-lo // 7), hi // 7 + 1)
    assert set(week_thursday_year(w)) == set(years)
    return w


OOF_W = oof_weeks()
YEAR_W = {y: OOF_W[week_thursday_year(OOF_W) == y] for y in OOF_YEARS}


def book_rows(key, trades, stakes):
    """one row per chain trade: sleeve, oid, exit week, stake, R, pnl = stake x R"""
    st = np.asarray(stakes, float)
    assert len(st) == len(trades)
    R = trades.R.to_numpy(float)
    return pd.DataFrame({"sleeve": key, "oid": trades.oid.to_numpy(np.int64),
                         "week": server_week(ns_of(trades.exit_time)), "stake": st, "R": R, "pnl": st * R})


def weekly(book, weeks):
    return book.groupby("week")["pnl"].sum().reindex(weeks, fill_value=0.0).to_numpy(np.float64)


def sharpe(w):
    sd = float(np.std(w, ddof=1))
    return float(np.mean(w) / sd * np.sqrt(52)) if sd > 0 else float("nan")


def longest_neg_run(w):
    best = cur = 0
    for v in w:
        cur = cur + 1 if v < 0 else 0
        best = max(best, cur)
    return int(best)


def max_fall(w):
    c = np.cumsum(w)
    peak = np.maximum.accumulate(np.r_[0.0, c])[1:]
    return float(np.max(peak - c)) if len(c) else 0.0


def measures(book, weeks, scale, months):
    w = weekly(book, weeks) * scale
    b = book[book.week.isin(weeks)]
    taken = b.stake.to_numpy() > 0
    R = b.R.to_numpy()[taken]
    st = b.stake.to_numpy()[taken]
    n = int(taken.sum())
    tot = float(w.sum())
    return {"weeks": int(len(w)), "trades": n, "sharpe": round(sharpe(w), 4),
            "total_R": round(tot, 2), "R_per_trade": round(tot / n, 4) if n else None,
            "eur_per_100_risked": round(100 * float((st * R).sum() / st.sum()), 2) if n else None,
            "mean_week": round(float(w.mean()), 4), "sd_week": round(float(np.std(w, ddof=1)), 4),
            "losing_weeks_pct": round(float(100 * (w < 0).mean()), 2), "worst_week": round(float(w.min()), 2),
            "longest_losing_weeks": longest_neg_run(w), "max_fall_weekly_R": round(max_fall(w), 2),
            "losing_trades_per_month": round(float((R < 0).sum() / months), 2),
            "mean_stake_scaled": round(float(st.mean()) * scale, 4) if n else None}


def compare(book, ref_book):
    """variant vs reference (same cost mode) at equal weekly swing over the 157 out-of-fold weeks"""
    sd_r = float(np.std(weekly(ref_book, OOF_W), ddof=1))
    sd_v = float(np.std(weekly(book, OOF_W), ddof=1))
    k = sd_r / sd_v
    out = {"scale_k": round(k, 4), "pooled": measures(book, OOF_W, k, 36), "pooled_ref": measures(ref_book, OOF_W, 1.0, 36)}
    out["pooled"]["sharpe_ratio_vs_ref"] = round(out["pooled"]["sharpe"] / out["pooled_ref"]["sharpe"], 4)
    out["by_year"] = {}
    up = 0
    for y, wk in YEAR_W.items():
        a = measures(book, wk, k, 12)
        r = measures(ref_book, wk, 1.0, 12)
        a["sharpe_ratio_vs_ref"] = round(a["sharpe"] / r["sharpe"], 4)
        up += int(a["sharpe"] > r["sharpe"])
        out["by_year"][str(y)] = {"variant": a, "ref": r}
    out["years_up"] = up
    return out


# ------------------------------------------------------------------------------------------- io
def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


def dump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=_js)


def append_trial(row):
    with open(TRIALS, "a") as f:
        f.write(json.dumps(row, default=_js) + "\n")


TRADE_COLS = ["oid", "side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "pnl", "risk", "R"]


def save_trades(t, name):
    t[[c for c in TRADE_COLS if c in t.columns]].reset_index(drop=True).to_parquet(os.path.join(OUT, f"{name}.parquet"))


def load_trades(name):
    t = pd.read_parquet(os.path.join(OUT, f"{name}.parquet"))
    assert (t.entry_time < IS_END).all() and (t.exit_time < IS_END).all()
    return t
