"""Round 4 (PROTOCOL_V3 Addendum J), rule 5: LETF_CLOSE_PAIR.  Writes results/r2/round4/letf_close_pair/declared.json
BEFORE any run and before any price frame is read: the judge's frozen `rule` and `test_plan` texts (copied verbatim
from results/r2/round4_ideas.json, judge.ranking[4], whose sha256 is checked against Addendum J), the 11 declared
configurations as parameters, and the readings chosen where the text leaves a detail open (the most conservative or
most literal one each time, said so).

    PYTHONDONTWRITEBYTECODE=1 python3 declare.py
"""
import datetime as dt
import hashlib
import json
import os

LAB = "/home/user/gold-orb/lab"
SRC = os.path.join(LAB, "results", "r2", "round4_ideas.json")
OUT = os.path.join(LAB, "results", "r2", "round4", "letf_close_pair")
SHA_ADDENDUM_J = "c81387985baf8e43d64caa339c75daf4d3ff936a925ef28d97ff94755b5e225a"

# minutes of day, New York.  sig_min: the decision instant (d is read on the close of the bar that starts one minute
# earlier); entry_min / exit_min: the bars at whose OPEN the legs are filled / closed; hed_e / hed_x: the bars whose
# mid OPENS bound the "15:30->15:59" returns of the hedge ratio and of sd_pi.
MAIN = dict(sig_min=930, entry_min=930, exit_min=959, hed_e=930, hed_x=959, thr=1.25, k=1.5, leg2="us30",
            win=60, minv=40, cost_mult=1.0)


def cfg(cid, name, role, **over):
    c = dict(MAIN)
    c.update(over)
    return {"id": cid, "name": name, "role": role, "params": c}


CONFIGS = [
    cfg(1, "main", "verdict"),
    cfg(2, "n_thr_1.0", "neighbour", thr=1.0),
    cfg(3, "n_thr_1.5", "neighbour", thr=1.5),
    cfg(4, "n_entry_1540", "neighbour", entry_min=940),
    cfg(5, "n_exit_1557", "neighbour (exit; knife-edge condition)", exit_min=957),
    cfg(6, "n_exit_1605", "neighbour (exit; knife-edge condition; dropped before the run only under R19)", exit_min=965),
    cfg(7, "n_stop_1.25", "neighbour", k=1.25),
    cfg(8, "n_stop_1.75", "neighbour", k=1.75),
    cfg(9, "n_us100_us500", "neighbour", leg2="us500"),
    cfg(10, "stress_x1.5", "cost stress", cost_mult=1.5),
    {"id": 11, "name": "null_200", "role": "random-entry null",
     "params": dict(MAIN, n_seeds=200, seed=0, of="main")},
]

