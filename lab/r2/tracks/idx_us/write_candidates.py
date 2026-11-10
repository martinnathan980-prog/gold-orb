"""candidates.json: the two finalists with their IS dossier and the single-shot validation (no re-tuning)."""
from harness import *     # noqa
pre = json.load(open(os.path.join(RES, "finalists_preval.json")))
val = json.load(open(os.path.join(RES, "val_results.json")))
acc = json.load(open(os.path.join(RES, "account_feasibility.json")))
lines, distinct = n_trials()
desc = {
    "noise30": "Noise-area intraday momentum (Zarattini, Aziz, Barbon 2024, published parameters) on us100: checks at 10:00, 10:30, ..., 15:30 New York; "
               "band = max/min(09:30 open, previous 16:00 price) x (1 +/- mean absolute move from the open to that time of day over the last 14 sessions); "
               "enter at market when the price is outside the band, close when it is back inside at a check or at 15:55; hard stop at the band centre; "
               "one position at a time, flat overnight.",
    "ocm4": "Opening-candle momentum on us100: at 09:34 New York trade the direction of the first 4-minute move (09:30 open -> 09:34) when that move is at "
            "least the median absolute 4-minute opening move of the previous 20 sessions; market entry, stop 0.3 x daily ATR(14), flat at 15:55; "
            "at most one trade a day.",
}
out = {"track": "idx_us", "trials_logged_lines": lines, "trials_distinct_configurations": distinct, "finalists": []}
for name, f in S.FINALISTS.items():
    p = pre["finalists"][name]
    v = val[f"{name}_us100"]
    out["finalists"].append({
        "name": name, "syms": f["syms"], "params": f["params"], "description": desc[name],
        "is": p["is"], "is_bps_per_trade": p["is_bps_per_trade"], "is_gross_bps_per_trade": p["is_gross_bps_per_trade"],
        "is_stress": p["is_stress"], "is_gross": p["is_gross"], "is_every_signal": p["is_every_signal"],
        "neighbor_median_pf": p["neighbor_median_pf"], "neighbor_min_pf": p["neighbor_min_pf"], "neighbors": p["neighbors"],
        "null_test": p["null_test"], "is_criteria": p["is_criteria"],
        "long_short_is": p["long_short"],
        "gross_bp_per_trade_2014_2017": p["gross_bp_per_trade_first_half_2014_2017(n,mean,t)"],
        "gross_bp_per_trade_2018_2021": p["gross_bp_per_trade_second_half_2018_2021(n,mean,t)"],
        "val": v["val"], "val_bps_per_trade": v["val_bps_per_trade"], "val_stress": v["val_stress"], "val_every_signal": v["val_every_signal"],
        "val_criteria": v["val_criteria"],
        "account": acc[name],
        "status": "PASS" if (p["is_criteria"]["pass"] and v["val_criteria"]["pass"]) else "FAIL",
    })
out["caveats"] = pre["disclosed_before_validation"]
out["latency_stress_available"] = {"noise30": "params first_min=601,last_min=931 (whole check grid one minute late): IS PF 1.175 (t 2.13); not run on validation",
                                   "ocm4": "param delay=1 (entry 09:35 instead of 09:34): IS PF 1.234 (t 2.60); not run on validation"}
json.dump(out, open(os.path.join(RES, "candidates.json"), "w"), indent=1, default=str)
for c in out["finalists"]:
    print(c["name"], c["status"], "IS PF", c["is"]["pf"], "t", c["is"]["t_stat"], "| VAL PF", c["val"]["pf"], "t", c["val"]["t_stat"])
