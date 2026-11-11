"""Pre-declared neighbours of B1 (plan_B_rules.json), quick runs."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import strategy as S
base = dict(family="fix", dec="16:00", look_min=60, exit="16:30", monthend_n=1, stop_atr=1.5)
N = [("exit", "16:20"), ("exit", "16:45"), ("exit", "17:00"), ("look_min", 30), ("look_min", 120),
     ("stop_atr", 1.0), ("stop_atr", 2.5), ("monthend_n", 2)]
out = {}
for k, v in N:
    p = dict(base, **{k: v})
    r = C.basket(f"B1n_{k}_{v}", S.make_orders, p, full=True)
    out[f"{k}={v}"] = r
    print(C.short(r), flush=True)
    print("   pairs", {s: round(x['exp_R'], 3) for s, x in r['fp']['by_sym'].items()}, "tD gross", r['gross']['t_daily'], flush=True)
C.save(out, "stageB1_neighbours.json")
import numpy as np
print("median PF", np.median([r['fp']['pf'] for r in out.values()]))
