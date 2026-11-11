"""Baseline in-sample diagnostics per sleeve (no variant simulated): columns, R0 estimate vs engine risk,
MFE in R, hold time, exit reasons. Output: results/r2/shape/baseline_diag.csv"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import strategy as S
import goldlab as gl
from goldlab import r2

OUT = os.path.join(S.LAB, "results", "r2", "shape")
rows = []
last = None
for key, (sym, mo, params) in S.sleeves().items():
    if sym != last:
        r2.free(); last = sym
    t0 = time.time()
    m1 = r2.load(sym)
    o = mo(m1, **params).reset_index(drop=True)
    t = gl.cut(r2.run(sym, mo, params, "fp", True, m1), "is")
    r0, _ = S.initial_risk(m1, o)
    est = r0[t.index.to_numpy()]
    rel = est / t.risk.to_numpy() - 1
    mfeR = t.mfe / t.risk
    d = dict(sleeve=key, cols=" ".join(c for c in o.columns), n=len(t), first=str(t.entry_time.min().date()),
             win=round((t.R > 0).mean(), 3), exp=round(t.R.mean(), 4), hold_h_med=round(t.hold_min.median() / 60, 2),
             reasons=t.reason.value_counts().to_dict(), r0_err_med=round(float(np.median(np.abs(rel))), 5),
             r0_err_p95=round(float(np.percentile(np.abs(rel), 95)), 5),
             trail=bool("trail" in o and o["trail"].notna().any()), be=bool("be" in o and o["be"].notna().any()),
             tgt=bool(("target" in o and o["target"].notna().any()) or ("target_dist" in o and o["target_dist"].notna().any())))
    for q in (0.5, 1, 1.5, 2, 3):
        d[f"mfe>={q}"] = round(float((mfeR >= q).mean()), 3)
    rows.append(d)
    print(d, f"[{time.time()-t0:.0f}s]", flush=True)
pd.DataFrame(rows).to_csv(os.path.join(OUT, "baseline_diag.csv"), index=False)
