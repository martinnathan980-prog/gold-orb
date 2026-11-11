"""Does the candidate add anything beyond its exposure to the two existing gold rules? (in-sample daily regression)
and: how far are R2 / S2 from yesterday's close (to size the no-pivot control)."""
import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd
import runpy
ns = runpy.run_path("/home/user/gold-orb/lab/pivbb/tracks/run/novelty.py")
DM = ns["DM"]; S = ns["S"]; m1 = ns["m1"]
out = {}
for c in ("r2s2_touch_run", "outer_close_ride"):
    X = np.column_stack([np.ones(len(DM)), DM["donch4h_stop"], DM["orb_asia_2d_buf10"]])
    y = DM[c].to_numpy()
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b
    cov = np.linalg.inv(X.T @ X) * (e @ e) / (len(y) - 3)
    out[c] = {"alpha_R_per_day": round(float(b[0]), 5), "alpha_t": round(float(b[0] / np.sqrt(cov[0, 0])), 2), "beta_donch": round(float(b[1]), 3),
              "beta_orb": round(float(b[2]), 3), "raw_mean_R_per_day": round(float(y.mean()), 5), "raw_t": round(float(y.mean() / y.std(ddof=1) * np.sqrt(len(y))), 2),
              "alpha_R_per_year": round(float(b[0] * 259), 1), "raw_R_per_year": round(float(y.mean() * 259), 1)}
c = S.context(m1); D = c["D"]; T = S.level_table(c)
D = D[(D.index >= "2013-01-01")]
ix = c["D"].index.get_indexer(D.index)
d2 = np.r_[(T["D_R2"][ix] - D.pc) / D.atr, (D.pc - T["D_S2"][ix]) / D.atr]
d1 = np.r_[(T["D_R1"][ix] - D.pc) / D.atr, (D.pc - T["D_S1"][ix]) / D.atr]
d3 = np.r_[(T["D_R3"][ix] - D.pc) / D.atr, (D.pc - T["D_S3"][ix]) / D.atr]
q = lambda x: [round(float(v), 2) for v in np.nanquantile(x, [0.1, 0.25, 0.5, 0.75, 0.9])]
out["distance_from_yesterdays_close_in_dATR_q10_25_50_75_90"] = {"R1/S1": q(d1), "R2/S2": q(d2), "R3/S3": q(d3)}
print(json.dumps(out, indent=1))
json.dump(out, open("/home/user/gold-orb/lab/results/pivbb/run/novelty_regression.json", "w"), indent=1)
