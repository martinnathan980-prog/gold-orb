"""Truncation test: orders built on the frame cut at random minutes must equal the orders built on the
full frame, for every order whose decision (entry bar, and trigger bar for brackets) lies before the cut.
Fields known at the decision are compared for all of them; the exit index is compared for the orders
whose scheduled exit bar lies before the cut.

Usage: python3 causality_test.py [sym ...]   (in-sample frame only)"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
for p in (LAB, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
from goldlab import r2  # noqa: E402
import strategy as S  # noqa: E402

CONFIGS = {
    "long_pre_hold": dict(rule="long", lead=5, exit="hold", hold=15, stop_atr=1.0),
    "long_pre_close": dict(rule="long", lead=5, exit="hhmm", exit_hhmm="15:55", stop_atr=1.0),
    "mom_fomc_close": dict(rule="mom", kinds="fomc", k=5, exit="hhmm", exit_hhmm="15:55", stop_atr=0.5),
    "mom_nextday": dict(rule="mom", k=30, exit="hhmm", exit_hhmm="15:55", exit_days=1, stop_atr=1.0, min_move=0.1),
    "fade": dict(rule="fade", kinds="nfp", k=5, exit="hold", hold=60, stop_atr=0.5),
    "brk": dict(rule="brk", k=2, pre_win=30, valid=30, buf_atr=0.05, exit="hold", hold=120, stop_atr=0.5),
}


def check(m1, params, n_cuts=8, seed=7):
    full = S.make_orders(m1, **params)
    rng = np.random.default_rng(seed)
    # half of the cuts are placed right inside event windows (the dangerous places), half anywhere
    ev_i = full.entry_i.to_numpy()
    cuts = list(rng.integers(len(m1) // 4, len(m1) - 1, n_cuts // 2))
    for e in rng.choice(ev_i[len(ev_i) // 4:], n_cuts - n_cuts // 2, replace=False):
        cuts.append(int(e + rng.integers(1, 40)))
    bad = 0
    compared = 0
    for c in cuts:
        S._cache.clear()
        part = S.make_orders(m1.iloc[:c], **params)
        trig = full.expiry_i.where(full.etype > 0, full.entry_i)
        f = full[(full.entry_i < c - 1) & (trig < c - 1)].reset_index(drop=True)
        trig_p = part.expiry_i.where(part.etype > 0, part.entry_i)
        q = part[(part.entry_i < c - 1) & (trig_p < c - 1)].reset_index(drop=True)
        cols = ["entry_i", "side", "etype", "level", "expiry_i", "stop_dist"]
        same = len(f) == len(q) and all(np.array_equal(f[k].to_numpy(), q[k].to_numpy(), equal_nan=True) for k in cols)
        if same:
            m = (f.exit_i < c - 1).to_numpy()
            same = np.array_equal(f.exit_i.to_numpy()[m], q.exit_i.to_numpy()[m])
        compared += len(f)
        if not same:
            bad += 1
            print(f"   MISMATCH at cut {c} ({m1.index[c]}): full {len(f)} orders vs truncated {len(q)}")
    S._cache.clear()
    return {"cuts": len(cuts), "orders_compared": int(compared), "mismatching_cuts": bad}


if __name__ == "__main__":
    out = {}
    for sym in (sys.argv[1:] or ["us500"]):
        r2.free()
        m1 = r2.load(sym, end="2022-01-01")
        for name, params in CONFIGS.items():
            res = check(m1, params)
            out[f"{sym}:{name}"] = res
            print(sym, name, res, flush=True)
    r2.free()
    path = os.path.join(LAB, "results", "r2", "events", "causality_test.json")
    prev = json.load(open(path)) if os.path.exists(path) else {}
    prev.update(out)
    json.dump(prev, open(path, "w"), indent=1)
