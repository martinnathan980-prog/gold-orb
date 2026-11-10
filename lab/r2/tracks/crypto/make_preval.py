"""Assemble results/r2/crypto/finalists_preval.json from the logged in-sample material.
Run BEFORE any validation access (the script refuses to run if the track already appears in val_access.log)."""
import datetime, json, os, sys
sys.path.insert(0, "/home/user/gold-orb/lab"); sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
from goldlab import r2
from final_cfg import FINAL, SYMS

OUT = "/home/user/gold-orb/lab/results/r2/crypto"
VAL_LOG = "/home/user/gold-orb/lab/results/val_access.log"

if os.path.exists(VAL_LOG):
    acc = [json.loads(l) for l in open(VAL_LOG) if l.strip()]
    assert not any(a.get("track") == "crypto" for a in acc), "validation already accessed for this track"

detail = [json.loads(l) for l in open(os.path.join(OUT, "trials_detail.jsonl"))]
lines = len(detail)
distinct = len({(d["sym"], json.dumps(d["params"], sort_keys=True)) for d in detail})
diag = json.load(open(os.path.join(OUT, "finalist_diag.json")))
nb = json.load(open(os.path.join(OUT, "neighbors_weekday.json")))
nul = json.load(open(os.path.join(OUT, "null_tests.json")))
caus = json.load(open(os.path.join(OUT, "causality.json")))

RULES = {
    "brk72_24h_wd": "H1 bars of mid prices on the UTC hour grid. At the end of each H1 bar whose end time falls on Monday-Friday (UTC), if no trade of this sleeve is open: go LONG at market if the close of the bar just finished is above the highest close of the previous 72 H1 bars, SHORT if it is below the lowest close of the previous 72 H1 bars. Initial and only stop: 3 x ATR(24) from the fill (ATR = mean true range of the last 24 H1 bars, frozen at the decision). No target, no trailing. Time exit at market 24 hours after the decision. A signal that arrives while a trade is open (including the minute at which that trade is closed by its time exit) is ignored. Signal skipped if no quote within 5 minutes after the bar end.",
    "sess_8_8_13_wd": "H1 bars of mid prices on the UTC hour grid. Every Monday-Friday at 08:00 UTC: move = close of the H1 bar ending at 08:00 UTC minus the close of the H1 bar ending at 00:00 UTC. LONG at market if move > 0, SHORT if move < 0 (no trade if either bar is missing). Stop: 3 x ATR(24) from the fill (mean true range of the last 24 H1 bars). No target, no trailing. Time exit at market at 21:00 UTC the same day (13 hours after the decision). Signal skipped if no quote within 5 minutes after 08:00 UTC.",
}

fin = {}
for name, p in FINAL.items():
    f = {"syms": list(SYMS), "params": p, "rule": RULES[name], "sleeves": {}}
    for sym in SYMS:
        ev = [d for d in detail if d["sym"] == sym and d["params"] == p and d["full"]][-1]["ev"]
        k = f"{name}:{sym}"
        nbm = nb[k]["median_pf"]
        crit = r2.is_criteria(ev, neighbor_median_pf=nbm)
        crit["null>=97.5pct"] = bool(nul[f"{k}:day"]["percentile"] >= 97.5)
        crit["pass"] = bool(all(v for q, v in crit.items() if q != "pass"))
        d = diag[k]
        f["sleeves"][sym] = {
            "is": ev["is"], "is_bps_per_trade": ev["is_bps_per_trade"],
            "is_stress": ev["is_stress"], "is_gross": ev["is_gross"], "is_gross_bps_per_trade": ev["is_gross_bps_per_trade"],
            "is_every_signal": ev["is_every_signal"],
            "neighbor_pfs": nb[k]["pfs_sorted"], "neighbor_median_pf": nbm,
            "null_day": nul[f"{k}:day"], "null_time_for_information": nul[f"{k}:time"],
            "is_criteria": crit,
            "long": d["long"], "short": d["short"],
            "gross_first_half": d["first_half_gross"], "gross_second_half": d["second_half_gross"], "halves_split_at": d["halves_split_at"],
            "gross_2021": d["y2021_gross"],
            "is_excluding_closure_delayed_exits": d["is_excluding_closure_delayed_exits"],
            "top5pct_share_of_total_R": d["top5pct_share_of_total_R"],
            "stop_2024_25": d["stop_2024_25"],
            "historical_dukascopy_spread_for_information": d["historical_dukascopy_spread"],
            "truncation_test_all_equal": caus[k]["all_equal"],
        }
    f["basket_is"] = diag[f"{name}:basket"]
    fin[name] = f

