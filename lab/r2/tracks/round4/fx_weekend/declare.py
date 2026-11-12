"""Round 4 (PROTOCOL_V3 Addendum J), rule 2: FX weekend overreaction fade (G10 basket) -- DECLARATION.

Written and run BEFORE any price frame is read.  Copies the judge's frozen texts verbatim from
lab/results/r2/round4_ideas.json (judge.ranking[1]) and records every reading of a detail the text leaves open
(the most conservative one each time), the eleven configurations, the criteria and the reports.

    PYTHONDONTWRITEBYTECODE=1 python3 declare.py
"""
import datetime as dt
import hashlib
import json
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SRC = os.path.join(LAB, "results", "r2", "round4_ideas.json")
OUT = os.path.join(LAB, "results", "r2", "round4", "fx_weekend", "declared.json")
SHA_FROZEN = "c81387985baf8e43d64caa339c75daf4d3ff936a925ef28d97ff94755b5e225a"

raw = open(SRC, "rb").read()
sha = hashlib.sha256(raw).hexdigest()
assert sha == SHA_FROZEN, f"round4_ideas.json changed: {sha}"
J = json.loads(raw)["judge"]["ranking"][1]
assert J["name"] == "FX weekend overreaction fade (G10 basket)", J["name"]

PAIRS = ["eurusd", "gbpusd", "usdjpy", "audusd", "usdcad", "usdchf", "nzdusd", "eurjpy"]
MAIN = dict(q=75, dec="20:00", exit="mon16", stop_atr=1.0)
CONFIGS = [
    {"id": 1, "label": "main", "role": "main", "params": dict(MAIN), "costs": "fp"},
    {"id": 2, "label": "thr_P65", "role": "neighbour", "params": dict(MAIN, q=65), "costs": "fp"},
    {"id": 3, "label": "thr_P85", "role": "neighbour", "params": dict(MAIN, q=85), "costs": "fp"},
    {"id": 4, "label": "dec_1900", "role": "neighbour", "params": dict(MAIN, dec="19:00"), "costs": "fp"},
    {"id": 5, "label": "dec_2100", "role": "neighbour", "params": dict(MAIN, dec="21:00"), "costs": "fp"},
    {"id": 6, "label": "exit_tue12", "role": "neighbour", "params": dict(MAIN, exit="tue12"), "costs": "fp"},
    {"id": 7, "label": "exit_wed12", "role": "neighbour", "params": dict(MAIN, exit="wed12"), "costs": "fp"},
    {"id": 8, "label": "stop_0.75atr", "role": "neighbour", "params": dict(MAIN, stop_atr=0.75), "costs": "fp"},
    {"id": 9, "label": "stop_1.5atr", "role": "neighbour", "params": dict(MAIN, stop_atr=1.5), "costs": "fp"},
    {"id": 10, "label": "main_costs_x1.5", "role": "stress", "params": dict(MAIN), "costs": "x1.5"},
    {"id": 11, "label": "null_200_replays", "role": "null", "params": dict(MAIN), "costs": "fp",
     "null": {"replays": 200, "seed": 20261112}},
]

