"""PROTOCOL_V3 Addendum J, rule 3 (ger40_noise30_xetra): write declared.json BEFORE any run.

The judge's texts are copied verbatim from results/r2/round4_ideas.json (judge.ranking[2], sha256 checked).  Every
detail the texts leave open is given ONE reading here (the most conservative one), before any simulation, signal or
trade of this rule is computed.  The only data look before this file: bar counts and quote activity of the ger40
in-sample frame between 09:00 and 17:30 Berlin on candidate holidays and on the last trading day of each year (to
check the calendar); no signal, band, order or trade of the rule was computed.

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
OUT = os.path.join(LAB, "results", "r2", "round4", "ger40_noise30_xetra")
SHA = "c81387985baf8e43d64caa339c75daf4d3ff936a925ef28d97ff94755b5e225a"

MAIN = {"lookback": 14, "vm": 1.0, "step": 30, "first_min": 570, "last_min": 1020, "exit_min": 1045}
CONFIGS = [
    {"id": 1, "name": "main", "role": "main", "params": dict(MAIN), "costs": "fp"},
    {"id": 2, "name": "lookback_11", "role": "neighbour", "params": {**MAIN, "lookback": 11}, "costs": "fp"},
    {"id": 3, "name": "lookback_17", "role": "neighbour", "params": {**MAIN, "lookback": 17}, "costs": "fp"},
    {"id": 4, "name": "band_0.8", "role": "neighbour", "params": {**MAIN, "vm": 0.8}, "costs": "fp"},
    {"id": 5, "name": "band_1.2", "role": "neighbour", "params": {**MAIN, "vm": 1.2}, "costs": "fp"},
    {"id": 6, "name": "step_15", "role": "neighbour", "params": {**MAIN, "step": 15}, "costs": "fp"},
    {"id": 7, "name": "step_60", "role": "neighbour", "params": {**MAIN, "step": 60}, "costs": "fp"},
    {"id": 8, "name": "first_0915", "role": "neighbour", "params": {**MAIN, "first_min": 555}, "costs": "fp"},
    {"id": 9, "name": "first_0945", "role": "neighbour", "params": {**MAIN, "first_min": 585}, "costs": "fp"},
    {"id": 10, "name": "main_costs_x1.5", "role": "stress", "params": dict(MAIN), "costs": "x1.5"},
    {"id": 11, "name": "null_day_200", "role": "null", "params": dict(MAIN), "costs": "fp",
     "null": {"mode": "day", "replays": 200, "seed": 0, "clock": "Europe/Berlin minute of day"}},
]


def checks_of(p):
    """Berlin clock times of the checks of a configuration (noise30 code: np.arange(first, last + 1, step))."""
    return [f"{m // 60:02d}:{m % 60:02d}" for m in range(p["first_min"], p["last_min"] + 1, p["step"])]


READINGS = {
    "R01_period": "IN SAMPLE ONLY. The ger40 FP frame (lab/data/fp/ger40_m1.parquet) is read with the pyarrow row filter "
                  "ts < 2022-01-01 00:00 UTC before anything else; that slice is passed explicitly to every simulation "
                  "(goldlab.r2.load / evaluate / null_test are never called: they read the whole frame). Trades are "
                  "counted for sessions from 2014-01-01 to 2021-12-31 (the judge's own figures and the correlation window "
                  "are 2014-2021; noise30 itself starts 2014-01-01; the 2013 data are sparse, results/r2/idx_eu/report.txt "
                  "s.1). The sessions of 2013-09-30 .. 2013-12-31 only warm up sigma (noise30's MIN_DATE logic).",
    "R02_clock": "Europe/Berlin wall clock, DST from the tz database (pandas tz_localize / tz_convert per date).",
    "R03_sessions": "Xetra sessions = weekdays that are not Xetra holidays. Holidays: the Deutsche Boerse cash-market "
                    "calendar of the `holidays` package 0.108 (financial calendar XETR, 2016-2021: 1 Jan, Good Friday, "
                    "Easter Monday, 1 May, Whit Monday and 3 October (holidays up to 2021 in that calendar), 24, 25, 26 "
                    "and 31 December, and 2017-10-31), and the same rules for 2013-2015 (the package starts in 2016). "
                    "Checked before this file: on these days the CFD frame has either no quote or thin, futures-like "
                    "quotes, consistent with a closed Xetra.",
    "R04_early_close": "'Full trading days' only. The CFD frame cannot show whether Xetra closed at 14:00 on the last "
                       "trading day of a year (it keeps quoting after 14:00). Conservative reading: the last session of "
                       "every calendar year (the last weekday before 31 December that is not a holiday) is treated as an "
                       "early close: it is not a full trading day, so it is neither traded nor a session of the grid "
                       "(not in any sigma window, never a PC source).",
    "R05_skipped_days": "Not traded (but kept as sessions for sigma, and as PC source): 24 and 31 December (holidays "
                        "anyway); the session after an early close (= the first session of each year, R04); and, because "
                        "the judge lists 24 December beside the early-close rule, the first session after a weekday 24 "
                        "December (conservative reading: as if 24 December were an early close). Also no trade on a "
                        "session without O (R07) or without PC (R07).",
    "R06_prices": "mid = (bid + ask) / 2 of the FP frame. Price at T = mid close of the last M1 bar that STARTED before T "
                  "(normally the bar starting at T-1 min); the check is skipped if that bar started more than 11 minutes "
                  "before T, i.e. its close (= last quote) is more than 10 minutes old (noise30's grid, stale_min 10). The "
                  "decision is executed at the OPEN of the first M1 bar starting at or after T if that bar starts at most "
                  "5 minutes after T (noise30's grid, late_min 5); otherwise the check is skipped.",
    "R07_anchors": "O = mid OPEN of the M1 bar starting exactly at 09:00:00 Berlin (literal reading; noise30's grid "
                   "accepted a first bar starting before 09:32 NY, the stricter literal reading is used: no 09:00 bar -> "
                   "no trade that session). PC = price at 17:30 (mid close of the 17:29 bar, staleness rule R06) of the "
                   "previous session of the grid. PC missing -> no trade that session (noise30's 'O alone' fallback was "
                   "its early-close treatment, which this rule replaces by skipping the day after an early close; no "
                   "undeclared fallback).",
    "R08_sigma": "sigma(T) = mean over the previous L sessions of the grid (today excluded) of |P_d(T)/O_d - 1|, with at "
                 "least max(int(0.7 L), 1) finite values: L=14 -> 9 (as declared), L=11 -> 7, L=17 -> 11 (noise30's code "
                 "rule). Sessions without O or with a stale price at T count as missing values inside the window.",
    "R09_checks": "Checks at T = first, first + step, ... <= 17:00 (noise30's np.arange(first, last + 1, step)); exit "
                  "17:25:00 for every configuration. Main 09:30..17:00 step 30 (16 checks); step 15: 09:30..17:00 (31); "
                  "step 60: 09:30..16:30 (8; 17:00 is not on that grid); first 09:15: 09:15, 09:45 .. 16:45 (16); first "
                  "09:45: 09:45 .. 16:45 (15). A check whose execution bar is at or after the 17:25 exit bar is skipped.",
    "R10_state_machine": "Identical to the frozen noise30 code (r2/tracks/idx_us/strategy.py::_noise), copied with the "
                         "Berlin grid: UB = max(O, PC) (1 + vm sigma), LB = min(O, PC) (1 - vm sigma). At a check: if "
                         "the state is long and P < UB, or short and P > LB: close at the open of the decision bar, state "
                         "flat; then if flat and P > UB: buy, stop max(O, PC); if P < LB: sell, stop min(O, PC); an entry "
                         "at the same check as an exit goes one bar later (noise30). After a stop the state stays long or "
                         "short (no new entry) until a check passes the exit test. Everything closed at 17:25:00 (open of "
                         "the first bar starting at or after 17:25; goldlab.exit_index closure rule). One position at most "
                         "(simulate no_overlap=True).",
    "R11_costs": "goldlab.sim.simulate on the in-sample slice with goldlab.r2.costs('ger40'): spread inside the FP frame "
                 "(1.6 pt at 25,820 = 0.62 bp with Dukascopy's intraday shape), market fills (entries, check exits, the "
                 "17:25 exit) 0.2 bp per side, stop fills 0.5 bp, swap charged by the simulator per 17:00 New York "
                 "rollover crossed (none expected: flat by 17:25 Berlin; checked). Config 10: spread and slippage x1.5, "
                 "orders rebuilt on the widened quotes (goldlab.r2.run 'stress' logic: apply_spread_mult(1.5) + "
                 "r2.costs('ger40', 1.5)).",
    "R12_three_spreads": "Broker rule: a trade whose initial stop is closer to its fill than 3 spreads (ask open - bid "
                         "open of its fill bar, on the frame of the run) is refused, as is a trade whose stop is already "
                         "crossed at the fill: its order is removed and the configuration re-simulated until no taken "
                         "trade violates it (convention of the breadth lens, r2/tracks/autopsy/breadth/common.py). Applied "
                         "in fp and x1.5 runs, not in the gross run. Count reported.",
    "R13_R": "1 R = |fill - initial stop| (simulator). PF, t, expectancy on per-trade R (goldlab.metrics.report).",
    "R14_every_signal": "Every-signal expectancy: the same (filtered) orders simulated with no_overlap=False. The state "
                        "machine never emits an order while its own previous order is open, so it should equal the main "
                        "run; computed anyway (part of config 1's line).",
    "R15_gross": "Gross run of config 1 (bid = ask = mid, no slippage, no swap; goldlab.r2 'gross' logic): information "
                 "only, stored in config 1's line as goldlab.r2.evaluate does; not a configuration and judges nothing.",
    "R16_null": "Config 11: the algorithm of goldlab.r2.null_test, mode 'day', 200 replays, seed 0, re-implemented on the "
                "in-sample slice with the Berlin minute of day: every taken trade of config 1 (FP costs, entries "
                "2014-2021) is re-entered AT MARKET at a random bar with the same Berlin minute of day, drawn among all "
                "bars of the slice (frame start 2013-09-30 .. 2021-12-31, as the lab's _minute_groups), with the same "
                "side, the same stop distance relative to price (scaled at the random entry's mid) and the same "
                "time-exit delay in bars (planned exit of the order: its check exit or 17:25), one position at a time, "
                "FP costs, no 3-spread filter (the lab's null has none), entries kept if before 2022-01-01. Pass: the "
                "rule's mean R above the 97.5th percentile of the 200 replay means (share of replays strictly below "
                ">= 0.975).",
    "R17_correlation": "Extra condition: weekly sums of R by calendar week of the EXIT (pandas W = Monday-Sunday, UTC), "
                       "every week from the week of 2014-01-01 to the week of 2021-12-31 counted (empty weeks = 0), "
                       "Pearson correlation of config 1 (FP costs) with the sum of the ten official sleeves "
                       "(results/r2/recalc/trades/<name>__<sym>.parquet read with the filters entry_time < 2022-01-01 "
                       "AND exit_time < 2022-01-01 in the same statement). Conservative reading of 'at most 0.30': "
                       "|rho| <= 0.30. Also reported (not judged): each cluster (us100 = noise30 + ocm4; gold = "
                       "GOLD_FRI_PM + donch4h_stop + orb_asia_2d_buf10; crypto = brk72_24h_wd btc + eth, "
                       "F1_brk_ridge_filter btc + eth, nq_btc_follow) and each sleeve.",
    "R18_years": "Years = calendar years of the entry, 2014..2021 (8 years); >= 60 % positive means at least 5 of 8 "
                 "(goldlab.r2.is_criteria: yp >= 0.6 yn).",
    "R19_reported_not_judged": "long and short R; R by year; R of entries whose move since the previous 17:30 close has "
                               "|z| >= 1.5 against the rest, z = (P(T)/PC - 1) / sd, sd = sample standard deviation "
                               "(ddof 1) of (P(T)/PC - 1) at the same check time over the previous 20 sessions that "
                               "have a value (20 required; idx_eu strategy._mom, trial 10's definition), entries with "
                               "no z counted apart; the result on days when noise30 on us100 was flat (no official "
                               "noise30 trade entered on that New York date; official file read as in R17); counts of "
                               "trades on the first session after Whit Monday / 3 October / 2017-10-31 (calendar "
                               "check). Information only.",
    "R20_causality": "Truncation test on at least 50 decisions of config 1 (fixed seed 7): 40 entries and 30 check "
                     "exits drawn among the 2014-2021 decisions; the in-sample slice is cut at the execution bar of the "
                     "decision (every bar starting at or after the check time T removed), 3 provisional bars are "
                     "appended at the real times of the next bars (three variants: flat at the last close, +3 %, -3 %), "
                     "the orders are rebuilt; the decision must be identical in all variants (entry: same entry bar, "
                     "side and stop; check exit: same exit bar of the open order) and the set of orders decided at or "
                     "before T must be identical to the full frame's.",
    "R21_neighbours": "Neighbours = configs 2..9 (FP costs); their median PF must be >= 1.06.",
}

PASS = {
    "n>=250": "config 1 n >= 250 (entries 2014-2021)",
    "pf>=1.12": "config 1 PF on R >= 1.12",
    "t>=2.5": "config 1 t on per-trade R >= 2.5",
    "years_pos>=60%": "config 1: at least 5 of the 8 entry years 2014-2021 with total R > 0",
    "stress_pf>=1.04": "config 10 PF >= 1.04",
    "neighbours_median_pf>=1.06": "median PF of configs 2-9 >= 1.06",
    "every_signal_exp>0": "config 1 every-signal expectancy > 0",
    "max_hold<=5d": "config 1 max hold <= 5 trading days (goldlab.r2.is_criteria: max_hold_h <= 192)",
    "null>=97.5pct": "config 11 percentile >= 97.5",
    "extra_weekly_corr_with_sum_of_ten<=0.30": "|rho| <= 0.30 (R17), 2014-2021",
}


def main():
    raw = open(SRC, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == SHA, sha
    judge = json.loads(raw)["judge"]["ranking"][2]
    assert judge["name"].startswith("ger40_noise30_xetra"), judge["name"]
    for c in CONFIGS:
        c["checks_berlin"] = checks_of(c["params"])
    out = {
        "_written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "_note": "Written BEFORE any run of this rule (no simulation, signal, band, order or trade computed). IN SAMPLE "
                 "ONLY: the frame is read with ts < 2022-01-01; nothing dated 2022 or later is read.",
        "addendum": "PROTOCOL_V3.md Addendum J, rule 3",
        "short_name": "ger40_noise30_xetra",
        "source_file": "results/r2/round4_ideas.json",
        "source_sha256": sha,
        "source_key": "judge.ranking[2]",
        "frozen_name": judge["name"],
        "frozen_rule": judge["rule"],
        "frozen_test_plan": judge["test_plan"],
        "frozen_instruments": judge["instruments"],
        "prior_pass_validation_pct": judge["prior_pass_validation_pct"],
        "configurations": CONFIGS,
        "param_legend": {"lookback": "sessions in the sigma window", "vm": "band multiplier", "step": "minutes between "
                         "checks", "first_min": "Berlin minute of the first check (570 = 09:30)", "last_min": "Berlin "
                         "minute of the last possible check (1020 = 17:00)", "exit_min": "Berlin minute of the time exit "
                         "(1045 = 17:25)"},
        "verdict_on": "configuration 1 only",
        "readings_of_open_details": READINGS,
        "pass_criteria_main": PASS,
        "information_only": ["config 1 gross run (R15)", "R19 break-downs", "correlation with clusters and sleeves"],
        "files": {"code": "r2/tracks/round4/ger40_noise30_xetra/", "results": "results/r2/round4/ger40_noise30_xetra/",
                  "trials": "results/r2/round4/ger40_noise30_xetra/trials.jsonl (one line per configuration, 11 lines)"},
    }
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "declared.json")
    assert not os.path.exists(path), "declared.json already exists: it is written once, before any run"
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print("written", path, out["_written_utc"])


if __name__ == "__main__":
    main()
