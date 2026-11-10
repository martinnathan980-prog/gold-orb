"""Truncation test: orders built on data cut at random times must equal the orders built on the longer
frame up to those times (entry time, side, level, stop, and the exit time when it lies before the cut).

Usage: python3 causality_test.py            (in-sample frame only; no performance is computed)
"""
import json
import os
import sys

sys.path.insert(0, "/home/user/gold-orb/lab")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from goldlab import r2  # noqa: E402

import strategy as S  # noqa: E402

OUT = "/home/user/gold-orb/lab/results/r2/idx_eu"


def _norm(m1, o):
    idx = m1.index
    d = pd.DataFrame({"entry_time": idx[o["entry_i"].to_numpy()], "side": o["side"].to_numpy(),
                      "exit_time": idx[o["exit_i"].to_numpy()]})
    for c in ("level", "stop", "stop_dist", "target", "trail"):
        if c in o:
            d[c] = o[c].to_numpy()
    return d


def check(m1, params, cuts):
    full = _norm(m1, S.make_orders(m1, **params))
    res = []
    for tau in cuts:
        sub = m1[m1.index < tau]
        # an order whose entry bar is the very last bar of the cut frame has no later bar for its time
        # exit and is dropped by make_orders (end-of-frame effect, not look-ahead): compare strictly before it
        last = sub.index[-1]
        a = _norm(sub, S.make_orders(sub, **params))
        a = a[a.entry_time < last].reset_index(drop=True)
        b = full[full.entry_time < last].reset_index(drop=True)
        same_n = len(a) == len(b)
        ok = same_n
        if same_n and len(a):
            cols = [c for c in a.columns if c != "exit_time"]
            for c in cols:
                x, y = a[c].to_numpy(), b[c].to_numpy()
                if c == "entry_time":
                    ok &= bool((x == y).all())
                else:
                    ok &= bool(np.allclose(x.astype(float), y.astype(float), rtol=0, atol=1e-9, equal_nan=True))
            # exits: comparable only when the scheduled exit lies before the cut
            m = (b.exit_time < tau - pd.Timedelta(minutes=45)).to_numpy()
            ok &= bool((a.exit_time.to_numpy()[m] == b.exit_time.to_numpy()[m]).all())
        res.append({"cut": str(tau), "orders_before_cut": int(len(b)), "orders_truncated": int(len(a)), "identical": bool(ok)})
    return res


def main(param_sets=None, n_cuts=6, seed=7):
    m1 = r2.load("ger40", end="2022-01-01")
    rng = np.random.default_rng(seed)
    lo, hi = int(len(m1) * 0.15), len(m1) - 1
    cuts = [m1.index[int(i)] + pd.Timedelta(seconds=0) for i in sorted(rng.integers(lo, hi, n_cuts))]
    # add cuts placed in the middle of an active day (10:17 and 16:43 Berlin)
    for d, hm in (("2019-06-12", "10:17"), ("2016-03-09", "16:43"), ("2021-02-25", "17:29")):
        cuts.append(pd.Timestamp(f"{d} {hm}", tz="Europe/Berlin").tz_convert("UTC"))
    if param_sets is None:
        param_sets = {
            "mom_default": {"family": "mom"},
            "mom_grid": {"family": "mom", "times": tuple(f"{h:02d}:{m:02d}" for h in range(9, 17) for m in (0, 30) if (h, m) >= (9, 30))},
            "orb_default": {"family": "orb"},
            "orb_us": {"family": "orb", "rs": "09:30@NY", "re": "10:00@NY", "entry_end": "21:00", "exit": "21:45"},
        }
    out = {}
    for name, p in param_sets.items():
        r = check(m1, p, cuts)
        out[name] = {"params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in p.items()}, "cuts": r,
                     "all_identical": all(x["identical"] for x in r)}
        print(name, "all identical:", out[name]["all_identical"], [(x["orders_before_cut"], x["identical"]) for x in r], flush=True)
    return out


if __name__ == "__main__":
    out = main()
    json.dump(out, open(os.path.join(OUT, "causality_test.json"), "w"), indent=1)
