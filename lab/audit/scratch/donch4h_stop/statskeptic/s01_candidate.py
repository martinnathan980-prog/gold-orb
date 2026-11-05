"""Reproduce the candidate on patched data; save trade lists (normal, costs x1.5, every-signal)
for IS and VAL.  ONE logged VAL access (all variants concatenated, cut once)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

OUT = HERE
m1 = gl.load_m1("xauusd")
orders = S.make_orders(m1, **PARAMS)
orders.to_parquet(os.path.join(OUT, "cand_orders.parquet"))
t = gl.simulate(m1, orders, no_overlap=True)
ts = gl.simulate(m1, orders, costs=stressed_costs("xauusd"), no_overlap=True)
te = gl.simulate(m1, orders, no_overlap=False)
t["variant"], ts["variant"], te["variant"] = "normal", "stress", "every"
t["oid"], ts["oid"], te["oid"] = t.index, ts.index, te.index
allt = pd.concat([t, ts, te], ignore_index=True)
ti = gl.cut(allt, "is")
tv = gl.cut(allt, "val", track="review", label=label("candidate-trades(normal,stress,every-signal)"))
ti.to_parquet(os.path.join(OUT, "cand_trades_is.parquet"))
tv.to_parquet(os.path.join(OUT, "cand_trades_val.parquet"))
res = {}
for per, d in (("is", ti), ("val", tv)):
    for v in ("normal", "stress", "every"):
        x = d[d.variant == v]
        r = gl.report(x)
        res[f"{per}_{v}"] = {k: r[k] for k in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "long_n",
                                              "long_R", "short_n", "short_R", "trades_per_year", "max_hold_h",
                                              "by_year_R")}
ri, rsi = gl.report(ti[ti.variant == "normal"]), gl.report(ti[ti.variant == "stress"])
rv = gl.report(tv[tv.variant == "normal"])
res["is_criteria"] = is_criteria(ri, rsi)
res["val_criteria"] = val_criteria(rv)
# taken vs skipped (patched data)
for per, d in (("is", ti), ("val", tv)):
    nor, ev = d[d.variant == "normal"], d[d.variant == "every"]
    taken = set(nor.oid)
    sk = ev[~ev.oid.isin(taken)]
    tk = ev[ev.oid.isin(taken)]
    # check identity of R for taken subset
    same = np.allclose(np.sort(tk.R.to_numpy()), np.sort(nor.R.to_numpy())) if len(tk) == len(nor) else False
    res[f"{per}_taken_vs_skipped"] = {"taken": summarize(tk), "skipped": summarize(sk), "subset_identical": bool(same)}
json.dump(res, open(os.path.join(OUT, "s01_candidate.json"), "w"), indent=1, default=str)
for k, v in res.items():
    print(k, json.dumps(v, default=str))
