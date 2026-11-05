"""POST-VALIDATION DIAGNOSTIC (not a candidate rule, not used for any selection).

Question: is the finalist's profit just 'trend beta' (gold went up)?  Benchmark = random
entries at H4 bar closes with EXACTLY the finalist's exit (stop 2xATR14(H4), trail 2xATR14(H4),
time stop 5 NY trading days, one position at a time), at a similar trade frequency.
20 seeds x {random side, long only, short only}; distribution of PF on IS and on VAL.
VAL access is logged by gl.cut (label 'benchmark-random-entry').  Output: benchmarks.json.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, LAB)
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goldlab as gl  # noqa: E402

import strategy as S  # noqa: E402

OUT = os.path.join(LAB, "results", "trend", "benchmarks.json")


def pf(R):
    g, l = R[R > 0].sum(), -R[R < 0].sum()
    return float(g / l) if l > 0 else float("nan")


def main():
    m1 = gl.load_m1("xauusd")
    b = gl.bars(m1, "4h")
    a = gl.atr(b, 14).to_numpy()
    tc = pd.DatetimeIndex(b["t_close"])
    ok = np.isfinite(a) & (np.arange(len(b)) >= 60)
    ei = gl.entry_index(m1, tc)
    xi = S.exit_index(m1, S.add_trading_days(tc, 5) - pd.Timedelta(minutes=5))
    ok &= (ei < len(m1)) & (xi > ei)
    p_place = 0.10            # ~ the finalist's 55-60 trades / year once overlaps are skipped
    out = {}
    first_val = True
    for mode in ("random", "long", "short"):
        rows = []
        for seed in range(20):
            rng = np.random.default_rng(1000 + seed)
            pick = ok & (rng.random(len(b)) < p_place)
            side = rng.choice([-1, 1], pick.sum()) if mode == "random" else \
                np.full(pick.sum(), 1 if mode == "long" else -1)
            o = pd.DataFrame({"entry_i": ei[pick], "side": side, "stop_dist": 2.0 * a[pick],
                              "trail": 2.0 * a[pick], "exit_i": xi[pick]})
            t = gl.simulate(m1, o)
            ti = gl.cut(t, "is")
            tv = gl.cut(t, "val", track="trend", label="benchmark-random-entry") if first_val else \
                t[(t.entry_time >= pd.Timestamp("2022-01-01", tz="UTC")) & (t.entry_time < pd.Timestamp("2026-01-01", tz="UTC"))]
            first_val = False      # one logged access for the whole benchmark run
            rows.append({"seed": seed, "is_n": len(ti), "is_pf": pf(ti.R.to_numpy()), "is_exp": float(ti.R.mean()),
                         "val_n": len(tv), "val_pf": pf(tv.R.to_numpy()), "val_exp": float(tv.R.mean())})
        df = pd.DataFrame(rows)
        out[mode] = {
            "is_n_median": float(df.is_n.median()), "val_n_median": float(df.val_n.median()),
            "is_pf_median": round(float(df.is_pf.median()), 3), "is_pf_p90": round(float(df.is_pf.quantile(0.9)), 3),
            "is_pf_max": round(float(df.is_pf.max()), 3),
            "val_pf_median": round(float(df.val_pf.median()), 3), "val_pf_p90": round(float(df.val_pf.quantile(0.9)), 3),
            "val_pf_max": round(float(df.val_pf.max()), 3),
            "is_exp_median": round(float(df.is_exp.median()), 4), "val_exp_median": round(float(df.val_exp.median()), 4),
        }
        print(mode, out[mode])
    json.dump({"note": __doc__, "results": out}, open(OUT, "w"), indent=1)
    print("saved", OUT)


if __name__ == "__main__":
    main()
