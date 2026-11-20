"""Supplement to the scan's discovery summary (DIRECTION4 section 6: 'share of rules with t > 2 by family, gross
against net'): the t of each rule-unit's daily GROSS sums (before costs), beside the net t of unit_stats.csv.
Reads only the discovery tables (bars before 2019). Written by the lead after the run; it changes no selection."""
import json, os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, "lab/explore")
from scan import discover as DS, grammar as G
from scan import select as SL

sdir = os.path.expanduser("~/explore_data/scan")
T = SL.Tables(os.path.join(sdir, "discovery"))
nR, nD = len(T.rules), len(SL.DAY_AXIS)
Dg = {}
for m in T.markets:
    a = DS.load_market(T.ddir, m)
    r = np.array([T.pos[int(x)] for x in a["d_rule"]], np.int64)
    dpos = np.searchsorted(SL.DAY_AXIS, a["d_day"])
    X = np.zeros((nR, nD)); X[r, dpos] = a["d_Rg"]; Dg[m] = X
rows = []
for unit in SL.UNIT_ORDER:
    ms = T.unit_markets(unit)
    if not ms:
        continue
    D = sum(Dg[m] for m in ms); N = sum(T.N[m] for m in ms)
    tg = SL._t_rows(D, N)
    rows.append(pd.DataFrame({"rule": [r["id"] for r in T.rules], "unit": unit, "t_gross": tg}))
g = pd.concat(rows, ignore_index=True)
st = pd.read_csv(os.path.join(sdir, "unit_stats.csv")).merge(g, on=["rule", "unit"], how="left", validate="1:1")
k = st[st.n >= 30]
def sh(x):
    return {"rule_units": int(len(x)), "net_t_gt_2": round(float((x.t > 2).mean()), 4), "net_t_lt_-2": round(float((x.t < -2).mean()), 4),
            "gross_t_gt_2": round(float((x.t_gross > 2).mean()), 4), "gross_t_lt_-2": round(float((x.t_gross < -2).mean()), 4),
            "median_gross_t": round(float(x.t_gross.median()), 3), "median_net_t": round(float(x.t.median()), 3)}
out = {"what": "shares of rule-units (n >= 30 trades) with t beyond +-2, on gross and on net daily results; discovery, bars before 2019",
       "noise_reference": "with no edge at all and independent days, about 0.023 on each side",
       "all": sh(k), "by_family": {}, "by_frame": {}, "by_unit_kind": {}, "by_family_frame": {}}
for fam, x in k.groupby("family"): out["by_family"][fam] = sh(x)
for fr, x in k.groupby("frame"): out["by_frame"][fr] = sh(x)
for b, x in k.groupby("basket"): out["by_unit_kind"]["baskets" if b else "single markets"] = sh(x)
for (fam, fr), x in k.groupby(["family", "frame"]): out["by_family_frame"][f"{fam}|{fr}"] = sh(x)
out["by_unit"] = {u: sh(x) for u, x in k.groupby("unit")}
json.dump(out, open(os.path.join(sdir, "gross_t.json"), "w"), indent=1, sort_keys=True)
print("ALL", out["all"])
for sec in ("by_unit_kind", "by_frame", "by_family"):
    for a, v in out[sec].items(): print(f"{sec:13} {a:15} n {v['rule_units']:>6}  gross >2 {v['gross_t_gt_2']:.3f} <-2 {v['gross_t_lt_-2']:.3f} med {v['median_gross_t']:+.2f} | net >2 {v['net_t_gt_2']:.3f} <-2 {v['net_t_lt_-2']:.3f} med {v['median_net_t']:+.2f}")
print("--- family|frame, gross")
for a, v in out["by_family_frame"].items(): print(f"  {a:16} n {v['rule_units']:>5}  gross >2 {v['gross_t_gt_2']:.3f} <-2 {v['gross_t_lt_-2']:.3f} med {v['median_gross_t']:+.2f}")
print("--- unit, gross")
for a, v in out["by_unit"].items(): print(f"  {a:8} n {v['rule_units']:>5}  gross >2 {v['gross_t_gt_2']:.3f} <-2 {v['gross_t_lt_-2']:.3f} med {v['median_gross_t']:+.2f} | net >2 {v['net_t_gt_2']:.3f} <-2 {v['net_t_lt_-2']:.3f}")
# the eligible table in short
el = st[st.eligible]
print("--- eligible", len(el), "by unit:", el.unit.value_counts().to_dict())
print("eligible by family:", el.family.value_counts().to_dict(), "by frame:", el.frame.value_counts().to_dict())
print(el.sort_values("t", ascending=False)[["rule", "unit", "n", "t", "t_gross", "PF", "years_pos", "mean_R", "mean_R_gross"]].head(14).round(3).to_string(index=False))
