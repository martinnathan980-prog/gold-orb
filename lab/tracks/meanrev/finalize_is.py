"""IS documentation of the finalist (uses the saved IS trades of trial #028; no new config)."""
import json
import os
import numpy as np
import pandas as pd
from run import SCRATCH, m1_is, gl, side_stats
from analysis import cost_decomp, worst, worst_weeks

OUT = "/home/user/gold-orb/lab/results/meanrev"
t = pd.read_pickle(os.path.join(SCRATCH, "t_028.pkl"))
m1 = m1_is()
rep = gl.report(t)
rl, rs_ = gl.report(t[t.side > 0]), gl.report(t[t.side < 0])
d = cost_decomp(t, m1).mean().round(4).to_dict()
w10 = worst(t, 10)
ww = worst_weeks(t, 5)
by_side_year = t.groupby([t.entry_time.dt.year, "side"]).R.sum().unstack().round(1)
print(json.dumps({k: v for k, v in rep.items()}, default=str))
print("LONG :", json.dumps({k: rl[k] for k in ("n", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "pf", "t_stat", "years_pos", "total_R")}))
print("SHORT:", json.dumps({k: rs_[k] for k in ("n", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "pf", "t_stat", "years_pos", "total_R")}))
print("costs (mean R/trade):", d)
print("by year x side R:\n", by_side_year.to_string())
print("worst 10 trades:\n", w10.to_string())
print("worst 5 weeks (R):", ww.round(2).to_dict())
json.dump({"is": rep, "is_long": rl, "is_short": rs_, "cost_R": d,
           "worst10": w10.astype(str).to_dict("records"), "worst_weeks": {str(k): round(v, 2) for k, v in ww.items()},
           "by_year_side": {str(k): v for k, v in by_side_year.to_dict("index").items()}},
          open(os.path.join(OUT, "finalist_A_is.json"), "w"), indent=1, default=str)
