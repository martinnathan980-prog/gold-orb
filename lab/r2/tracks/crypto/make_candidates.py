"""Assemble results/r2/crypto/candidates.json (finalists with their in-sample and validation numbers) from the
files written during the research.  No market data is loaded here."""
import json, os

OUT = "/home/user/gold-orb/lab/results/r2/crypto"
pre = json.load(open(os.path.join(OUT, "finalists_preval.json")))
val = json.load(open(os.path.join(OUT, "val_results.json")))
detail = [json.loads(l) for l in open(os.path.join(OUT, "trials_detail.jsonl"))]
stages = {}
for d in detail:
    stages[d["stage"]] = stages.get(d["stage"], 0) + 1
distinct = len({(d["sym"], json.dumps(d["params"], sort_keys=True)) for d in detail})
distinct_params = len({json.dumps(d["params"], sort_keys=True) for d in detail})

FX = 0.87
fins = []
for name, f in pre["finalists"].items():
    sleeves = []
    for sym in f["syms"]:
        s = f["sleeves"][sym]
        v = val["finalists"][name]["sleeves"][sym]
        r, rv = s["is"], v["val"]
        sleeves.append({
            "sym": sym,
            "is_n": r["n"], "is_trades_per_year": r["trades_per_year"], "is_win_rate": r["win_rate"], "is_pf": r["pf"],
            "is_t": r["t_stat"], "is_exp_R": r["expectancy_R"], "is_bps_per_trade": s["is_bps_per_trade"],
            "is_years_pos": r["years_pos"], "is_by_year_R": r["by_year_R"], "is_long_R": r["long_R"], "is_short_R": r["short_R"],
            "is_avg_hold_h": r["avg_hold_h"], "is_max_dd_R": r["max_dd_R"],
            "stress_pf": s["is_stress"]["pf"], "gross_pf": s["is_gross"]["pf"], "gross_bps_per_trade": s["is_gross_bps_per_trade"],
            "every_signal_exp_R": s["is_every_signal"]["expectancy_R"], "every_signal_pf": s["is_every_signal"]["pf"],
            "neighbor_pfs": s["neighbor_pfs"], "neighbor_median_pf": s["neighbor_median_pf"],
            "null_percentile": s["null_day"]["percentile"], "null_day": s["null_day"],
            "is_criteria": s["is_criteria"], "is_pass": s["is_criteria"]["pass"],
            "long": s["long"], "short": s["short"],
            "gross_first_half": s["gross_first_half"], "gross_second_half": s["gross_second_half"], "gross_2021": s["gross_2021"],
            "is_excluding_closure_delayed_exits": s["is_excluding_closure_delayed_exits"],
            "val_n": rv["n"], "val_trades_per_year": rv["trades_per_year"], "val_win_rate": rv["win_rate"], "val_pf": rv["pf"],
            "val_exp_R": rv["expectancy_R"], "val_t": rv["t_stat"], "val_years_pos": rv["years_pos"], "val_by_year_R": rv["by_year_R"],
            "val_long_R": rv["long_R"], "val_short_R": rv["short_R"], "val_max_dd_R": rv["max_dd_R"], "val_avg_hold_h": rv["avg_hold_h"],
            "val_bps_per_trade": v["val_bps_per_trade"], "val_pf_equal_notional": rv.get("pf_ret"),
            "val_gross": v["val_gross"], "val_gross_bps_per_trade": v["val_gross_bps_per_trade"],
            "val_stress_pf": v["val_stress"]["pf"], "val_stress_exp_R": v["val_stress"]["expectancy_R"],
            "val_every_signal_exp_R": v["val_every_signal"]["expectancy_R"], "val_every_signal_pf": v["val_every_signal"]["pf"],
            "val_every_signal_by_year_R": v["val_every_signal"].get("by_year_R"),
            "val_criteria": v["val_criteria"], "val_pass": v["val_criteria"]["pass"],
            "median_stop_2024_25": s["stop_2024_25"]["median_stop_dist"], "median_stop_pct_of_price": s["stop_2024_25"]["median_stop_pct_of_price"],
            "min_lot_stop_money_usd": s["stop_2024_25"]["min_lot_stop_usd"], "min_lot_stop_money_eur": s["stop_2024_25"]["min_lot_stop_eur"],
            "min_lot_margin_usd": s["stop_2024_25"]["min_lot_margin_usd"],
        })
    b_is, b_val = f["basket_is"], val["finalists"][name]["basket"]
    fins.append({
        "name": name, "syms": f["syms"], "params": f["params"], "rule": f["rule"], "sleeves": sleeves,
        "basket": {"is": {k: b_is["fp"][k] for k in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "by_year_R", "long_R", "short_R", "max_dd_R")},
                   "is_stress_pf": b_is["stress"]["pf"], "is_every_signal_exp_R": b_is["every"]["expectancy_R"],
                   "val": {k: b_val["fp"][k] for k in ("n", "pf", "t_stat", "expectancy_R", "years_pos", "by_year_R", "long_R", "short_R", "max_dd_R")},
                   "val_stress_pf": b_val["stress"]["pf"], "val_every_signal_exp_R": b_val["every"]["expectancy_R"],
                   "val_criteria": b_val["criteria"]},
        "passes": bool(any(s["is_pass"] and s["val_pass"] for s in sleeves) or b_val["criteria"]["pass"]),
    })

doc = {
    "track": "crypto",
    "trials_logged_lines": len(detail), "distinct_sym_param_configurations": distinct, "distinct_parameter_sets": distinct_params,
    "trials_by_stage": stages,
    "note_on_count": "118 lines in trials.jsonl = 94 distinct (instrument, parameters) configurations: 18 lines re-run the stage-A breakout grid after a bookkeeping fix and 6 lines re-run stage-A configurations in full mode; 8 of the 94 are execution-delay probes.",
    "preval_decided_at_utc": pre["decided_at_utc"],
    "finalists": fins,
    "files": sorted(os.listdir(OUT)),
}
json.dump(doc, open(os.path.join(OUT, "candidates.json"), "w"), indent=1, default=str)
print(json.dumps({k: doc[k] for k in ("trials_logged_lines", "distinct_sym_param_configurations", "distinct_parameter_sets", "trials_by_stage")}))
for f in fins:
    print(f["name"], "passes:", f["passes"], "| basket val:", f["basket"]["val"]["pf"], f["basket"]["val_criteria"]["pass"])
