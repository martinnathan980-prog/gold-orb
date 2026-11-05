"""Summarise every logged trial (results/meanrev/trials.jsonl) + gross/cost decomposition."""
import json
import os
import pandas as pd
from run import TRIALS, SCRATCH, m1_is
from analysis import cost_decomp

rows = [json.loads(l) for l in open(TRIALS)]
m1 = m1_is()
out = []
for k, r in enumerate(rows, 1):
    c, m = r["config"], r["is"]
    p = os.path.join(SCRATCH, f"t_{k:03d}.pkl")
    g = cost_decomp(pd.read_pickle(p), m1).mean() if os.path.exists(p) else None
    out.append({"id": k, "stage": c.get("_stage"), "note": c.get("_note"), "n": m.get("n"),
                "tpy": m.get("trades_per_year"), "win": m.get("win_rate"), "pf": m.get("pf"),
                "exp": m.get("expectancy_R"), "t": m.get("t_stat"), "yrs": m.get("years_pos"),
                "stress_pf": m.get("stress_pf"), "long_pf": m.get("long_pf"), "short_pf": m.get("short_pf"),
                "gross": round(float(g.gross_R), 3) if g is not None else None,
                "cost": round(float(g.gross_R - g.R), 3) if g is not None else None})
df = pd.DataFrame(out)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
print(df.to_string(index=False))
df.to_csv("/home/user/gold-orb/lab/results/meanrev/trials_summary.csv", index=False)
