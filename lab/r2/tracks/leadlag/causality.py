"""Truncation test: orders built on data cut at random times must equal the orders built on the full data
(for all orders whose entry AND planned exit are before the cut). Leaders are cut at the same time."""
import sys
import numpy as np, pandas as pd
from common import *


def truncation_test(sym, params, n_cuts=4, seed=1, verbose=True):
    use(sym)
    m1 = r2.load(sym)
    strategy.clear_leaders()
    full = strategy.make_orders(m1, **params)
    leaders = {s: strategy._LEADERS[s] for s in list(strategy._LEADERS)}
    rng = np.random.default_rng(seed)
    idx = m1.index
    lo = int(len(m1) * 0.25)
    hi = int(idx.searchsorted(pd.Timestamp("2022-01-01", tz="UTC")))
    ok_all = True
    for c in sorted(rng.integers(lo, hi, n_cuts)):
        T = idx[c]
        tcut = int(T.value // 60_000_000_000) if T.unit == "ns" else int(T.as_unit("ns").value // 60_000_000_000)
        strategy.clear_leaders()
        for s, (tm, cl, op) in leaders.items():
            k = tm < tcut
            strategy._LEADERS[s] = (tm[k], cl[k], op[k] if op is not None else None)
        part = strategy.make_orders(m1.iloc[:c], **params)
        a = full[(full.entry_i < c - 5) & (full.exit_i < c - 5)].reset_index(drop=True)
        b = part[(part.entry_i < c - 5) & (part.exit_i < c - 5)].reset_index(drop=True)
        same = len(a) == len(b) and bool((a.entry_i.values == b.entry_i.values).all()) and bool((a.side.values == b.side.values).all()) \
            and bool((a.exit_i.values == b.exit_i.values).all()) and bool(np.allclose(a.stop_dist.values, b.stop_dist.values, rtol=1e-9, atol=0))
        ok_all &= same
        if verbose:
            print(f"  cut at {T}: full-data orders before cut {len(a)}, truncated-data orders {len(b)} -> {'IDENTICAL' if same else 'DIFFERENT'}", flush=True)
    strategy.clear_leaders()
    return ok_all, len(full)


if __name__ == "__main__":
    tests = [
        ("btcusd", {"rule": "xlead", "leader": "us100", "pred": "lead", "k": 5, "z": 5, "sess": "uscash", "hold": 30, "stop": 2.0, "dirn": 1}),
        ("ger40", {"rule": "xlead", "leader": "us500", "pred": "resid", "k": 5, "z": 3, "sess": "eu_am", "hold": 30, "stop": 2.0, "dirn": 1}),
        ("us100", {"rule": "relstr", "peers": ["us500", "us30"], "T": 600, "ref": "open", "disp": 1.0, "xmin": 959, "stop": 3.0}),
        ("us30", {"rule": "relstr", "peers": ["us100", "us500"], "T": 600, "ref": "prevclose", "disp": 0.0, "xmin": 959, "stop": 3.0}),
    ]
    for sym, p in tests:
        ok, n = truncation_test(sym, p)
        o = strategy.make_orders(r2.load(sym), **p)
        m1 = r2.load(sym)
        yrs = pd.Series(1, index=m1.index[o.entry_i.to_numpy()].year).groupby(level=0).sum().to_dict()
        print(sym, p, "-> orders", n, "| causal:", ok, "| longs", int((o.side > 0).sum()), "shorts", int((o.side < 0).sum()), "| orders by year", yrs, flush=True)
        strategy.clear_leaders()
