"""Addendum H, lens `breadth` -- shared tools (IN SAMPLE ONLY).

The frozen rules of the ten validated sleeves, with their parameters UNCHANGED, run on instruments they were never
tried on.  Every price frame is cut at 2021-12-31 23:59 UTC while it is read (pyarrow filter on the bar start `ts`:
no 2022+ row is ever materialised); every official trades file is read with `entry_time < 2022-01-01` in the same
statement.  Each rule is called on the in-sample slice that is passed to it explicitly (never r2.run / recalc on a
full frame).  The rules come from the lab registry (lab/r2/recalc.py::sleeves()), untouched.

Costs: FP Markets model (lab/r2/fp_costs.json via goldlab.r2.costs); stress = spread and slippage x1.5 with the
orders rebuilt on the widened quotes (same as goldlab.r2.run mode "stress").  Two instruments have no FP figure in
the lab and get a declared model, injected in memory only (r2.SPEC, nothing written):
  jp225   Dukascopy JPN.IDX/JPY mid prices (lab/data/raw_jp, 2013-2021 CSVs), FP-style frame built here with the
          build_fp_frames logic: 12 index points at 50,000 = 2.4 bp all-in spread (other brokers publish 5.5-10
          points; Dukascopy quotes 6-7), Dukascopy intraday spread shape; slippage 0.5 bp stop / 0.2 bp market per
          side (the lab's index values); swap long 5.5 %/yr, short 0, triple Friday.
  shares  the stocks track's provisional model (lab/r2/tracks/stocks/transfer.py STOCK_SPEC): Dukascopy share CFD
          quotes plus 0.02 USD per share per side folded in the frame (data/fp/<ticker>_m1.parquet, split-adjusted),
          slippage 2 bp stop / 1 bp market, swap 7 % / 3 %.
Broker rule (task rule 4): a stop closer than 3 spreads is refused -> such trades are not taken (the order is removed
and the sleeve re-simulated until no taken trade violates it; the spread is the frame's own at the fill bar).
"""
import glob
import importlib.util
import json
import os
import sys
import time

SCR = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/breadth"
os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(SCR, "numba"))
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
RES = os.path.join(LAB, "results", "r2", "autopsy", "breadth")
sys.path.insert(0, LAB)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.metrics import report  # noqa: E402
from goldlab.sim import GAP, apply_spread_mult, simulate  # noqa: E402,F401

IS_END = pd.Timestamp("2022-01-01", tz="UTC")           # nothing at or after this instant is ever read
COMMON_START = pd.Timestamp("2018-02-01", tz="UTC")     # common in-sample window of the ten sleeves
YEARS = (2018, 2019, 2020, 2021)
NY = "America/New_York"

SLEEVES = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
RULES = ["noise30", "ocm4", "donch4h_stop", "orb_asia_2d_buf10", "GOLD_FRI_PM", "brk72_24h_wd",
         "F1_brk_ridge_filter", "nq_btc_follow"]

