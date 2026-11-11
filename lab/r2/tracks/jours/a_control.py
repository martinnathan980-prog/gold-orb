"""Zero-edge control of construction (a), from the saved shaped trades (gross, common period 2018-02 .. 2021).

For each variant: every trade's result has its sleeve's mean removed (expectation exactly zero, the SHAPE of the
distribution is kept: many small wins, few large losses), then the results are shuffled among the trades of the same
sleeve (200 draws). What is reported is therefore what the exit shape alone gives when the entries carry no edge.
(The coin-flip-direction control computed in a_shape.py is kept for information but is NOT zero-mean: it keeps the
entry minutes of the rules, and with asymmetric exits a coin flip at those minutes still earns / loses.)

    python3 a_control.py   -> results/r2/jours/a_control.json
"""
import json
import os

import numpy as np
import pandas as pd

import common as C
from a_shape import VARIANTS

N = 200
out = {}
for vname, k, m, eve in VARIANTS:
    t = pd.read_parquet(os.path.join(C.OUT, "a_shape_trades", f"{vname}__gross.parquet"))
    t = t[(t.t_in >= C.COMMON_START) & (t.t_in < C.IS_END)].reset_index(drop=True)
    base = (t.res - t.groupby("sleeve").res.transform("mean")).to_numpy()
    groups = [np.flatnonzero((t.sleeve == s).to_numpy()) for s in t.sleeve.unique()]
    rng = np.random.default_rng(5)
    rows = []
    for b in range(N):
        r = base.copy()
        for g in groups:
            r[g] = base[rng.permutation(g)]
        day = C.daily(t.t_out, r)
        s = C.stats(day)
        s["low"] = float(day.cumsum().min())
        rows.append(s)
    z = pd.DataFrame(rows)
    out[vname] = {"green_days": round(float(z.green_days.mean()), 1), "green_weeks": round(float(z.green_weeks.mean()), 1),
                  "green_months": round(float(z.green_months.mean()), 1), "avg_green": round(float(z.avg_green.mean()), 2),
                  "avg_red": round(float(z.avg_red.mean()), 2), "worst_day_median": round(float(z.worst_day.median()), 2),
                  "worst_week_median": round(float(z.worst_week.median()), 2), "worst_week_p5": round(float(z.worst_week.quantile(0.05)), 2),
                  "max_dd_median": round(float(z.max_dd.median()), 1), "total_p5": round(float(z.total.quantile(0.05)), 1),
                  "p_lose_50_units": round(float((z.low <= -50).mean()), 3), "p_lose_25_units": round(float((z.low <= -25).mean()), 3)}
    print(vname, out[vname], flush=True)
json.dump(out, open(os.path.join(C.OUT, "a_control.json"), "w"), indent=1)
