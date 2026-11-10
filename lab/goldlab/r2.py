"""Round-2 toolkit (PROTOCOL_V2): FP Markets cost frames, evaluation, criteria.

    import goldlab as gl
    from goldlab import r2

    m1 = r2.load("us100")                      # FP-cost M1 frame (bid/ask = FP Raw-account model), research data only
    orders = make_orders(m1, **params)          # your strategy; indices into m1
    ev = r2.evaluate("us100", make_orders, params)   # IS metrics under FP costs, FP stress, gross
    r2.log_trial("idx_us", "us100", params, ev)      # log EVERY configuration you evaluate
    crit = r2.is_criteria(ev)

    # finalists only (single shot, logged):
    val = r2.validate("us100", make_orders, params, track="idx_us", label="name")

`make_orders(m1, **params)` must build its orders from the frame it is given (so that the cost-stress
re-run sees consistent quotes) and must be causal.
"""
import json
import os
from dataclasses import replace

import numpy as np
import pandas as pd

from . import data as _data
from .metrics import report
from .sim import Costs, apply_spread_mult, simulate
from .split import RESULTS, cut

_HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = {k: v for k, v in json.load(open(os.path.join(_HERE, "..", "r2", "fp_costs.json"))).items() if not k.startswith("_")}
SYMS = list(SPEC)
CRYPTO = ("btcusd", "ethusd")
_fp_cache = {}


def load(sym, start=None, end=None):
    """FP-cost M1 frame for `sym` (xauusd, xagusd, us100, us500, us30, ger40, btcusd, ethusd).
    Research data only (< 2026-01-01). ~330 MB per symbol: load one symbol at a time and call
    `r2.free()` when you switch."""
    if sym not in _fp_cache:
        _fp_cache[sym] = pd.read_parquet(os.path.join(_data.DATA, "fp", f"{sym}_m1.parquet"))
    df = _fp_cache[sym]
    idx = df.index
    lo = 0 if start is None else int(idx.searchsorted(_data._utc(start), side="left"))
    cap = _data._utc(_data.HOLDOUT_START)
    if end is not None and _data._utc(end) < cap:
        cap = _data._utc(end)
    return df.iloc[lo:int(idx.searchsorted(cap, side="left"))]


def free(sym=None):
    """Drop cached frames (all, or one symbol) to release memory."""
    if sym is None:
        _fp_cache.clear()
    else:
        _fp_cache.pop(sym, None)


def costs(sym, stress=1.0):
    """FP Markets costs for the simulator (the spread, and the Raw commission where there is one, are
    already inside the FP frame)."""
    s = SPEC[sym]
    return Costs(commission=0.0, slip_bps=s["slip_stop_bps"] * stress, slip_mkt_bps=s["slip_mkt_bps"] * stress,
                 swap_long=s["swap_long"], swap_short=s["swap_short"], spread_mult=1.0,
                 swap_triple=s.get("swap_triple", "Wed"))


GROSS = Costs(commission=0.0, slip_bps=0.0, slip_mkt_bps=0.0, swap_long=0.0, swap_short=0.0, spread_mult=1.0)


def run(sym, make_orders, params, mode="fp", no_overlap=True, m1=None):
    """Simulate one configuration. mode: 'fp' (base costs) | 'stress' (spread and slippage x1.5,
    orders rebuilt on the widened quotes) | 'gross' (mid prices, no cost at all)."""
    m1 = load(sym) if m1 is None else m1
    if mode == "fp":
        return simulate(m1, make_orders(m1, **params), sym=sym, costs=costs(sym), no_overlap=no_overlap)
    if mode == "stress":
        mk = apply_spread_mult(m1, 1.5)
        return simulate(mk, make_orders(mk, **params), sym=sym, costs=costs(sym, 1.5), no_overlap=no_overlap)
    if mode == "gross":
        mk = apply_spread_mult(m1, 0.0)
        return simulate(mk, make_orders(mk, **params), sym=sym, costs=GROSS, no_overlap=no_overlap)
    raise ValueError(mode)


def _bps(t):
    """Mean net result per trade in basis points of the entry price."""
    return round(float((t["pnl"] / t["entry"]).mean() * 1e4), 2) if len(t) else 0.0


