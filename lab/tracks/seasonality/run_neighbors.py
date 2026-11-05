"""Neighbour robustness (IS) for the two pre-chosen finalists: +-30 min entry, adjacent exit, stop k +-20 %,
limit window +-20 %, adjacent limit offset.  All logged."""
import json, os
import numpy as np
from trials import evaluate, RES

BASE = {
    "FRI_PM_LIM": dict(entry_time="13:30", exit_time="16:45", exit_days=0, stop_atr=3.0, entry="limit", limit_off=0.0, limit_min=60),
    "WKND_LIM": dict(entry_time="13:30", exit_time="22:00", exit_days=2, stop_atr=3.0, entry="limit", limit_off=0.0, limit_min=60),
}
VAR = {
    "FRI_PM_LIM": [("entry 13:00", dict(entry_time="13:00")), ("entry 14:00", dict(entry_time="14:00")),
                   ("exit 16:30", dict(exit_time="16:30")), ("exit 16:55", dict(exit_time="16:55")),
                   ("k 2.4", dict(stop_atr=2.4)), ("k 3.6", dict(stop_atr=3.6)),
                   ("lim 48m", dict(limit_min=48)), ("lim 72m", dict(limit_min=72)), ("off 0.1", dict(limit_off=0.1))],
    "WKND_LIM": [("entry 13:00", dict(entry_time="13:00")), ("entry 14:00", dict(entry_time="14:00")),
                 ("exit Sun 21:00", dict(exit_time="21:00")), ("exit Sun 23:00", dict(exit_time="23:00")),
                 ("k 2.4", dict(stop_atr=2.4)), ("k 3.6", dict(stop_atr=3.6)),
                 ("lim 48m", dict(limit_min=48)), ("lim 72m", dict(limit_min=72)), ("off 0.1", dict(limit_off=0.1))],
}
out = {}
for fin, base in BASE.items():
    pfs = []
    rows = []
    for lab, ch in VAR[fin]:
        p = {**base, **ch}
        t, rep, rep_s, crit = evaluate(f"NB {fin} {lab}", p)
        pfs.append(rep["pf"])
        rows.append({"neighbor": lab, "params": p, "n": rep["n"], "pf": rep["pf"], "t": rep["t_stat"],
                     "exp": rep["expectancy_R"], "years_pos": rep["years_pos"], "stress_pf": rep_s["pf"]})
    out[fin] = {"median_neighbor_pf": float(np.median(pfs)), "neighbors": rows}
    print(f"### {fin}: median neighbour PF = {np.median(pfs):.3f}  (min {min(pfs):.3f}, max {max(pfs):.3f})\n")
with open(os.path.join(RES, "neighbors.json"), "w") as f:
    json.dump(out, f, indent=1, default=str)