doc = {
    "decided_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "track": "crypto",
    "trials_logged_lines": lines,
    "distinct_configurations": distinct,
    "validation_access_before_this_file": "none",
    "finalists": fin,
    "validation_plan": [
        "one r2.validate call per finalist sleeve: (brk72_24h_wd, btcusd), (brk72_24h_wd, ethusd), (sess_8_8_13_wd, btcusd), (sess_8_8_13_wd, ethusd)",
        "each sleeve is judged alone on PROTOCOL_V2 section 4 (PF >= 1.06, expectancy > 0, every-signal expectancy > 0)",
        "in addition each finalist is reported as a two-instrument basket (pooled trades, same parameters); the basket passes only if pooled PF >= 1.06, pooled expectancy > 0, pooled every-signal expectancy > 0 AND the expectancy is positive on each instrument (strict reading of the basket clause)",
        "no parameter, filter or instrument is changed after the validation run, whatever the result",
    ],
    "decision_notes": [
        "Both rules were first screened and neighbour-tested WITHOUT a day filter (trials 1-86). The weekday-only form was adopted before validation because the in-sample data cannot support weekend trading: no weekend quotes at all in 2017-2018, partial ones in 2019-2020, and where weekend decisions exist (2019-2021) their expectancy is about zero in all four sleeves (-0.05R / +0.12R for the breakout on BTC / ETH, -0.06R / +0.03R for the session rule) against +0.11R to +0.26R on weekdays. The choice was made after looking at that split: the in-sample numbers of the weekday-only form are therefore slightly flattering (the all-days numbers are in trials 45-50 and finalist_diag_alldays.json).",
        "Known weaknesses stated before validation: (1) the gross edge shrinks through the sample - for the BTC breakout 92 bp per trade in the first half vs 43 bp in the second and 23 bp in 2021; the session rule earns ~2 bp gross per trade in 2021 on both instruments; (2) in 2021 - the only in-sample year with clean 24/7 quotes - the every-signal run of the breakout is flat on both instruments (BTC +8.8R on 703 signals, ETH -1.8R on 709 signals) although the one-position run made +12.1R and +15.4R (160 trades each): per signal there was no edge left in 2021; (3) in 2017-2018 the trades whose exit waited for the weekend reopening of the Dukascopy feed made about +1R each (31 BTC / 14 ETH breakout trades, 41 / 27 session trades); without every closure-delayed exit (34 / 18 / 42 / 28 trades) each sleeve still passes (PF 1.34-1.67, t 3.4-4.0); (4) the 2017 BTC quotes are noisy and the 2018-2020 Dukascopy spreads were 1-4 % of price - the mid prices are usable at H1 but that market was not tradable at those quotes (historical-spread run: PF 0.24-0.42).",
        "My own expectation before the run: more likely than not the validation fails (the 2021 collapse looks like decay, not noise); the breakout has a better chance than the session rule.",
    ],
}
json.dump(doc, open(os.path.join(OUT, "finalists_preval.json"), "w"), indent=1, default=str)
for name, f in fin.items():
    for sym, s in f["sleeves"].items():
        print(name, sym, "IS criteria:", s["is_criteria"])
print("written; lines", lines, "distinct", distinct)