READINGS = {
    "R1_period_and_sessions": (
        "In sample only: every price frame is read with the parquet row filter ts < 2022-01-01 and the slices are passed "
        "explicitly to every function; nothing dated 2022 or later is read. Sessions = NYSE full sessions from the "
        "rule-based calendar already used by noise30 / ocm4 / IDXRS_1000 (r2/tracks/idx_us/idxus_lib.calendar_flags, "
        "imported read-only): weekdays that are neither a full closure nor a 13:00 early close. Early-close days are not "
        "sessions (not traded, not counted in any look-back window). The session list runs from 2013-09-30 (first day of "
        "the us30 frame) to 2021-12-31 and is the SAME list for every configuration, (9) us100/us500 included, so that (9) "
        "differs from the main by the instrument only. Trades are counted from the first one the warm-up allows."),
    "R2_bars": (
        "'the 15:29 bar', 'the 15:30 bar', 'the 15:59 bar' = the M1 bar that STARTS at that New York minute (bars are "
        "labelled by their start; DST handled by the tz database). The decision at 15:30 uses the close of the 15:29 bar, "
        "known at 15:30. Mid = (bid + ask) / 2. Every bar the signal names must exist exactly (no forward fill): if the "
        "15:29 bar of the day or the 15:59 bar of the previous session is missing for an index, its d is missing that day "
        "(no trade, no value in the look-back windows)."),
    "R3_previous_session": (
        "'the previous session' = the previous NYSE trading day (weekday that is not a full closure). When that day was a "
        "13:00 early close it has no 15:59 cash-session bar: d is then missing for both indices and the day is not traded "
        "(and gives no value to the sd_d and sd_pi windows). This is the conservative reading, and the one of the lab's "
        "frozen noise30, which ignores the previous close after an early close. After a full closure (holiday, weekend) "
        "the previous session is the last trading day before it."),
    "R4_signal_condition": (
        "d_i = ln(mid close of the day's 15:29 bar / mid close of the previous session's 15:59 bar), i = us100 and leg 2 "
        "(us30; us500 in (9)). Condition: d_us100 and d_leg2 both strictly positive or both strictly negative (a zero "
        "has no sign: no trade), and |d_us100| >= thr x sd_d (thr = 1.25; 1.0 / 1.5 in (2) / (3)). 'd > 0' / 'd < 0' "
        "in the entry text = that common sign; direction dir = sign(d_us100)."),
    "R5_sd_d": (
        "sd_d = sample standard deviation (ddof = 1) of d_us100 over the finite values among the previous 60 sessions "
        "(the current session excluded), at least 40 values. The text gives no minimum; 40 of 60 is the minimum the "
        "sister rule IDXRS_1000 states for its 60-session windows (this rule reuses its pair mark and stop)."),
    "R6_hedge": (
        "h = sd_us100 / sd_leg2, sd = sample sd (ddof = 1) of each index's log return from the mid OPEN of the 15:30 bar "
        "to the mid OPEN of the 15:59 bar (the main's holding period, as the rule writes '15:30->15:59'), each over its "
        "own finite values among the previous 60 sessions, at least 40; a day's return is missing if either bar is "
        "missing. N on us100, h x N on leg 2. The windows stay at 15:30->15:59 in EVERY configuration (no neighbour names "
        "them: a neighbour changes only what it names)."),
    "R7_sd_pi": (
        "For every previous session j (traded or not) with a defined direction dir_j = sign(d_us100,j): pi_j = dir_j x "
        "(r_us100,j - h_j x r_leg2,j), with the mid 15:30-open -> 15:59-open returns of R6 and day j's own h_j (from day "
        "j's own trailing windows). sd_pi = sample sd (ddof = 1) of pi over the finite values among the previous 60 "
        "sessions, at least 40. A day trades only if the condition of R4 holds and h > 0 and sd_pi > 0 are defined."),
    "R8_entry": (
        "Both legs need an M1 bar starting exactly at the entry minute (15:30; 15:40 in (4)); otherwise the signal is not "
        "entered ('if one leg fails'). Fills at the open: the long leg at ask x (1 + 0.2 bp), the short leg at bid x "
        "(1 - 0.2 bp), same minute; d > 0: long us100 (N) and short leg 2 (h x N); d < 0: short us100 (N) and long leg 2 "
        "(h x N). In (4) the SIGNAL stays at 15:30 (15:29 bar) and the windows at 15:30->15:59: only the entry minute "
        "moves, because the neighbour names only the entry (in IDXRS_1000 the judge wrote 'ranking and entry' where he "
        "meant both). One pair a day."),
    "R9_stop_monitoring": (
        "Pair mark as in IDXRS_1000: pi = dir x [ln(P_us100 / P_us100,fill) - h x ln(P_leg2 / P_leg2,fill)] at exit-side "
        "prices (a long leg at its bid, a short leg at its ask). Hard rule 3: pi is marked on the close of every M1 bar "
        "from the entry bar to the bar before the exit bar (a leg without a bar in that minute keeps its last close). If "
        "pi <= -k x sd_pi, both legs are closed at the open of the next bar (for each leg its first bar at or after the "
        "next minute): long leg at bid x (1 - 0.5 bp), short leg at ask x (1 + 0.5 bp). A stop decided on the close of the "
        "bar before the exit bar is executed at the exit bar's open and pays the stop slippage. No intrabar trigger is "
        "assumed (an M1 frame cannot order the two legs' extremes)."),
    "R10_time_exit": (
        "Both legs at the open of the first bar at or after the exit minute (15:59; 15:57 in (5); 16:05 in (6)): long leg "
        "at bid x (1 - 0.2 bp), short leg at ask x (1 + 0.2 bp). A leg with no bar from that minute to 16:59 New York is "
        "closed at its last close (counted and reported). No position crosses the 17:00 New York rollover: no swap."),
    "R11_R_unit": (
        "net pi = the pair mark at the actual fill and exit prices (spread and slippage inside them), log returns as the "
        "rule writes pi; R = net pi / (k x sd_pi), k = 1.5 in the main ('R = net pi / (1.5 x sd_pi)'), 1.25 / 1.75 in "
        "(7) / (8) (R per unit of the initial pair risk, as goldlab defines R; a constant k changes neither PF nor t). The "
        "money result with simple returns (N x (P/P_fill - 1) per leg, signed, leg 2 weighted by h) is reported beside "
        "it, not judged."),
    "R12_stop_floor": (
        "Hard rule 4: a pair is refused if k x sd_pi < 3 x (spread_us100 + h x spread_leg2), spreads = quoted (ask - bid) "
        "/ mid at the open of the entry bar, on the frame of the run (widened in the stress run)."),
    "R13_costs_and_stress": (
        "FP costs: spreads inside the FP frames (lab/data/fp; r2/fp_costs.json: 0.37 / 0.35 / 0.54 bp for us100 / us30 / "
        "us500 at the reference price, Dukascopy intraday shape), market slippage 0.2 bp per side per leg, stop slippage "
        "0.5 bp per leg (= r2.costs(sym), identical for the three indices; the judge's '+0.6 bp on stop fills' is the "
        "0.3 bp extra per leg on the two legs), no swap. Configuration 10: each leg's frame widened with "
        "goldlab.sim.apply_spread_mult(frame, 1.5) (mid unchanged, so the signals are unchanged) and both slippages x1.5 "
        "(0.3 bp market, 0.75 bp stop)."),
    "R14_every_signal": (
        "One pair a day, intraday: no signal can be skipped for an open position, so the every-signal run IS the main run "
        "(signals refused by R12 or not filled by R8 are counted and reported)."),
    "R15_null": (
        "Configuration 11: each filled pair of the main is replayed with the same legs (us100 / us30), the same direction "
        "(sides), the same hedge ratio h, the same stop level -1.5 x sd_pi and R unit 1.5 x sd_pi of the original trade, "
        "entry at the open of the 15:30 bar and time exit at the open of the 15:59 bar (the main's holding time), FP "
        "costs, the same fill and stop rules, on a session drawn uniformly with replacement among all sessions of the "
        "list (2013-09-30 .. 2021-12-31) on which both legs have a 15:30 bar. The replays are not re-filtered (no "
        "condition, no stop floor). 200 replays, numpy default_rng(0); statistic = mean R; percentile = share of replays "
        "whose mean R is below the main's; pass >= 97.5."),
    "R16_years": "Years positive = calendar years of entry with at least one trade whose summed R > 0; bar >= 60 %.",
    "R17_neighbour_median": (
        "Neighbours = configurations 2-9 (eight); their median PF (median of eight = mean of the 4th and 5th values) "
        "must be >= 1.06. PF everywhere = profit factor on R (goldlab convention), FP costs."),
    "R18_knife_edge": (
        "Extra condition declared by the judge: PF of (5) exit 15:57 >= 1.06 AND PF of (6) exit 16:05 >= 1.06."),
    "R19_drop_rule_of_6": (
        "(6) is run unless the frames have (essentially) no quotes after 16:00 New York: data_check.py counts, on the "
        "sessions of the list, the days on which us100 and us30 BOTH have an M1 bar starting in [16:00, 16:10) New York; "
        "(6) is dropped (and logged as dropped in trials.jsonl) only if that share is below 50 %. If dropped, the "
        "neighbour median is taken over seven and the knife-edge condition is read on (5) alone, said so in the verdict."),
    "R20_weekly_correlation_reported": (
        "Weekly sums of R booked at the exit week (pandas weekly periods W-SUN of the UTC exit time, as goldlab.metrics), "
        "every calendar week from the week of 2014-01-01 to the week of 2021-12-31 counted (weeks without a trade = 0), "
        "Pearson. IDXRS_1000 = its main configuration's in-sample trades (results/r2/round4/idxrs_1000/"
        "trades_01_main.parquet, read with the filter entry_time < 2022-01-01); noise30 and the rest of the ten = their "
        "official trades (results/r2/recalc/trades, read with the filter entry_time < 2022-01-01 in the same statement; a "
        "trade exiting in 2022 dropped). Reported, not judged: with IDXRS_1000, with noise30, with the sum of the ten and "
        "with each of the three clusters."),
    "R21_split_by_direction_reported": (
        "The main's trades split by the day's direction: d > 0 (long us100 / short us30) and d < 0 (short us100 / long "
        "us30): n, expectancy, PF, total R, t, net bp. Also by year."),
    "R22_gross_reported": (
        "Gross: the same signals simulated on mid prices without slippage (mode 'mid'): gross bp per pair and gross PF, "
        "reported not judged; cost per pair = mid result at the trade's own minutes - net result."),
    "R23_checks_not_trials": (
        "Verification of the main only, not configurations: (a) synthetic unit tests of the two-leg simulator (no market "
        "data); (b) a hand check of 6 days recomputed from the raw in-sample bars with plain loops; (c) a cross-check of "
        "every pair of the main with IDXRS_1000's two-leg simulator (r2/tracks/round4/idxrs_1000/common.sim_pairs, "
        "imported read-only, on its own 09:30-16:00 grid; a short-us100 pair is passed to it as long us30 with weight 1/h "
        "and stop -k sd_pi / h, which is the same pair scaled by 1/h); (d) the truncation test of hard rule 3 on at least "
        "50 decisions (entry decisions on frames cut at 15:30, stop decisions on frames cut at the end of the decision "
        "bar, no-stop checks cut inside the hold)."),
}

