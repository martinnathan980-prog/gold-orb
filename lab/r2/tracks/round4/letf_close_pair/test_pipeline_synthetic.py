"""Smoke test of the whole pipeline (calendar -> grid -> signals -> two-leg simulation -> report -> null) on SYNTHETIC
random-walk M1 frames (no market data), so that run.py cannot crash half-way through the single real run."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import run as RUN  # noqa: E402


def fake_frame(seed, base, start="2013-09-16", end="2014-12-31"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, end, freq="1min", tz="UTC")
    ny = idx.tz_convert(C.NY)
    mod = ny.hour * 60 + ny.minute
    keep = (ny.dayofweek < 5) & (mod >= 900) & (mod < 975)          # 15:00 .. 16:14 New York only
    idx = idx[keep]
    keep2 = rng.random(len(idx)) > 0.01                              # 1 % of bars missing
    idx = idx[keep2]
    m = base * np.exp(np.cumsum(rng.normal(0, 0.0004, len(idx))))
    sp = base * 0.37e-4
    return pd.DataFrame({"bo": m - sp / 2, "bc": m - sp / 2, "ao": m + sp / 2, "ac": m + sp / 2}, index=idx)


def main():
    fr = {"us100": fake_frame(1, 15000), "us30": fake_frame(2, 34000), "us500": fake_frame(3, 4500)}
    cal = C.calendar(last="2014-12-31")
    P = C.prepare(C.build_grid(fr, cal["tdays"]))
    for name, over in (("main", {}), ("exit_1605", {"exit_min": 965}), ("entry_1540", {"entry_min": 940}),
                       ("us500", {"leg2": "us500"}), ("stop_1.25", {"k": 1.25})):
        p = dict(sig_min=930, entry_min=930, exit_min=959, hed_e=930, hed_x=959, thr=1.25, k=1.5, leg2="us30",
                 win=60, minv=40, cost_mult=1.0)
        p.update(over)
        sg = C.signals(P, cal, **p)
        t, counts = C.run_config(P, sg, p)
        tg, _ = C.run_config(P, sg, p, mode="mid")
        rep = C.summarize(t, tg)
        assert len(t) > 10, (name, counts)
        assert (t.hold_min <= (p["exit_min"] - p["entry_min"])).all()
        assert set(t.reason) <= {"stop", "time"}
        print(name, counts, {k: rep.get(k) for k in ("n", "pf", "t_stat", "expectancy_R", "stop_share",
                                                     "cost_bp_per_pair", "gross_bp_per_pair")})
        if name == "main":
            nul = RUN.null_test(P, cal, t, n_seeds=20, seed=0)
            print("null (20 seeds):", {k: v for k, v in nul.items() if k != "means"})
    print("synthetic pipeline smoke test passed")


if __name__ == "__main__":
    main()
