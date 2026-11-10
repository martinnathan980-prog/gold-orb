"""Write the pre-validation decision (finalists chosen on IS only) BEFORE any validation access."""
import datetime as dt
from harness import *     # noqa
import harness

det = harness._load_detail()
def ev_of(sym, params):
    return det[harness._key(sym, S.resolve(params))]["ev"]
def pf_of(sym, params):
    return ev_of(sym, params)["is"]["pf"]

A = S.FINALISTS["noise30"]["params"]; B = S.FINALISTS["ocm4"]["params"]
neighA = [("lookback", 11), ("lookback", 17), ("vm", 0.8), ("vm", 1.2), ("step", 15), ("step", 60), ("first_min", 585), ("first_min", 630),
          ("last_min", 900), ("exit_min", 945), ("exit_min", 959), ("hs_atr", 0.5)]
latA = [{"first_min": 601, "last_min": 931}, {"first_min": 602, "last_min": 932}, {"first_min": 605, "last_min": 935}]
neighB = [("n", 3), ("n", 5), ("k", 0.24), ("k", 0.36), ("size_min", 0.8), ("size_min", 1.2), ("size_win", 16), ("size_win", 24),
          ("atr_n", 11), ("atr_n", 17), ("exit_min", 930), ("exit_min", 959), ("delay", 1)]
rowsA = [{"change": {k: v}, "pf": pf_of("us100", {**A, k: v}), "t": ev_of("us100", {**A, k: v})["is"]["t_stat"]} for k, v in neighA]
rowsA += [{"change": c, "pf": pf_of("us100", {**A, **c}), "t": ev_of("us100", {**A, **c})["is"]["t_stat"], "kind": "latency: whole check grid shifted"} for c in latA]
rowsB = [{"change": {k: v}, "pf": pf_of("us100", {**B, k: v}), "t": ev_of("us100", {**B, k: v})["is"]["t_stat"]} for k, v in neighB]
nulls = json.load(open(os.path.join(RES, "null_tests.json")))
diag = json.load(open(os.path.join(RES, "finalist_diag_is.json")))
caus = json.load(open(os.path.join(RES, "causality_test.json")))
out = {
    "track": "idx_us",
    "written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "statement": "Finalists chosen on the in-sample period only (entries before 2022-01-01). No validation result has been computed, "
                 "printed or read by this track before this file was written. After this file: one r2.validate call per finalist sleeve, "
                 "no re-tuning whatever the result.",
    "trials_at_decision": {"lines_in_trials_jsonl": n_trials()[0], "distinct_configurations": n_trials()[1]},
    "judging_rule": "Each finalist has ONE sleeve (us100) and is judged alone: IS criteria of PROTOCOL_V2 section 4 (all met, see below) and "
                    "VAL criteria (PF >= 1.06, expectancy > 0, every-signal expectancy > 0). No basket. us500 and us30 are NOT finalists: "
                    "the same rules have IS PF 1.09-1.14 on us500 (t 1.2-1.6, edge about 2x cost, fragile to the check-grid phase) and <= 1.10 on us30.",
    "finalists": {},
    "disclosed_before_validation": [
        "Both rules were selected on us100 after seeing the three indices: us100 is the best of three (selection).",
        "noise30 is the published rule with the published parameters (no tuning). Its IS PF is 1.28 on the HH:00/HH:30 grid; with the whole "
        "grid shifted by +1/+2/+5/+15/+30 minutes it is 1.175/1.170/1.249/1.231/1.252 (t 2.1-2.9): the data show a +0.4-0.5 bp continuation in "
        "the single minute after HH:00/HH:30 when the price is outside the band; the back-test gets it by filling at the first tick of that "
        "minute. A live EA should count on PF about 1.2, not 1.28.",
        "ocm4 replaces the literature 5-minute candle (IS PF 1.31, t 3.3): with n=5 about 1.8 bp of the 6.5 bp net edge is earned in the single "
        "minute 09:35-09:36 and an entry one minute late gives PF 1.17 (t 1.9). The 4-minute candle enters before that minute; an entry one "
        "minute late leaves it unchanged (PF 1.234). Its neighbours n=3 (1.13) and n=5 (1.31) show how noisy the family is: honest PF about 1.2.",
        "ocm4 gross edge per trade halves between 2014-2017 (6.99 bp, t 2.6) and 2018-2021 (3.64 bp, t 0.95); 2015 is a losing year, 2020 flat.",
        "Profits are concentrated: the 10 best days give 53% (noise30) and 47% (ocm4) of the total IS R. Trend-following payoff.",
        "The two sleeves trade the same instrument; daily-R correlation about 0.4 on IS.",
    ],
    "causality_test": caus,
}
for name, P in (("noise30", A), ("ocm4", B)):
    ev = ev_of("us100", P)
    rows = rowsA if name == "noise30" else rowsB
    med = float(np.median([r["pf"] for r in rows]))
    key = "noise30_us100" if name == "noise30" else "ocm4_us100"
    nk = "noise_us100" if name == "noise30" else "ocm4_us100"
    out["finalists"][name] = {
        "syms": ["us100"], "params": P,
        "is": {k: v for k, v in ev["is"].items()},
        "is_bps_per_trade": ev["is_bps_per_trade"], "is_gross_bps_per_trade": ev["is_gross_bps_per_trade"],
        "is_stress": ev["is_stress"], "is_gross": ev["is_gross"], "is_every_signal": ev["is_every_signal"],
        "neighbors": rows, "neighbor_median_pf": med, "neighbor_min_pf": float(min(r["pf"] for r in rows)),
        "is_criteria": r2.is_criteria(ev, neighbor_median_pf=med),
        "null_test": {k: nulls[nk][k] for k in ("n", "mode", "rule_mean_R", "null_mean_R", "null_p95_R", "null_max_R", "percentile", "pass")},
        "long_short": diag[key]["by_side"],
        "gross_bp_per_trade_first_half_2014_2017(n,mean,t)": diag[key]["gross_bp_per_trade_2014_2017"],
        "gross_bp_per_trade_second_half_2018_2021(n,mean,t)": diag[key]["gross_bp_per_trade_2018_2021"],
        "stop_bp_median_by_year": diag[key]["stop_bp_median_by_year"],
        "top10_days_share_of_total_R": diag[key]["top10_days_share_of_total_R"],
        "daily_R": diag[key]["daily_R"],
    }
    print(name, "IS criteria:", out["finalists"][name]["is_criteria"], "| neighbour median PF", round(med, 3), "| null pct", nulls[nk]["percentile"])
p = os.path.join(RES, "finalists_preval.json")
assert not os.path.exists(p), "pre-validation file already written"
json.dump(out, open(p, "w"), indent=1, default=str)
print("written", p)
