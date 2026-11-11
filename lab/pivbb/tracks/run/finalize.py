"""Finalists: reproduce the engine numbers from FINALISTS, criteria, and write finalists.json (in-sample only)."""
import sys, json, shutil
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd
from goldlab import r2
from pivbb.tracks.run import strategy as S
OUT = "/home/user/gold-orb/lab/results/pivbb/run"
tr = [json.loads(l) for l in open(OUT + "/trials.jsonl")]
by = {t["tag"]: t for t in tr}
NEI = {"r2s2_touch_run": ["nA stop 0.15", "nA stop 0.40", "nA no target", "nA stop-order at level", "nA hours 02-16", "nA first touch", "nA + R3/S3", "B3 R2/S2"],
       "outer_close_ride": ["nB stop 0.15", "nB stop 0.40", "nB hours 02-14", "nB all hours", "nB R2/S2 only", "nB trail mid", "nB exit 15:00", "nB touch market"]}
PLC = {"r2s2_touch_run": "placebo A", "outer_close_ride": "placebo B"}
diag = json.load(open(OUT + "/candidate_diagnostics.json"))
nul = json.load(open(OUT + "/null_test.json"))
nov = json.load(open(OUT + "/novelty.json"))
reg = json.load(open(OUT + "/novelty_regression.json"))
pld = json.load(open(OUT + "/placebo_descriptive_40seeds.json"))
fin = {}
for name, prm in S.FINALISTS.items():
    ev = r2.evaluate("xauusd", S.make_orders, prm)                 # reproduction of an already-logged configuration (not a new trial)
    npf = [by[k]["pf"] for k in NEI[name]]
    crit = r2.is_criteria(ev, neighbor_median_pf=float(np.median(npf)))
    pl = [t for t in tr if t["tag"].startswith(PLC[name])]
    ppf = np.array([t["pf"] for t in pl]); pex = np.array([t["exp_R"] for t in pl])
    r = ev["is"]
    d = diag[name]
    fin[name] = {
        "params": prm, "is": {k: r[k] for k in ("n", "trades_per_year", "win_rate", "pf", "t_stat", "expectancy_R", "years_pos", "long_R", "short_R", "max_dd_R", "avg_hold_h", "max_hold_h") if k in r},
        "by_year_R": r.get("by_year_R"), "stress_pf": ev["is_stress"]["pf"], "gross_pf": ev["is_gross"]["pf"], "gross_exp_R": ev["is_gross"]["expectancy_R"],
        "every_signal": {k: ev["is_every_signal"][k] for k in ("n", "pf", "expectancy_R")}, "net_bps_per_trade": ev["is_bps_per_trade"], "gross_bps_per_trade": ev["is_gross_bps_per_trade"],
        "neighbours": dict(zip(NEI[name], npf)), "neighbours_median_pf": float(np.median(npf)), "criteria": crit,
        "null_test": nul[name],
        "placebo_engine_10_sets": {"pf": [float(x) for x in ppf], "pf_median": float(np.median(ppf)), "pf_min": float(ppf.min()), "pf_max": float(ppf.max()),
                                   "exp_R_median": float(np.median(pex)), "exp_R_max": float(pex.max()), "sets_at_or_above_real_pf": int((ppf >= r["pf"]).sum())},
        "placebo_descriptive_40_sets_gross_every_signal": pld[name],
        "novelty_daily_corr": {"donch4h_stop": nov["daily_mtm_corr"][name]["donch4h_stop"], "orb_asia_2d_buf10": nov["daily_mtm_corr"][name]["orb_asia_2d_buf10"]},
        "novelty_weekly_corr": {"donch4h_stop": nov["weekly_corr"][name]["donch4h_stop"], "orb_asia_2d_buf10": nov["weekly_corr"][name]["orb_asia_2d_buf10"]},
        "novelty_overlap": {k.split("|")[1]: v for k, v in nov.items() if k.startswith(name + "|")}, "novelty_regression": reg[name],
        "erosion": {k: d[k] for k in ("gross_R_2013_2017", "gross_R_2018_2021", "net_R_2013_2017", "net_R_2018_2021", "gross_bps_2013_2017", "gross_bps_2018_2021", "by_year_gross_meanR")},
        "median_stop_usd_2020_2021": d["median_stop_usd_2020_2021"], "p90_stop_usd_2020_2021": d["p90_stop_usd_2020_2021"],
        "min_lot_risk_usd_2020_2021": round(d["median_stop_usd_2020_2021"] * r2.SPEC["xauusd"]["units_per_lot"] * r2.SPEC["xauusd"]["min_lot"], 2),
        "tails": {k: d[k] for k in ("top5_R", "sum_R", "sum_R_without_top10", "t_winsor_3R", "t_daily_cluster")}}
    print(name, json.dumps(fin[name]["is"]), "criteria", crit, "neigh", fin[name]["neighbours_median_pf"], "placebo", fin[name]["placebo_engine_10_sets"])
json.dump(fin, open(OUT + "/finalists.json", "w"), indent=1, default=str)
shutil.copy("/home/user/gold-orb/lab/results/r2/pivbb_run/trials.jsonl", OUT + "/trials_r2_format.jsonl")
print("trials logged:", len(tr), "| r2-format lines:", sum(1 for _ in open(OUT + "/trials_r2_format.jsonl")))
print(pd.Series([t["kind"] for t in tr]).value_counts().to_dict())
