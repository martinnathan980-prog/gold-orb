import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np
from pivbb.tracks.run.harness import trial, OUT
O2 = ["D_R2", "D_S2"]; O4 = ["D_R2", "D_S2", "D_R3", "D_S3"]
A = dict(levels=O2, entry="touch")
Bc = dict(levels=O4, hours=[2, 12], target=None)
res = {}
for name, base in (("A", A), ("B", Bc)):
    rows = []
    for sd in range(10):
        ev, row = trial(f"placebo {name} seed {sd}", dict(base, placebo=sd), kind="placebo")
        rows.append({k: row[k] for k in ("n", "pf", "t", "exp_R", "gross_pf", "gross_exp_R", "long_R", "short_R")})
    res[name] = rows
json.dump(res, open(OUT + "/placebo_raw.json", "w"), indent=1)
for k, v in res.items():
    pf = np.array([r["pf"] for r in v]); ex = np.array([r["exp_R"] for r in v])
    print(k, "placebo PF median", np.median(pf), "min", pf.min(), "max", pf.max(), "| exp median", np.median(ex), "max", ex.max())
