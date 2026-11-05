"""ONE validation run per finalist (2022-2025), frozen params from strategy.FINALISTS.
gl.cut(..., 'val') is called exactly once per finalist (access is logged)."""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import goldlab as gl  # noqa: E402
from goldlab.evalkit import val_criteria  # noqa: E402
from strategy import FINALISTS, make_orders  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "results", "meanrev")

if __name__ == "__main__":
    name = sys.argv[1]
    params = FINALISTS[name]
    m1 = gl.load_m1("xauusd")                       # full history (warm-up + VAL)
    t = gl.simulate(m1, make_orders(m1, **params), sym="xauusd", no_overlap=True)
    is_chk = gl.report(gl.cut(t, "is"))             # must reproduce the IS trial
    tv = gl.cut(t, "val", track="meanrev", label=name)   # <-- the single logged VAL access
    rv = gl.report(tv)
    crit = val_criteria(rv)
    rl, rsh = gl.report(tv[tv.side > 0]), gl.report(tv[tv.side < 0])
    wk = gl.weekly_R(tv)
    out = {"name": name, "params": params, "val": rv, "val_criteria": crit,
           "val_long": rl, "val_short": rsh,
           "val_worst10": tv.nsmallest(10, "R")[["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "R"]].astype(str).to_dict("records"),
           "val_worst_weeks": {str(k): round(float(v), 2) for k, v in wk.nsmallest(5).items()},
           "is_recheck": {k: is_chk[k] for k in ("n", "pf", "expectancy_R", "t_stat")}}
    json.dump(out, open(os.path.join(OUT, f"val_{name}.json"), "w"), indent=1, default=str)
    print("IS recheck:", out["is_recheck"])
    print("VAL:", json.dumps({k: v for k, v in rv.items()}, default=str))
    print("VAL criteria:", crit)
    for nm, r in (("LONG", rl), ("SHORT", rsh)):
        print(nm, json.dumps({k: r.get(k) for k in ("n", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "pf", "t_stat", "years_pos", "total_R")}))
    print("worst 5 weeks:", out["val_worst_weeks"])
    print(tv.nsmallest(10, "R")[["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "R"]].to_string())
