"""Assemble the final evidence files after the single validation run (no new simulation of the
validation period: it only merges val_results.json into candidates.json and tabulates the IS trials)."""
import csv
import json
import os

from research import OUT, _load_cache

cache = _load_cache()
rows = sorted(cache.values(), key=lambda r: r["n_trial"])
with open(os.path.join(OUT, "trials_summary.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["trial", "tag", "family", "params", "n", "per_year", "win", "exp_R", "pf", "t", "years_pos", "max_dd_R",
                "long_R", "short_R", "avg_hold_h", "net_bps", "gross_pf", "gross_bps", "stress_pf", "every_signal_exp_R"])
    for r in rows:
        ev, i = r["ev"], r["ev"]["is"]
        w.writerow([r["n_trial"], r["tag"], r["params"]["family"], json.dumps({k: v for k, v in r["params"].items() if k != "family"}),
                    i["n"], i["trades_per_year"], i["win_rate"], i["expectancy_R"], i["pf"], i["t_stat"], i["years_pos"], i["max_dd_R"],
                    i["long_R"], i["short_R"], i["avg_hold_h"], ev["is_bps_per_trade"], ev["is_gross"]["pf"], ev["is_gross_bps_per_trade"],
                    ev["is_stress"]["pf"], ev["is_every_signal"]["expectancy_R"]])

cand = json.load(open(os.path.join(OUT, "candidates.json")))
val = json.load(open(os.path.join(OUT, "val_results.json")))
for name, d in cand["finalists"].items():
    v = val[f"{name}:ger40"]
    d["validation"] = {"val": v["val"], "val_bps_per_trade": v["val_bps_per_trade"], "val_stress": v["val_stress"],
                       "val_every_signal": v["val_every_signal"], "val_criteria": v["val_criteria"], "run_utc": v["run_utc"]}
    d["passes_is_and_val"] = bool(d["is_criteria"]["pass"] and v["val_criteria"]["pass"])
by_tag = {r["tag"]: r for r in rows}


def brief(tag):
    r = by_tag[tag]
    ev, i = r["ev"], r["ev"]["is"]
    return {"trial": r["n_trial"], "params": r["params"], "n": i["n"], "per_year": i["trades_per_year"], "pf": i["pf"], "t": i["t_stat"],
            "exp_R": i["expectancy_R"], "years_pos": i["years_pos"], "max_dd_R": i["max_dd_R"], "long_R": i["long_R"], "short_R": i["short_R"],
            "net_bps": ev["is_bps_per_trade"], "gross_bps": ev["is_gross_bps_per_trade"], "stress_pf": ev["is_stress"]["pf"],
            "by_year_R": i.get("by_year_R")}


cand["not_selected_candidates"] = {
    "morning_gap_momentum_exit1600 (S3_B09)": brief("S3_B09_grid_exit1600") | {
        "null_percentile": 99.0, "status": "passes the IS thresholds; NOT a finalist (long-skewed: short side +0.058 R/trade t 0.45; "
        "fat-tailed: without its 10 best trades t = 1.07); validation data untouched for it"},
    "morning_gap_momentum_exit1730 (S2_B03)": brief("S2_B03_grid0930-1030") | {
        "null_percentile": 99.5, "status": "same rule held to 17:30; a third of its edge is the late-day effect that failed validation"},
}
cand["screens"] = {t: brief(t) for t in by_tag if t.startswith("S1_")}
cand["n_trials_logged"] = len(rows)
cand["verdict"] = ("late_mom_1600 FAILS validation (PF 0.977). close_run_1725 passes the letter of the validation criteria "
                   "(PF 1.105, +0.0105 R/trade, t 0.93) but is negative with costs x1.5 and in 2 of 4 years: not confirmed.")
json.dump(cand, open(os.path.join(OUT, "candidates.json"), "w"), indent=1, default=str)
print("trials:", len(rows))
for r in rows:
    ev, i = r["ev"], r["ev"]["is"]
    print(f"| {r['n_trial']} | {r['tag']} | {i['n']} | {i['trades_per_year']} | {i['win_rate']:.3f} | {i['expectancy_R']:+.4f} | {i['pf']:.3f} | {i['t_stat']:+.2f} | {i['years_pos']} | {i['max_dd_R']} | {i['long_R']:+.1f} | {i['short_R']:+.1f} | {ev['is_bps_per_trade']:+.2f} | {ev['is_gross']['pf']:.3f} | {ev['is_gross_bps_per_trade']:+.2f} | {ev['is_stress']['pf']:.3f} |")