def evaluate(sym, make_orders, params, full=True, no_overlap=True):
    """IS evaluation of one configuration under FP costs; with full=True also the x1.5 cost stress,
    the gross (zero-cost) run and the every-signal diagnostic. Returns a dict of reports (IS only)."""
    m1 = load(sym)
    t = run(sym, make_orders, params, "fp", no_overlap, m1)
    ti = cut(t, "is")
    out = {"sym": sym, "is": report(ti), "is_bps_per_trade": _bps(ti)}
    if full:
        ts = cut(run(sym, make_orders, params, "stress", no_overlap, m1), "is")
        tg = cut(run(sym, make_orders, params, "gross", no_overlap, m1), "is")
        out["is_stress"] = report(ts)
        out["is_gross"] = report(tg)
        out["is_gross_bps_per_trade"] = _bps(tg)
        if no_overlap:
            te = cut(run(sym, make_orders, params, "fp", False, m1), "is")
            out["is_every_signal"] = report(te)
    return out


def is_criteria(ev, neighbor_median_pf=None):
    """PROTOCOL_V2 section 4, in-sample criteria for one sleeve."""
    r = ev["is"]
    if r.get("n", 0) == 0:
        return {"pass": False}
    yp, yn = (int(x) for x in r["years_pos"].split("/"))
    c = {"n>=250": r["n"] >= 250, "pf>=1.12": r["pf"] >= 1.12, "t>=2.5": r["t_stat"] >= 2.5,
         "years_pos>=60%": yp >= 0.6 * yn, "max_hold<=5d": r["max_hold_h"] <= 5 * 24 + 72}
    if "is_stress" in ev:
        c["stress_pf>=1.04"] = ev["is_stress"].get("pf", 0) >= 1.04
    if "is_every_signal" in ev:
        c["every_signal_exp>0"] = ev["is_every_signal"].get("expectancy_R", -1) > 0
    if neighbor_median_pf is not None:
        c["neighbors_median_pf>=1.06"] = neighbor_median_pf >= 1.06
    c["pass"] = all(c.values())
    return c


def validate(sym, make_orders, params, track, label, no_overlap=True):
    """Single-shot validation (2022-2025) of a finalist chosen on IS. Logged. Returns reports + criteria."""
    m1 = load(sym)
    t = run(sym, make_orders, params, "fp", no_overlap, m1)
    tv = cut(t, "val", track=track, label=label)
    out = {"val": report(tv), "val_bps_per_trade": _bps(tv)}
    ts = cut(run(sym, make_orders, params, "stress", no_overlap, m1), "val", track=track, label=label + ":stress")
    out["val_stress"] = report(ts)
    if no_overlap:
        te = cut(run(sym, make_orders, params, "fp", False, m1), "val", track=track, label=label + ":every")
        out["val_every_signal"] = report(te)
    r = out["val"]
    c = {"pf>=1.06": r.get("pf", 0) >= 1.06, "expectancy>0": r.get("expectancy_R", -1) > 0}
    if "val_every_signal" in out:
        c["every_signal_exp>0"] = out["val_every_signal"].get("expectancy_R", -1) > 0
    c["pass"] = all(c.values())
    out["val_criteria"] = c
    return out


def log_trial(track, sym, params, ev):
    """Append one evaluated configuration to results/r2/<track>/trials.jsonl (every config, no exception)."""
    d = os.path.join(RESULTS, "r2", track)
    os.makedirs(d, exist_ok=True)
    keep = lambda r: {k: v for k, v in r.items() if k not in ("by_year_R", "exit_reasons")}
    row = {"sym": sym, "params": params, "is": keep(ev["is"]), "is_bps_per_trade": ev.get("is_bps_per_trade")}
    for k in ("is_stress", "is_gross", "is_every_signal"):
        if k in ev:
            row[k] = {q: ev[k].get(q) for q in ("n", "pf", "expectancy_R", "t_stat")}
    with open(os.path.join(d, "trials.jsonl"), "a") as f:
        f.write(json.dumps(row, default=str) + "\n")


# ----------------------------------------------------------------------------------------------
# Random-entry null (PROTOCOL_V2 section 4): does the rule beat chance with the SAME trade structure?
# ----------------------------------------------------------------------------------------------
_null_cache = {}


def _minute_groups(m1, period_end="2022-01-01", period_start=None):
    """Bars grouped by New-York minute of day, restricted to [period_start, period_end)."""
    key = (id(m1), len(m1), period_start, period_end)
    if key not in _null_cache:
        _null_cache.clear()
        idx = m1.index
        lo = 0 if period_start is None else int(idx.searchsorted(_data._utc(period_start)))
        hi = int(idx.searchsorted(_data._utc(period_end)))
        ny = idx[lo:hi].tz_convert(_data.NY)
        mod = (ny.hour * 60 + ny.minute).to_numpy()
        order = np.argsort(mod, kind="stable")
        bounds = np.searchsorted(mod[order], np.arange(1441))
        _null_cache[key] = (lo, hi, mod, order, bounds)
    return _null_cache[key]


