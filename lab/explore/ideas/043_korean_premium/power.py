"""Idea 043, power first: count the signals of each threshold from the signal data alone (no traded price, no return).
    EXPLORE_CACHE=~/explore_data/idea_043 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/043_korean_premium/power.py"""
import json, os, sys
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_043"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import premium as P

d = P.load_inputs()
k = P.premium(d)
out = {"weekday_T": int(len(k)), "k_finite": int(np.isfinite(k).sum()),
       

       "k_quantiles": {str(q): float(k.quantile(q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)}}
for thr in (0.02, 0.03, 0.04, 0.05):
    s = k[k >= thr]
    out[f"n_thr{thr}"] = int(len(s))
    out[f"by_year_thr{thr}"] = {str(y): int(v) for y, v in s.groupby(s.index.year).size().items()}
    # runs of consecutive signal weekdays (Fri -> Mon counts as consecutive)
    out[f"by_month_thr{thr}"] = {str(p): int(v) for p, v in s.groupby(s.index.strftime("%Y-%m")).size().items()}
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "power.json"), "w"), indent=1)
