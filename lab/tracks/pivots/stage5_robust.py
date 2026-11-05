"""Stage 5: robustness of the IS candidate (decided BEFORE any VAL access).
Neighbours: every tuned parameter +-20% or the adjacent grid step / hour; placebo of the exact rule;
engine diagnostic with overlapping positions allowed (no_overlap=False)."""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import run, run_placebo, OUT, m1, fmt, ntrials
import strategy as S
import goldlab as gl
from goldlab.evalkit import is_criteria

A = dict(family="round", levels=("RB", "RA"), grid=100.0, mode="tbreak", stop_atr=0.4, tgt=1.0, fresh=True)
NEIGH = {
    "stop_atr=0.32": dict(A, stop_atr=0.32), "stop_atr=0.48": dict(A, stop_atr=0.48),
    "tgt=0.8R": dict(A, tgt=0.8), "tgt=1.2R": dict(A, tgt=1.2),
    "win_start=07:00LDN": dict(A, win=("LDN", 420, "NY", 720)), "win_start=09:00LDN": dict(A, win=("LDN", 540, "NY", 720)),
    "win_end=11:00NY": dict(A, win=("LDN", 480, "NY", 660)), "win_end=13:00NY": dict(A, win=("LDN", 480, "NY", 780)),
    "eod=15:00NY": dict(A, eod=900), "eod=16:30NY": dict(A, eod=990),
}
if __name__ == "__main__":
    res = {"params": A, "neighbors": {}}
    for nm, prm in NEIGH.items():
        t, rep, rs, crit = run("A_neighbor_" + nm, prm)
        res["neighbors"][nm] = {"pf": rep["pf"], "t": rep["t_stat"], "n": rep["n"], "exp": rep["expectancy_R"],
                                "stress_pf": rs.get("pf"), "years_pos": rep["years_pos"]}
    pfs = [v["pf"] for v in res["neighbors"].values()]
    res["neighbor_median_pf"] = float(np.median(pfs))
    print("neighbor PFs:", [round(x, 3) for x in pfs], "median", round(float(np.median(pfs)), 3))
    res["placebo"] = run_placebo("A_rn100_fresh", A)
    # engine diagnostic: every signal traded (overlapping positions allowed)
    d = m1()
    o = S.make_orders(d, **A)
    t2 = gl.cut(gl.simulate(d, o, no_overlap=False), "is")
    r2 = gl.report(t2)
    gl.log_trial("pivots", {"name": "A_diag_no_overlap_False", **A, "no_overlap": False}, r2)
    print(f"[{ntrials():3d}] A diag no_overlap=False  {fmt(r2)}")
    res["diag_no_overlap_false"] = {k: v for k, v in r2.items() if k not in ("exit_reasons",)}
    with open(os.path.join(OUT, "stage5_robust.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