FX = ["eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "usdchf", "nzdusd", "eurjpy"]
STOCKS = ["aapl", "msft", "amzn", "googl", "fb", "nvda", "tsla", "nflx", "amd", "intc", "csco", "orcl", "crm", "adbe",
          "qcom", "avgo", "mu", "pypl", "baba", "jpm", "bac", "c", "wfc", "gs", "v", "ma", "jnj", "pfe", "mrk", "unh",
          "xom", "cvx", "ba", "cat", "ge", "wmt", "hd", "dis", "mcd", "nke"]

JP225_SPEC = {"spread": 12.0, "spread_ref_price": 50000.0, "slip_stop_bps": 0.5, "slip_mkt_bps": 0.2,
              "swap_long": 0.055, "swap_short": 0.0, "swap_triple": "Fri", "units_per_lot": 1, "min_lot": 0.1,
              "lot_step": 0.1, "leverage": 200, "quote": "JPY"}
STOCK_SPEC = {"spread": 0.0, "slip_stop_bps": 2.0, "slip_mkt_bps": 1.0, "swap_long": 0.07, "swap_short": 0.03,
              "swap_triple": "Fri", "units_per_lot": 1, "min_lot": 1, "lot_step": 1, "leverage": 10, "quote": "USD"}


def register_specs():
    """Declared cost rows for the two instruments without an FP row (in memory only)."""
    r2.SPEC.setdefault("jp225", dict(JP225_SPEC))
    for t in STOCKS:
        r2.SPEC.setdefault(t, dict(STOCK_SPEC))


register_specs()


# ------------------------------------------------------------------------------------------------ data
def load_is(sym):
    """In-sample M1 frame of `sym` (bar start < 2022-01-01 00:00 UTC), filtered while reading."""
    if sym == "jp225":
        return build_jp225_is()
    path = os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet")
    df = pd.read_parquet(path, filters=[("ts", "<", IS_END)])
    assert df.index.is_monotonic_increasing and df.index.max() < IS_END
    return df


def build_jp225_is():
    """FP-style cost frame of the Japanese index from the Dukascopy CSVs (2013-2021 only exist on disk).
    Same cleaning as lab/prep_round2.py (inner join of bid and ask, flat filler minutes and weekend trading days
    dropped, crossed quotes dropped) and same cost construction as lab/build_fp_frames.py."""
    out = {}
    for side in ("bid", "ask"):
        fr = []
        for f in sorted(glob.glob(os.path.join(LAB, "data", "raw_jp", f"jpnidxjpy-{side}-*.csv"))):
            d = pd.read_csv(f)
            if not len(d):
                continue
            d["ts"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
            fr.append(d.drop(columns="timestamp").set_index("ts"))
        x = pd.concat(fr)
        out[side] = x[~x.index.duplicated(keep="first")].sort_index()
    df = out["bid"].add_prefix("b_").join(out["ask"].add_prefix("a_"), how="inner")
    df = df[df.index < IS_END]
    flat = (df.b_open == df.b_high) & (df.b_high == df.b_low) & (df.b_low == df.b_close) & (df.b_close == df.b_close.shift(1))
    df = df[~flat]
    ny = df.index.tz_convert(NY)
    df = df[(ny + pd.Timedelta(hours=7)).dayofweek < 5]
    bad = (df.a_close < df.b_close) | (df.a_high < df.b_high) | (df.a_low < df.b_low)
    df = df[~bad]
    raw = pd.DataFrame({"bo": df.b_open, "bh": df.b_high, "bl": df.b_low, "bc": df.b_close,
                        "ao": df.a_open, "ah": df.a_high, "al": df.a_low, "ac": df.a_close}).astype("float64")
    raw.index.name = "ts"
    spr = (raw.ac - raw.bc).clip(lower=0)
    mid_c = (raw.ac + raw.bc) / 2
    td = gl.trading_day(raw.index)
    day_med = spr.groupby(td).transform("median").replace(0, np.nan)
    shape = (spr / day_med).clip(0.7, 6.0).fillna(1.0)
    bps = JP225_SPEC["spread"] / JP225_SPEC["spread_ref_price"] * 1e4
    hs = 0.5 * bps * 1e-4 * mid_c * shape
    fp = pd.DataFrame(index=raw.index)
    for k in "ohlc":
        m = (raw["b" + k] + raw["a" + k]) / 2
        fp["b" + k] = m - hs
        fp["a" + k] = m + hs
    fp = fp[["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]].astype("float64")
    fp.index.name = "ts"
    return fp


def official(name, sym):
    """Official trades of a sleeve, rows with entry_time < 2022-01-01 only (filtered while reading)."""
    path = os.path.join(LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet")
    t = pd.read_parquet(path, filters=[("entry_time", "<", IS_END)])
    assert (t.entry_time < IS_END).all()
    return t.sort_values("entry_time", kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ rules
_REG = None


def registry():
    """{rule name: (track, make_orders, params)} from lab/r2/recalc.py::sleeves() (frozen; the crypto rule comes
    with its FP-hours exit wrapper, exactly as recalculated)."""
    global _REG
    if _REG is None:
        spec = importlib.util.spec_from_file_location("r2_recalc_autopsy_breadth", os.path.join(LAB, "r2", "recalc.py"))
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
    for modname, attr in (("r2_ml_strategy", "_cache"), ("strategy_trend", "_bar_cache"), ("strategy_orb", "_daily_cache"),
                          ("r2_idx_us_strategy", None)):
        mod = sys.modules.get(modname)
        if mod is None:
            continue
        if attr and hasattr(mod, attr):
            getattr(mod, attr).clear()
        if modname == "r2_idx_us_strategy":
            mod.cm._grid_cache.clear()
            mod.cm._atr_cache.clear()


def leader_series(m1_us100):
    """us100 mid closes (in-sample slice), the leader of nq_btc_follow."""
    return ((m1_us100["bc"] + m1_us100["ac"]) / 2).astype("float64")


def build_orders(rule, m1, leader=None):
    """Orders of the frozen rule on the frame given (the frame IS the in-sample slice, fp or stressed)."""
    track, mo, params = registry()[rule]
    clear_rule_caches()
    if rule == "nq_btc_follow":
        if leader is None:
            raise ValueError("nq_btc_follow needs the in-sample us100 leader")
        mod = sys.modules["r2_leadlag_strategy"]
        mod.clear_leaders()
        mod.set_leader("us100", leader)
    o = mo(m1, **params)
    return o.reset_index(drop=True)


def mode_frame(m1, mode):
    if mode == "fp":
        return m1
    if mode == "stress":
        return apply_spread_mult(m1, 1.5)
    if mode == "gross":
        return apply_spread_mult(m1, 0.0)
    raise ValueError(mode)


def mode_costs(sym, mode):
    if mode == "fp":
        return r2.costs(sym)
    if mode == "stress":
        return r2.costs(sym, 1.5)
    if mode == "gross":
        return r2.GROSS
    raise ValueError(mode)


def simulate_filtered(mk, orders, sym, costs, min_spreads=3.0, no_overlap=True, max_iter=20):
    """simulate() with the broker's minimum stop distance: a trade whose initial stop is closer than `min_spreads`
    times the spread of its fill bar is not taken; its order is removed and the sleeve re-simulated (a refused order
    leaves the sleeve flat, so later signals may be taken) until no taken trade violates the rule."""
    o = orders.reset_index(drop=True).copy()
    o["oid"] = np.arange(len(o), dtype=np.int64)
    spr_all = (mk["ao"].to_numpy() - mk["bo"].to_numpy())
    idx = mk.index
    refused = []
    t = None
    for _ in range(max_iter):
        t = simulate(mk, o, sym=sym, costs=costs, no_overlap=no_overlap)
        if not len(t) or min_spreads is None:
            break
        fi = idx.searchsorted(t.entry_time)
        bad = (t["risk"].to_numpy() < min_spreads * spr_all[fi]) & (t["reason"].to_numpy() != "gap")
        bad |= t["reason"].to_numpy() == "gap"            # a stop already crossed at the fill: refused as well
        if not bad.any():
            break
        ids = t["oid"].to_numpy()[bad]
        refused.extend(int(i) for i in ids)
        o = o[~o["oid"].isin(ids)]
    t = t.copy()
    t.attrs["refused_3spreads"] = len(refused)
    t.attrs["refused_oids"] = refused
    return t


def run_rule(rule, sym, m1, mode="fp", leader=None, min_spreads=3.0, no_overlap=True):
    """One frozen rule on one in-sample slice in one cost mode.  Returns (trades, orders, info)."""
    mk = mode_frame(m1, mode)
    t0 = time.time()
    o = build_orders(rule, mk, leader=leader)
    if len(o) == 0:
        return pd.DataFrame(), o, {"orders": 0, "refused_3spreads": 0, "sec": round(time.time() - t0, 1)}
    t = simulate_filtered(mk, o, sym, mode_costs(sym, mode), min_spreads=min_spreads, no_overlap=no_overlap)
    info = {"orders": int(len(o)), "refused_3spreads": int(t.attrs.get("refused_3spreads", 0)),
            "sec": round(time.time() - t0, 1)}
    return t, o, info


# ------------------------------------------------------------------------------------------------ metrics
def window(t, start=COMMON_START, end=IS_END):
    if not len(t):
        return t
    return t[(t.entry_time >= start) & (t.entry_time < end)]


def summ(t, label=""):
    """Compact report of a trades frame (R-based, as goldlab.metrics.report) + year-by-year R."""
    if t is None or not len(t):
        return {"n": 0}
    r = report(t)
    keep = ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "t_stat", "pf", "total_R",
            "max_dd_R", "years_pos", "long_n", "long_R", "short_n", "short_R", "avg_hold_h", "max_hold_h", "by_year_R",
            "exit_reasons")
    out = {k: r[k] for k in keep if k in r}
    out["bps_per_trade"] = round(float((t["pnl"] / t["entry"]).mean() * 1e4), 2)
    yr = t.groupby(t.entry_time.dt.year)["R"].sum()
    out["years_2018_2021_pos"] = int(sum(1 for y in YEARS if yr.get(y, 0.0) > 0))
    out["years_2018_2021_present"] = int(sum(1 for y in YEARS if y in yr.index))
    return out


def weekly(t, start=COMMON_START, end=IS_END):
    """Sum of R per calendar week of the exit (Monday-Sunday, UTC), every week of the window (empty weeks = 0)."""
    weeks = pd.period_range(start.tz_convert(None), (end - pd.Timedelta(seconds=1)).tz_convert(None), freq="W")
    if t is None or not len(t):
        return pd.Series(0.0, index=weeks)
    w = t.groupby(t.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    return w.reindex(weeks, fill_value=0.0)


def breadth_pass(fp_s, st_s):
    """Addendum H breadth criteria (fixed in the protocol before any run), on the common window 2018-02..2021, FP
    costs: PF >= 1.15, positive in at least 3 of the 4 years 2018-2021, positive with costs x1.5; parameters
    unchanged (by construction)."""
    c = {"pf>=1.15": bool(fp_s.get("n", 0) > 0 and fp_s.get("pf", 0) >= 1.15),
         "years_pos>=3of4": bool(fp_s.get("years_2018_2021_pos", 0) >= 3),
         "stress_positive": bool(st_s.get("n", 0) > 0 and st_s.get("total_R", -1) > 0),
         "params_unchanged": True}
    c["pass"] = all(c.values())
    return c


def v2_criteria(fp_s, st_s):
    """PROTOCOL_V2 section 4 sleeve bars, for information only (not the breadth criterion)."""
    if not fp_s.get("n"):
        return {"pass": False}
    yp, yn = (int(x) for x in fp_s["years_pos"].split("/"))
    c = {"n>=250": fp_s["n"] >= 250, "pf>=1.12": fp_s["pf"] >= 1.12, "t>=2.5": fp_s["t_stat"] >= 2.5,
         "years>=60%": yp >= 0.6 * yn, "stress_pf>=1.04": st_s.get("pf", 0) >= 1.04}
    c["pass"] = all(c.values())
    return c


def jdump(obj, path):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=_js)


def _js(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (pd.Timestamp,)):
        return str(x)
    return str(x)


def append_trial(row):
    with open(os.path.join(RES, "trials.jsonl"), "a") as f:
        f.write(json.dumps(row, default=_js) + "\n")
