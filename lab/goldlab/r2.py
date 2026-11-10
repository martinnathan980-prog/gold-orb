"""Round-2 toolkit (PROTOCOL_V2): FP Markets cost frames, evaluation, criteria.

    import goldlab as gl
    from goldlab import r2

    m1 = r2.load("us100")                      # FP-cost M1 frame (bid/ask = FP Standard model), research data only
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
    """FP Markets Standard costs for the simulator (spread is already inside the FP frame)."""
    s = SPEC[sym]
    return Costs(commission=0.0, slip_bps=s["slip_stop_bps"] * stress, slip_mkt_bps=s["slip_mkt_bps"] * stress,
                 swap_long=s["swap_long"], swap_short=s["swap_short"], spread_mult=1.0)


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
