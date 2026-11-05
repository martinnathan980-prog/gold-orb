"""Neighbour robustness of the best-effort finalist (one parameter at a time: +-20% or the
adjacent grid value).  Declared before running."""
import json
import numpy as np
from run import ev, n_trials

BASE = dict(family="soup", tf="D", n=5, min_age=1, mode="close_inside", stop_buf=1.0, max_bars=3)
NEIGH = [("n", 4), ("n", 6), ("min_age", 2), ("stop_buf", 0.8), ("stop_buf", 1.2), ("max_bars", 2), ("max_bars", 4)]

if __name__ == "__main__":
    print("trials before:", n_trials())
    rows = []
    for k, v in NEIGH:
        cfg = dict(BASE, **{k: v})
        _, rep, rs = ev(cfg, stage="R", note=f"neighbour of finalist A: {k}={v}")
        rows.append({"param": k, "value": v, "n": rep["n"], "pf": rep["pf"], "exp": rep["expectancy_R"],
                     "t": rep["t_stat"], "years_pos": rep["years_pos"], "stress_pf": rs["pf"]})
    pfs = [r["pf"] for r in rows]
    print("neighbour PFs:", pfs, "median:", float(np.median(pfs)))
    json.dump(rows, open("/home/user/gold-orb/lab/results/meanrev/neighbours_A.json", "w"), indent=1)
    print("trials after:", n_trials())
