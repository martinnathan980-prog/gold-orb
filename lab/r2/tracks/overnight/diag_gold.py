"""In-sample diagnostics of the frozen gold finalist (run after validation; nothing re-tuned):
(1) market entry instead of the limit entry (logged trial); (2) the historical Dukascopy spread instead of the FP
spread, FP slippage/swap (information only, PROTOCOL_V2 section 3 guard-rail c).   Usage: python3 diag_gold.py [market]
"""
import json
import os
import sys

import pandas as pd

from common import RES, S, gl, r2, trial
from goldlab.metrics import report
from goldlab.split import cut

p = S.finalist_params("GOLD_FRI_PM", "xauusd")
if "market" in sys.argv:        # logs one trial
    q = dict(p); q["entry_type"] = "market"; q.pop("limit_min")
    trial("xauusd", q, "DIAG gold Fri 13:30->16:45 MARKET entry (IS only; finalist frozen)", full=True,
          extra={"diagnostic_of": "GOLD_FRI_PM", "post_validation": True})
raw = gl.load_m1("xauusd")      # research data only (the 2026 holdout is excluded by default)
ti = cut(gl.simulate(raw, S.make_orders(raw, **p), sym="xauusd", costs=r2.costs("xauusd"), no_overlap=True), "is")
r = report(ti)
out = {"model": "historical Dukascopy spread + FP slippage/swap, no commission (information only, IS)",
       "is": {k: r[k] for k in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "win_rate", "by_year_R")},
       "is_bps_per_trade": round(float((ti.pnl / ti.entry).mean() * 1e4), 2)}
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(RES, "gold_fri_pm_historical_cost_is.json"), "w"), indent=1)
r2.free()