def null_test(sym, make_orders, params, n_seeds=200, mode="day", period="is", no_overlap=True, seed=0):
    """Compare the rule with random entries that keep its structure.

    The filled trades of the rule (FP costs) are re-entered AT MARKET at random moments:
      mode="day"  : same New-York time of day, random day of the period   (use for signal-based rules)
      mode="time" : random day AND random time                              (use for calendar / time-of-day rules)
    keeping for each trade its side, its stop / target / trailing / break-even distances (scaled with the
    price level) and its time-exit delay. Returns the percentile of the rule's mean R among `n_seeds`
    random replays, plus the null's mean and 95th percentile. Criterion: percentile >= 97.5 on IS.
    period: 'is' (free) only; validation-period nulls are for the lead."""
    if period != "is":
        raise ValueError("null_test is for the in-sample period")
    m1 = load(sym)
    orders = make_orders(m1, **params).reset_index(drop=True)
    c = costs(sym)
    t = simulate(m1, orders, sym=sym, costs=c, no_overlap=no_overlap)
    t = cut(t, "is")
    if len(t) < 30:
        return {"n": int(len(t))}
    o = orders.loc[t.index]
    idx = m1.index
    fill_i = idx.searchsorted(t.entry_time.to_numpy())
    entry = t.entry.to_numpy(float)
    side = t.side.to_numpy()
    rel = lambda v: np.asarray(v, float) / entry
    stop_rel = rel(t.risk.to_numpy(float))
    tgt_rel = np.full(len(t), np.nan)
    if "target" in o and o["target"].notna().any():
        tgt_rel = np.where(o["target"].notna(), (o["target"].to_numpy(float) - entry) * side / entry, tgt_rel)
    if "target_dist" in o and o["target_dist"].notna().any():
        tgt_rel = np.where(o["target_dist"].notna(), o["target_dist"].to_numpy(float) / entry, tgt_rel)
    tgt_rel = np.where(tgt_rel > 0, tgt_rel, np.nan)
    trail_rel = rel(o["trail"].to_numpy(float)) if "trail" in o else np.full(len(t), np.nan)
    be_rel = rel(o["be"].to_numpy(float)) if "be" in o else np.full(len(t), np.nan)
    xi = o["exit_i"].to_numpy(np.int64) if "exit_i" in o else np.full(len(t), -1, np.int64)
    dur = np.where(xi >= 0, np.maximum(xi - fill_i, 1), -1)
    lo, hi, mod, order, bounds = _minute_groups(m1)
    mod_c = mod[np.clip(fill_i - lo, 0, hi - lo - 1)]
    mid = ((m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2)
    rng = np.random.default_rng(seed)
    means = []
    n_bars = len(m1)
    for _ in range(n_seeds):
        if mode == "day":
            a, b = bounds[mod_c], bounds[mod_c + 1]
            ok = b > a
            pos = (a + (rng.random(len(t)) * np.maximum(b - a, 1)).astype(np.int64))
            ei = lo + order[np.minimum(pos, len(order) - 1)]
        else:
            ok = np.ones(len(t), bool)
            ei = lo + rng.integers(0, hi - lo - 2, len(t))
        px = mid[ei]
        no = pd.DataFrame({"entry_i": ei, "side": side, "stop_dist": stop_rel * px, "target_dist": tgt_rel * px,
                           "trail": trail_rel * px, "be": be_rel * px,
                           "exit_i": np.where(dur >= 0, np.minimum(ei + dur, n_bars - 1), -1)})[ok]
        tn = simulate(m1, no, sym=sym, costs=c, no_overlap=no_overlap)
        tn = cut(tn, "is")
        means.append(float(tn.R.mean()) if len(tn) else 0.0)
    means = np.array(means)
    cand = float(t.R.mean())
    return {"n": int(len(t)), "mode": mode, "rule_mean_R": round(cand, 4), "null_mean_R": round(float(means.mean()), 4),
            "null_p95_R": round(float(np.percentile(means, 95)), 4), "null_max_R": round(float(means.max()), 4),
            "percentile": round(float((means < cand).mean() * 100), 1), "pass": bool((means < cand).mean() >= 0.975)}
