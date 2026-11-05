"""Reproduce the candidate on the CURRENT (patched) data; save its orders and trades for the other
scripts.  VAL trades are obtained with ONE logged gl.cut on a concatenated frame."""
import json
import time

from common import *  # noqa

t0 = time.time()
m1 = gl.load_m1("xauusd")
print("load", round(time.time() - t0, 1), "s", len(m1), flush=True)
t1 = time.time()
o = S.make_orders(m1, **PARAMS)
print("make_orders", round(time.time() - t1, 1), "s", len(o), flush=True)
o.to_parquet(os.path.join(HERE, "cand_orders.parquet"))
t1 = time.time()
t = gl.simulate(m1, o, no_overlap=True)
print("simulate", round(time.time() - t1, 2), "s", flush=True)
ts = gl.simulate(m1, o, costs=STRESS, no_overlap=True)
te = gl.simulate(m1, o, no_overlap=False)
for d, nm in ((t, "normal"), (ts, "stress"), (te, "every")):
    d["cost"] = nm
    d["oid"] = d.index
allt = pd.concat([t, ts, te])
ti = gl.cut(allt, "is")
tv = gl.cut(allt, "val", track="review", label=label("candidate VAL trades normal/stress/every-signal (saved for bootstrap, concentration, holdout model)"))
ti.to_parquet(os.path.join(HERE, "cand_trades_is.parquet"))
tv.to_parquet(os.path.join(HERE, "cand_trades_val.parquet"))
out = {}
for per, d in (("is", ti), ("val", tv)):
    for nm in ("normal", "stress", "every"):
        x = d[d.cost == nm]
        rep = gl.report(x)
        s = summarize(x)
        out[f"{per}_{nm}"] = {**{k: rep[k] for k in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "trades_per_year",
                                                        "max_hold_h", "total_R", "by_year_R")},
                              "pf_unrounded": pf(x.R), "t_unrounded": tstat(x.R),
                              "long_pf": s["long_pf"], "short_pf": s["short_pf"], "long_R": s["long_R"], "short_R": s["short_R"]}
ri, rsi = gl.report(ti[ti.cost == "normal"]), gl.report(ti[ti.cost == "stress"])
out["is_criteria"] = is_criteria(ri, rsi)
rv = gl.report(tv[tv.cost == "normal"])
out["val_criteria"] = val_criteria(rv)
out["val_pf_rounding_note"] = {"report_pf": rv["pf"], "unrounded": pf(tv[tv.cost == "normal"].R)}
out["orders_total"] = int(len(o))
out["orders_is"] = int((pd.to_datetime(o.date) < "2022-01-01").sum())
out["skipped_attr"] = int(t.attrs.get("skipped", 0))
json.dump(out, open(os.path.join(HERE, "s01_candidate.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
print("total secs", round(time.time() - t0, 1))