READINGS = [
    ("data",
     "Frames lab/data/fp/<pair>_m1.parquet only, read with the pyarrow row filter ts < 2022-01-01 00:00 UTC before "
     "anything else; that slice is passed explicitly to every function and simulation (never goldlab.r2.load / r2.run / "
     "r2.null_test, which read the full frame). Trades are kept only with entry < 2022-01-01; the last decision Sunday "
     "is 2021-12-26 and its latest exit (Wednesday 2021-12-29 12:00 NY) is inside the slice. Official trades of the ten "
     "are read with the filter entry_time < 2022-01-01 in the same statement."),
    ("clock", "America/New_York from the tz database (DST-aware). Decision Sundays: every calendar Sunday of the slice."),
    ("F",
     "mid = (bid open + ask open)/2 of the first M1 bar whose start is in [Friday 16:50, Friday 17:05) NY, the Friday "
     "two days before the decision Sunday. The text gives no tolerance for F; the 15-minute tolerance it gives for P is "
     "applied, and a pair with no such bar (holiday Fridays, gaps) is skipped that weekend -- never a later bar."),
    ("P", "mid of the open of the first M1 bar whose start is in [D, D + 15 min); none -> the pair is skipped that weekend."),
    ("entry",
     "The decision uses the OPEN of the P bar, i.e. that bar is not closed when P is known. To keep decisions on closed "
     "information only (task rule 3) the market order is filled at the open of the NEXT M1 bar (one minute later in "
     "normal data), never on the tick that defines P. That bar must start no later than D + 15 min, else the pair is "
     "skipped that weekend. Long fills at the ask, short at the bid, plus 0.1 bp market slippage."),
    ("sigma",
     "Sample sd (ddof 1) of the last 60 log returns of daily MID closes, daily bars = the lab's trading days ending "
     "17:00 NY built by goldlab.full_days (days with at least 600 M1 bars; holiday stubs dropped), using only days "
     "complete at D (t_close <= D): the last return ends at Friday's 17:00 close. Fewer than 60 returns -> no z."),
    ("z", "z = ln(P/F) / sigma; z = 0 -> no signal."),
    ("threshold",
     "numpy.percentile (linear interpolation) at q of the pair's |z| over its previous 104 weekends that HAVE a z (the "
     "current weekend excluded), at least 52 such values, else no decision (warm-up). Each configuration uses the |z| "
     "history of its own decision clock (19:00 / 20:00 / 21:00). Signal when |z| >= that value."),
    ("side", "-sign(z): fade the weekend move."),
    ("atr",
     "ATR(20) = goldlab.atr (Wilder, alpha 1/20, mid true range) on the same full daily bars, value of the last day "
     "complete at D (Friday). Stop distance = stop_atr x ATR(20), from the fill, fixed (no trailing, no target)."),
    ("broker_min_stop",
     "A trade whose stop distance is below 3 x the spread of its entry bar (ask open - bid open of the frame used, i.e. "
     "the widened spread in the x1.5 run) is refused (not taken) and counted."),
    ("exit",
     "Market at the open of the first M1 bar at or after Monday 16:00 NY (Tuesday 12:00 / Wednesday 12:00 in (6)/(7)) via "
     "goldlab.exit_index (if that time falls in a closure of more than 30 min, the last bar before it). Exit bar must be "
     "after the entry bar. Stops are resting orders filled by the lab simulator (stop slippage 0.3 bp; gap -> worse of "
     "stop/open; stop assumed hit inside a bar that touches it)."),
    ("costs",
     "FP frames (FP Raw spread with the 6 USD/lot commission folded in, Dukascopy's intraday spread shape including Sunday "
     "evening, clipped 0.7x-6x the trading day's median) + goldlab.r2.costs(pair): market slippage 0.1 bp/side, stop "
     "0.3 bp, swaps of r2/fp_costs.json on the paying side only (credits ignored), Wednesday triple; the simulator charges "
     "one swap per 17:00 NY rollover crossed: none for exits on Monday 16:00, 1 night for Tuesday 12:00, 2 for Wednesday "
     "12:00."),
    ("stress", "(10) = main with spread x1.5 around the mid and both slippages x1.5 (goldlab.r2 'stress' mode: orders rebuilt on the widened quotes; mids and signals unchanged)."),
    ("positions",
     "One position per pair (simulate no_overlap=True per pair; the rule cannot overlap itself: one decision per pair "
     "per weekend, exits before the next Friday). The every-signal run (no_overlap=False) is computed for the main. No "
     "cap across pairs ('the robot's position cap is applied afterwards')."),
    ("basket_stats",
     "Pooled over the pairs kept after the pre-check. t on daily sums = t of the sums of R per trading day of ENTRY (all "
     "entries of a weekend fall on its Monday trading day), days with at least one trade. PF on R. Years by calendar "
     "year of entry (UTC). Pair positive = pair expectancy in R > 0. Pair share = pair total R / pooled total R (fails "
     "if the pooled total is not positive). R = net pnl / initial stop distance (1 R per trade, equal R per pair)."),
    ("criteria",
     "Judge's PASS list for the main configuration, plus the single-sleeve bars of PROTOCOL_V3 s.4 / PROTOCOL_V2 s.4 that "
     "the basket text does not replace (n >= 250, max hold <= 5 trading days): all must hold."),
    ("neighbours_median", "Median of the pooled PF (FP costs) of configurations (2)-(9) (8 values)."),
    ("null",
     "(11): for each of the main's trades, 200 times: a weekend drawn at random (uniform, with replacement, seeded) "
     "among that pair's decision weekends of the main (weekends after the 52-value warm-up whose P bar and entry bar "
     "exist), re-entered at the same Sunday clock exactly as the rule enters (open of the bar after the first bar at or "
     "after 20:00 NY), same pair, same side, same stop as a fraction of price (scaled to the replay's entry mid), same "
     "holding time (exit at the same Monday 16:00 NY clock via goldlab.exit_index), FP costs, every replayed trade "
     "simulated (no_overlap=False); the statistic is the pooled mean R of each replay; pass if the main's mean R is "
     "above at least 97.5 % of the 200 replay means."),
    ("precheck",
     "Not trials. (a) For each pair, share of the calendar Sundays 2014-01-05 .. 2021-12-26 with an M1 bar starting in "
     "[20:00, 20:15) NY; below 90 % the pair is dropped before the run. (b) Median frame spread (ask open - bid open, in "
     "bp of mid) of the bar starting at 20:00 NY on Sundays against Monday-Thursday, 2014-2021."),
    ("reported_information",
     "From the main's trades only (no new configuration): split by USD side (long USD / short USD / cross eurjpy); "
     "|z| >= 1.5 against the rest; mean path at Sunday 22:00, Monday 03:00, 08:00 and 16:00 NY (unstopped mid move in "
     "the trade's direction in bp and R, and the share already stopped); net result split into gross move and cost paid "
     "per trade (accounting of the same trades, not a re-simulation); weekly correlation (sums of R per exit week, "
     "every calendar week 2014-01 .. 2021-12) with the sum of the ten and with each cluster (us100: noise30 + ocm4; gold: "
     "GOLD_FRI_PM + donch4h_stop + orb_asia_2d_buf10; crypto: brk72_24h_wd btc + eth, F1_brk_ridge_filter btc + eth, "
     "nq_btc_follow), the main's weekly Sharpe and the change of the ten's weekly Sharpe when it is added at 1 R."),
    ("causality",
     "Truncation test on at least 50 decisions: the decision quantities (F, P, sigma, z, threshold, side, ATR, stop "
     "distance, P-bar time) recomputed on a frame cut just after the P bar, with that bar's high, low and close "
     "blanked (only its open survives), must equal the full-frame ones; plus orders rebuilt on frames cut at random "
     "times must equal the full-frame orders decided before the cut."),
    ("mt5_sunday_spread",
     "The judge's 'BEFORE ANY VAL LOOK' condition (FP's Sunday 20:00 NY spreads read in MT5; if above 2x the frame's, "
     "recompute the in-sample row) needs the user's MT5: it cannot be read here and is reported as pending."),
]

