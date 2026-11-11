"""Round 3, track `shape` (PROTOCOL_V3 sections 2 and 4): reshape the EXITS of the validated sleeves.

Entries, initial stops, time exits and trailing parameters are frozen: `shaped(make_orders, ...)` returns a
make_orders that calls the sleeve's own make_orders and only ADDS exit columns to its orders:

  * target   : a take-profit at k x the initial risk R0 from the fill  (column `target_dist` = k * R0;
               if the sleeve already had a target, the nearer of the two is kept: none of the eleven has one)
  * be       : break-even (stop moved to the fill price) once the trade is `be_r` x R0 ahead (column `be`)

R0 (initial risk) of an order = its `stop_dist`, or |estimated fill - stop| when the stop is an absolute price.
Estimated fill = ask open of the entry bar for a long market order, bid open for a short one, the level for a
stop / limit entry (slippage and gaps are not known in advance: the live EA would use the real fill; the
difference with the engine's `risk` column is measured in run.py and reported).
Causality: every added column is a function of the order's own stop / stop_dist / level / side and of the open
of its entry bar, i.e. of quantities known at the entry minute.

"Half and half" (half the risk on the original exit, half on the target variant) needs no new rule: it is the
average, order by order, of the baseline R and the variant R of the same order.

SELECTED = {sleeve key: variant dict or None} is the frozen in-sample choice (results/r2/shape/selection.json).
"""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(LAB, "r2"))


def initial_risk(m1, o):
    """Estimated initial risk R0 (price units) of each order, from data known at its entry minute."""
    n = len(o)
    side = o["side"].to_numpy(np.int64)
    et = o["etype"].to_numpy(np.int64) if "etype" in o else np.zeros(n, np.int64)
    ei = np.clip(o["entry_i"].to_numpy(np.int64), 0, len(m1) - 1)
    lv = o["level"].to_numpy(float) if "level" in o else np.full(n, np.nan)
    ao, bo = m1["ao"].to_numpy(float), m1["bo"].to_numpy(float)
    fill = np.where(et > 0, lv, np.where(side > 0, ao[ei], bo[ei]))
    st = o["stop"].to_numpy(float) if "stop" in o else np.full(n, np.nan)
    sd = o["stop_dist"].to_numpy(float) if "stop_dist" in o else np.full(n, np.nan)
    return np.where(np.isnan(st), sd, np.abs(fill - st)), fill


def shaped(make_orders, k=None, be_r=None):
    """make_orders of the same sleeve with an added target at k x R0 and/or a break-even at be_r x R0."""
    def wrapped(m1, **params):
        o = make_orders(m1, **params)
        if not len(o) or (k is None and be_r is None):
            return o
        o = o.copy()
        r0, fill = initial_risk(m1, o)
        o["shape_r0"] = r0
        if k is not None:
            td = k * r0
            old_t = o["target"].to_numpy(float) if "target" in o else np.full(len(o), np.nan)
            old_td = o["target_dist"].to_numpy(float) if "target_dist" in o else np.full(len(o), np.nan)
            side = o["side"].to_numpy(np.int64)
            old = np.where(~np.isnan(old_t), side * (old_t - fill), old_td)   # existing target as a distance
            o["target"] = np.nan
            o["target_dist"] = np.where(np.isnan(old), td, np.minimum(old, td))
        if be_r is not None:
            b = be_r * r0
            old_be = o["be"].to_numpy(float) if "be" in o else np.full(len(o), np.nan)
            o["be"] = np.where(np.isnan(old_be), b, np.minimum(old_be, b))
        return o
    return wrapped


def _mod(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(LAB, path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


KEEP10 = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
          ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
          ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]


def sleeves():
    """{"name:sym": (sym, make_orders, params)} for the eleven validated sleeves, ordered by symbol."""
    import recalc
    out = {}
    for track, name, sym, mo, params in recalc.sleeves():
        if (name, sym) in KEEP10:
            out[f"{name}:{sym}"] = (sym, mo, params)
    from pivbb.tracks.run import strategy as piv
    out["outer_close_ride:xauusd"] = ("xauusd", piv.make_orders, piv.FINALISTS["outer_close_ride"])
    assert len(out) == 11, list(out)
    order = {"us100": 0, "btcusd": 1, "ethusd": 2, "xauusd": 3}
    return dict(sorted(out.items(), key=lambda kv: order[kv[1][0]]))


# Frozen in-sample selection (PROTOCOL_V3 section 4), filled from results/r2/shape/selection.json.
# A variant: {"k": target multiple or None, "be": break-even multiple or None, "half": True = half the risk on the
# original exit, half on the variant}.  None = the sleeve keeps its original exit.
SELECTED = {
    "noise30:us100": {"k": 2.0, "be": None, "half": True},
    "ocm4:us100": {"k": 2.0, "be": None, "half": True},
    "brk72_24h_wd:btcusd": None,
    "nq_btc_follow:btcusd": {"k": 1.0, "be": None, "half": False},
    "F1_brk_ridge_filter:btcusd": None,
    "brk72_24h_wd:ethusd": {"k": 2.0, "be": None, "half": False},
    "F1_brk_ridge_filter:ethusd": {"k": 2.0, "be": None, "half": True},
    "GOLD_FRI_PM:xauusd": {"k": 0.5, "be": None, "half": True},
    "donch4h_stop:xauusd": {"k": 2.0, "be": None, "half": False},
    "orb_asia_2d_buf10:xauusd": None,
    "outer_close_ride:xauusd": None,
}