CRITERIA = {
    "n>=250": "main n >= 250",
    "pf>=1.12": "main PF on R >= 1.12",
    "t>=2.5": "main t on per-trade R >= 2.5",
    "years_pos>=60%": "share of positive entry years >= 60 % (R16)",
    "stress_pf>=1.04": "configuration 10 PF >= 1.04",
    "neighbours_median_pf>=1.06": "median PF of configurations 2-9 >= 1.06 (R17)",
    "every_signal_exp>0": "every-signal expectancy > 0 (= main, R14)",
    "max_hold<=5d": "hold <= 5 trading days",
    "null>=97.5": "configuration 11 percentile >= 97.5 (R15)",
    "extra_knife_edge_exit_neighbours_pf>=1.06": "PF of (5) >= 1.06 and PF of (6) >= 1.06 (R18, R19)",
}


def main():
    raw = open(SRC, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == SHA_ADDENDUM_J, f"round4_ideas.json changed: {sha}"
    j = json.loads(raw)["judge"]["ranking"][4]
    assert j["name"].startswith("LETF_CLOSE_PAIR")
    out = {
        "_written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "_note": ("Written BEFORE any run of this rule and before any price frame was read by this track (no signal, no "
                  "simulation, no data check had been run). IN SAMPLE ONLY: every frame is read with ts < 2022-01-01; "
                  "nothing dated 2022 or later is read."),
        "addendum": "PROTOCOL_V3.md Addendum J, rule 5",
        "short_name": "letf_close_pair",
        "source_file": "results/r2/round4_ideas.json", "source_sha256": sha, "source_key": "judge.ranking[4]",
        "frozen_name": j["name"],
        "frozen_rule": j["rule"],
        "frozen_test_plan": j["test_plan"],
        "frozen_instruments": j["instruments"],
        "frozen_why": j["why"],
        "prior_pass_validation_pct": j["prior_pass_validation_pct"],
        "configurations": CONFIGS,
        "param_legend": {"sig_min": "New York minute of the decision (d read on the close of the bar starting one minute "
                                    "earlier)",
                         "entry_min": "New York minute of the entry bar (fills at its open)",
                         "exit_min": "New York minute of the exit bar (time exit at its open)",
                         "hed_e / hed_x": "bars whose mid opens bound the returns of the hedge ratio and of sd_pi",
                         "thr": "threshold on |d_us100| in sd_d units", "k": "pair stop in sd_pi units",
                         "leg2": "second leg (us30; us500 in (9))", "win": "look-back sessions",
                         "minv": "minimum finite values in a window", "cost_mult": "spread and slippage multiplier"},
        "verdict_on": "configuration 1 (main) only; 2-9 are its neighbours, 10 its cost stress, 11 its random-entry null",
        "readings_of_open_details": READINGS,
        "pass_criteria_main": CRITERIA,
        "files": {"code": "r2/tracks/round4/letf_close_pair/", "results": "results/r2/round4/letf_close_pair/",
                  "trials": "results/r2/round4/letf_close_pair/trials.jsonl (one line per configuration, 11 lines)"},
    }
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "declared.json")
    assert not os.path.exists(p), "declared.json already exists: never rewritten"
    with open(p, "w") as f:
        json.dump(out, f, indent=1)
    print("written", p, sha)


if __name__ == "__main__":
    main()