CRITERIA_MAIN = [
    "t on daily (Monday) sums >= 2.5",
    "pooled PF >= 1.12",
    "pooled PF >= 1.04 at costs x1.5 (config 10)",
    ">= 60 % of years positive",
    ">= 6 of 8 pairs positive (65 % of the pairs kept)",
    "no pair above 25 % of the profit",
    "neighbours' median PF >= 1.06 (configs 2-9)",
    "every-signal expectancy > 0",
    "null >= 97.5th percentile (config 11)",
    "n >= 250 (PROTOCOL_V2 s.4)",
    "max hold <= 5 trading days (PROTOCOL_V2 s.4)",
]

out = {
    "written_utc": dt.datetime.utcnow().isoformat(timespec="seconds"),
    "written_before_any_price_frame_was_read": True,
    "protocol": "PROTOCOL_V3.md Addendum J (round 4), rule 2; in sample only (2013-2021 frames, trades 2014-2021)",
    "short_name": "fx_weekend",
    "source": {"file": "lab/results/r2/round4_ideas.json", "sha256": sha, "path": "judge.ranking[1]"},
    "judge_frozen": {k: J[k] for k in ("name", "score", "prior_pass_validation_pct", "why", "rule", "instruments",
                                       "test_plan", "instruments_note")},
    "pairs": PAIRS,
    "configurations": CONFIGS,
    "trials_declared": len(CONFIGS),
    "verdict_read_on": "configuration 1 only; 2-9 neighbours, 10 cost stress, 11 random-entry null",
    "criteria_main": CRITERIA_MAIN,
    "readings_of_open_details": {k: v for k, v in READINGS},
    "files": {
        "code": "lab/r2/tracks/round4/fx_weekend/",
        "results": "lab/results/r2/round4/fx_weekend/ (declared.json, precheck.json, trials.jsonl, results.json, "
                   "truncation.json, correlation.json, trades_*.parquet)",
    },
}
if os.path.exists(OUT):
    raise SystemExit(f"{OUT} exists: the declaration is written once")
with open(OUT, "w") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
print("written", OUT, "sha256 of source", sha)
