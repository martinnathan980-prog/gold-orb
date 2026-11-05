"""ONE-SHOT validation of the pre-chosen finalist(s) of track `trend` on VAL (2022-2025).

Refuses to run if results/trend/val_results.json already exists (no second look).
Steps: full M1 history -> orders -> simulate (normal + costs x1.5) -> check the IS part
reproduces the research log exactly -> gl.cut(..., "val", track="trend", label=name) (logged)
-> report + val_criteria.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, LAB)
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

import goldlab as gl  # noqa: E402
from goldlab.evalkit import stressed_costs, val_criteria  # noqa: E402

import research as RS  # noqa: E402
import strategy as S  # noqa: E402

OUT = os.path.join(LAB, "results", "trend", "val_results.json")


def side_stats(t):
    out = {}
    for name, m in (("long", t.side > 0), ("short", t.side < 0)):
        R = t.loc[m, "R"].to_numpy()
        out[name] = {"n": int(len(R)), "sum_R": round(float(R.sum()), 1),
                     "exp_R": round(float(R.mean()), 4) if len(R) else None,
                     "pf": RS._pf(R) if len(R) else None,
                     "win_rate": round(float((R > 0).mean()), 3) if len(R) else None}
    return out


def main():
    if os.path.exists(OUT) and "--force" not in sys.argv:
        raise SystemExit(f"{OUT} exists: validation was already run once. Not running again.")
    m1 = gl.load_m1("xauusd")
    detail = {json.dumps(r["config"], sort_keys=True): r for r in
              (json.loads(x) for x in open(RS.DETAIL))}
    results = {}
    for name, params in S.FINALISTS.items():
        orders = S.make_orders(m1, **params)
        t = gl.simulate(m1, orders)
        ts = gl.simulate(m1, orders, costs=stressed_costs("xauusd"))
        # 1) the IS part must reproduce the research log exactly
        ris = gl.report(gl.cut(t, "is"))
        logged = detail[json.dumps(S.resolve(params), sort_keys=True)]["is"]
        for k in ("n", "pf", "t_stat", "total_R"):
            assert ris[k] == logged[k], (name, k, ris[k], logged[k])
        # 2) the one VAL look (logged by gl.cut)
        tv = gl.cut(t, "val", track="trend", label=name)
        tvs = gl.cut(ts, "val", track="trend", label=name + "-costx1.5")
        rv, rvs = gl.report(tv), gl.report(tvs)
        R = tv["R"].to_numpy()
        k = max(1, int(round(0.05 * len(R))))
        top = np.sort(R)[::-1][:k].sum()
        results[name] = {
            "params": S.resolve(params),
            "val": {kk: vv for kk, vv in rv.items()},
            "val_stress_pf": rvs.get("pf"), "val_stress_exp": rvs.get("expectancy_R"),
            "val_sides": side_stats(tv),
            "val_top5pct_R": round(float(top), 1),
            "val_top5pct_share": round(float(top / R.sum()), 2) if R.sum() > 0 else None,
            "val_criteria": val_criteria(rv),
            "is_check": {kk: ris[kk] for kk in ("n", "pf", "t_stat", "total_R")},
        }
        gl.show(rv, f"VAL {name}")
        print("   stress pf", rvs.get("pf"), "| sides", results[name]["val_sides"],
              "| top5% share", results[name]["val_top5pct_share"], "| criteria", results[name]["val_criteria"])
    with open(OUT, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("saved", OUT)


if __name__ == "__main__":
    main()
