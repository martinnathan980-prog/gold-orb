"""Truncation test (hard rule 4): orders built on data cut at random minutes must equal the orders built
on the full data, for every order that was triggered before the cut.  No P&L is computed here.

Comparison: full-frame orders whose trigger bar (first touch / market-entry bar) is <= cut-2 must be
exactly the orders of the truncated frame (entry bar, side, type, level, stop, target, trailing).
Forward-looking clock fields (time exit, expiry of a pending order) must be equal when they fall before
the cut, and point at the last available bar otherwise."""
import json
import os
import sys

import numpy as np
import pandas as pd

from research import RES, r2, S, use

EXACT = ["entry_i", "side", "etype", "level", "stop", "stop_dist", "target", "trail", "trig_i"]


def truncation_test(sym, params, n_cuts=6, seed=7, end=None, lo_frac=0.25):
    use(sym)
    m1 = r2.load(sym, end=end)
    N = len(m1)
    full = S.make_orders(m1, **params).reset_index(drop=True)
    rng = np.random.default_rng(seed)
    cuts = sorted(int(x) for x in rng.integers(int(N * lo_frac), N - 3000, n_cuts))
    out = {"sym": sym, "params": S.resolve(params), "n_orders_full": int(len(full)), "cuts": []}
    ok_all = True
    for nj in cuts:
        oc = S.make_orders(m1.iloc[:nj], **params).reset_index(drop=True)
        of = full[full.trig_i <= nj - 2].reset_index(drop=True)
        oc = oc[oc.trig_i <= nj - 2].reset_index(drop=True)
        r = {"cut_time": str(m1.index[nj]), "n_full_before_cut": int(len(of)), "n_truncated": int(len(oc))}
        same = len(of) == len(oc)
        if same:
            for col in EXACT:
                if col in of or col in oc:
                    x = of[col].to_numpy(float) if col in of else np.full(len(of), np.nan)
                    y = oc[col].to_numpy(float) if col in oc else np.full(len(oc), np.nan)
                    eq = (x == y) | (np.isnan(x) & np.isnan(y))
                    if not eq.all():
                        same = False
                        r["diff_" + col] = int((~eq).sum())
            for col in ("exit_i", "expiry_i"):
                if col in of:
                    x, y = of[col].to_numpy(np.int64), oc[col].to_numpy(np.int64)
                    known = x < nj - 1
                    bad = (known & (x != y)) | (~known & (y < nj - 1))
                    if bad.any():
                        same = False
                        r["diff_" + col] = int(bad.sum())
        r["identical"] = bool(same)
        ok_all &= same
        out["cuts"].append(r)
    out["pass"] = bool(ok_all)
    return out


if __name__ == "__main__":
    import stageA
    cfgs = {k: v[0] for k, v in stageA.A.items()}
    extra = {
        "donch_1h_n120_k2": dict(family="donch", tf=60, n=120, stop_atr=2.0, trail_atr=2.0),
        "donch_1h_n120_k2_sess": dict(family="donch", tf=60, n=120, stop_atr=2.0, trail_atr=2.0, sess_start=420, sess_end=1020),
        "donch_1h_n120_trend480": dict(family="donch", tf=60, n=120, stop_atr=2.0, trail_atr=2.0, trend_n=480),
        "donch_1h_n24_squeeze": dict(family="donch", tf=60, n=24, stop_atr=2.0, trail_atr=2.0, squeeze=0.7, squeeze_ref=480),
        "pullback_1h": dict(family="pullback", tf=60, trend_n=240, pb_n=24),
    }
    cfgs.update(extra)
    res = {}
    for k, p in cfgs.items():
        r = truncation_test("xauusd", p, n_cuts=5, seed=11, end="2022-01-01")
        res[k] = r
        print(k, "PASS" if r["pass"] else "FAIL", [(c["n_full_before_cut"], c["n_truncated"], c["identical"]) for c in r["cuts"]],
              [{q: v for q, v in c.items() if q.startswith("diff_")} for c in r["cuts"] if not c["identical"]], flush=True)
    json.dump(res, open(os.path.join(RES, "causality_stageAB.json"), "w"), indent=1, default=str)
