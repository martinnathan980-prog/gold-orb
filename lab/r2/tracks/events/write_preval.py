"""Write the pre-validation decision (finalists fixed on IS only) to results/r2/events/finalists_preval.json."""
import datetime as dt, json, os
from runner import RES, r2, S, n_trials
rows = [json.loads(l) for l in open(f"{RES}/trials_full.jsonl")]
nb = json.load(open(f"{RES}/neighbors_prem.json"))
chk = json.load(open(f"{RES}/preval_checks.json"))
hist = json.load(open(f"{RES}/hist_cost_check_is.json"))
log = os.path.join(RES, "..", "..", "val_access.log")
n_val_before = sum(1 for l in open(log) if '"track": "events"' in l)
fin = S.FINALISTS["EV_PREM_LONG"]
P = S.resolve(fin["params"])
sleeves = {}
for sym in fin["syms"]:
    ev = [r for r in rows if r["tag"] == "F:prem-full" and r["sym"] == sym][-1]["ev"]
    crit = r2.is_criteria(ev, neighbor_median_pf=nb[sym]["median_pf_pm20"])
    c = chk[f"EV_PREM_LONG:{sym}"]
    sleeves[sym] = {
        "is": {k: v for k, v in ev["is"].items() if k != "exit_reasons"},
        "is_bps_per_trade": ev["is_bps_per_trade"], "is_gross_bps_per_trade": ev["is_gross_bps_per_trade"],
        "is_gross": {k: ev["is_gross"][k] for k in ("n", "pf", "t_stat", "expectancy_R")},
        "is_stress": {k: ev["is_stress"][k] for k in ("n", "pf", "t_stat", "expectancy_R")},
        "is_every_signal": {k: ev["is_every_signal"][k] for k in ("n", "pf", "t_stat", "expectancy_R")},
        "neighbors": nb[sym], "is_criteria": crit, "null_time": c["null"],
        "gross_bps_first_half": c["gross_bps_first_half"], "gross_bps_second_half": c["gross_bps_second_half"],
        "cost_x3": c["cost_x3"], "median_stop_2024_25": c["median_stop_2024_25"],
        "min_lot_stop_money_usd": c["min_lot_stop_money_quote"], "historical_cost_model_is": hist[sym],
    }
out = {
    "written_utc": dt.datetime.utcnow().isoformat(timespec="seconds"),
    "track": "events", "trials_logged_before_validation": n_trials(),
    "validation_accesses_by_this_track_before_this_file": n_val_before,
    "decision": "ONE finalist rule (2 index sleeves). Fixed on in-sample data (entries < 2022-01-01) only.",
    "finalists": {"EV_PREM_LONG": {
        "rule": "Buy at market 5 minutes before every scheduled FOMC statement (14:00 NY), NFP and CPI release (08:30 NY); "
                "stop 1.0 x ATR_D(14) below the fill; time exit 15 minutes after the release.",
        "syms": fin["syms"], "params": P, "sleeves": sleeves, "basket_is": chk["EV_PREM_LONG:basket"],
        "known_weaknesses": [
            "us500 and us100 are one bet (R correlation 0.94): event-clustered basket t = 2.70, not the naive 3.82",
            "in-sample edge comes from FOMC and NFP; CPI contributed nothing in 2013-2021",
            "t without the 5 best trades: 1.78 (us500) / 1.91 (us100)",
            "found after ~630 overlapping descriptive cells and a grid of 8: the in-sample t is biased upward",
            "fails t >= 2.5 under the historical Dukascopy spread (PF 1.39 / 1.28, t 1.84 / 1.38): needs today's tight index spread",
            "long only; the position is held THROUGH the release (stop slippage in the release minute is not modelled; 1 stop in 268 trades)",
        ]}},
    "not_finalist": {"XAU_FOMC_MOM": {
        "rule": "gold, 5 min after the FOMC statement follow the first move, stop 0.5 ATR_D, exit next day 15:55 NY",
        "is": "n 70, PF 2.31, t 2.57, +45.7 bp/trade", "why_rejected": "n = 70 can never reach 250 (8 events a year); the gross edge "
        "is +103.9 bp/trade in 2013-mid 2017 and -6.1 bp/trade in mid 2017-2021 (eroded). Not sent to validation."}},
}
json.dump(out, open(f"{RES}/finalists_preval.json", "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k != "finalists"}, indent=1))
for sym, s in sleeves.items():
    print(sym, s["is_criteria"], "nb median", s["neighbors"]["median_pf_pm20"], "null pct", s["null_time"]["percentile"])
