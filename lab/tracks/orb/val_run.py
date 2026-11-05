"""The ONE validation access of track orb (2022-2025) for the pre-chosen finalist.
Normal and x1.5-cost simulations are cut in a single logged call.  No re-tuning afterwards."""
import json
import os

import numpy as np
import pandas as pd

import research as R
import strategy as S
import goldlab as gl
from goldlab.evalkit import stressed_costs, val_criteria

FINAL = "orb_asia_2d_buf10"

if __name__ == "__main__":
    path = os.path.join(R.RES, "candidates.json")
    cand = json.load(open(path))
    if "VAL" in cand["finalists"][FINAL]:
        raise SystemExit("VAL already evaluated for this finalist -- refusing a second access")
    m1 = R.m1()
    o = S.make_orders(m1, **S.FINALISTS[FINAL])
    t = gl.simulate(m1, o)
    ts = gl.simulate(m1, o, costs=stressed_costs("xauusd"))
    both = pd.concat([t.assign(cost="normal"), ts.assign(cost="x1.5")])
    v = gl.cut(both, "val", track="orb", label=FINAL)          # single logged access
    tv, tvs = v[v.cost == "normal"], v[v.cost == "x1.5"]
    rv, rvs = gl.report(tv), gl.report(tvs)
    crit = val_criteria(rv)
    gl.show(rv, f"VAL {FINAL}")
    print("VAL stress PF:", rvs.get("pf"), "| criteria:", crit)
    print("VAL sides:", R.side_stats(tv))
    yr = tv.entry_time.dt.year
    print(tv.assign(yr=yr).pivot_table(index="yr", columns="side", values="R", aggfunc=["sum", "count"]).round(1))
    keep = {k: v for k, v in rv.items()}
    cand["finalists"][FINAL]["VAL"] = {**keep, "stress_pf": rvs.get("pf"), "sides": R.side_stats(tv),
                                       "by_year_side_R": {int(k): {int(s): round(float(x), 1) for s, x in g.items()}
                                                          for k, g in tv.groupby([yr, tv.side]).R.sum().unstack().iterrows()}}
    cand["finalists"][FINAL]["val_criteria"] = {"VAL_" + k: bool(x) for k, x in crit.items()}
    cand["finalists"][FINAL]["criteria"].update(cand["finalists"][FINAL]["val_criteria"])
    json.dump(cand, open(path, "w"), indent=1, default=str)
