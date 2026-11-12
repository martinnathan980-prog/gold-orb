"""Addendum H, lens `entry` -- the declaration, written BEFORE any part-1 number was computed and BEFORE any variant
was simulated (only the baseline reproduction, s0_baseline.py, had been run).  Writes
results/r2/autopsy/entry/declared.json.  The window lengths N come from each rule's own clock (its decision step or
planned life), not from data.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ORDER, RES, jdump, key  # noqa: E402

MKT_N = {"noise30:us100": 15, "ocm4:us100": 30, "brk72_24h_wd:btcusd": 60, "brk72_24h_wd:ethusd": 60,
         "F1_brk_ridge_filter:btcusd": 60, "F1_brk_ridge_filter:ethusd": 60, "nq_btc_follow:btcusd": 10}
N_WHY = {
    "noise30:us100": "half the rule's 30-minute decision step (its first possible band exit is the next check)",
    "ocm4:us100": "the first half hour of a trade that lives from 09:34 to 15:55 New York",
    "brk72_24h_wd:btcusd": "one decision step of the hourly rule (the trade lives 24 h)",
    "brk72_24h_wd:ethusd": "one decision step of the hourly rule (the trade lives 24 h)",
    "F1_brk_ridge_filter:btcusd": "one decision step of the hourly rule (the trade lives to 15:55 New York)",
    "F1_brk_ridge_filter:ethusd": "one decision step of the hourly rule (the trade lives to 15:55 New York)",
    "nq_btc_follow:btcusd": "a sixth of the 60-minute trade: the follow-through the rule trades happens in minutes",
    "GOLD_FRI_PM:xauusd": "the rule's own limit window (bars starting 13:30 to 14:29 New York), frozen",
    "donch4h_stop:xauusd": "retest windows of 1 h, 4 h (the rule's 4-hour decision step) and 12 h (half the median hold)",
    "orb_asia_2d_buf10:xauusd": "retest windows of 30 min, 2 h and 5 h (5 h = the length of the rule's 07:00-12:00 "
                                "London entry window)",
}
RT_N = {"donch4h_stop:xauusd": (60, 240, 720), "orb_asia_2d_buf10:xauusd": (30, 120, 300)}


def market_variants(N):
    return [
        {"id": "LIM10_skip", "family": "LIM", "k": 0.10, "N_min": N, "fallback": "skip"},
        {"id": "LIM25_skip", "family": "LIM", "k": 0.25, "N_min": N, "fallback": "skip"},
        {"id": "LIM10_mkt", "family": "LIM", "k": 0.10, "N_min": N, "fallback": "market"},
        {"id": "CONF1", "family": "CONF", "tf_min": 1, "N_min": N},
        {"id": "CONF5", "family": "CONF", "tf_min": 5, "N_min": N},
        {"id": "HALF25", "family": "HALF", "k": 0.25, "N_min": N, "w_pullback_leg": 0.5},
    ]


MARKET_NEIGHBOURS = {"LIM10_skip": ["LIM25_skip", "LIM10_mkt"], "LIM25_skip": ["LIM10_skip", "HALF25"],
                     "LIM10_mkt": ["LIM10_skip"], "CONF1": ["CONF5"], "CONF5": ["CONF1"],
                     "HALF25": ["LIM25_skip"]}


def retest_variants(Ns):
    a, b, c = Ns
    return [
        {"id": f"RT{a}_skip", "family": "RT", "N_min": a, "fallback": "skip"},
        {"id": f"RT{b}_skip", "family": "RT", "N_min": b, "fallback": "skip"},
        {"id": f"RT{c}_skip", "family": "RT", "N_min": c, "fallback": "skip"},
        {"id": f"RT{a}_mkt", "family": "RT", "N_min": a, "fallback": "market"},
        {"id": f"RT{b}_mkt", "family": "RT", "N_min": b, "fallback": "market"},
        {"id": f"HALFRT{b}", "family": "HALFRT", "N_min": b, "w_pullback_leg": 0.5},
    ]


def retest_neighbours(Ns):
    a, b, c = Ns
    return {f"RT{a}_skip": [f"RT{b}_skip", f"RT{a}_mkt"], f"RT{b}_skip": [f"RT{a}_skip", f"RT{c}_skip", f"RT{b}_mkt",
                                                                          f"HALFRT{b}"],
            f"RT{c}_skip": [f"RT{b}_skip"], f"RT{a}_mkt": [f"RT{b}_mkt", f"RT{a}_skip"],
            f"RT{b}_mkt": [f"RT{a}_mkt", f"RT{b}_skip"], f"HALFRT{b}": [f"RT{b}_skip"]}


def main():
    sleeves = {}
    for name, sym in ORDER:
        k = key(name, sym)
        if k in RT_N:
            sleeves[k] = {"kind": "stop-entry rule (buffers frozen): retest of the broken level only",
                          "N_why": N_WHY[k], "variants": retest_variants(RT_N[k]),
                          "neighbours": retest_neighbours(RT_N[k])}
        elif name == "GOLD_FRI_PM":
            sleeves[k] = {"kind": "limit-entry rule: the generic families, measured from the rule's own limit level L0",
                          "N_why": N_WHY[k], "variants": market_variants("rule window (60)"),
                          "neighbours": MARKET_NEIGHBOURS}
        else:
            sleeves[k] = {"kind": "market-entry rule", "N_why": N_WHY[k], "variants": market_variants(MKT_N[k]),
                          "neighbours": MARKET_NEIGHBOURS}
        for v in sleeves[k]["variants"]:
            v["stop_modes"] = ["price", "dist"]
    decl = {
        "written_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protocol": "PROTOCOL_V3.md Addendum H, lens entry (getting in better); in sample only",
        "status_when_written": "the ten official in-sample trade lists had been reproduced exactly (baseline.json: same "
                               "trades, R identical except the one trade of donch4h_stop and of orb_asia_2d_buf10 that "
                               "straddles the cut); no part-1 number had been computed and no variant simulated",
        "budget": "at most 12 per sleeve: 6 entry variants per sleeve x the 2 stop placements the protocol requires = "
                  "12 simulated cells per sleeve, 120 in all; each cell is one line of trials.jsonl (FP and x1.5 "
                  "results in the same line)",
        "data": {
            "frames": "lab/data/fp/<sym>_m1.parquet read with the row filter ts < 2022-01-01 00:00 UTC; that slice is "
                      "passed to every rule and every simulation",
            "trades": "results/r2/recalc/trades/<name>__<sym>.parquet read with entry_time < 2022-01-01 (baseline check "
                      "only)",
            "leader": "nq_btc_follow: the in-sample us100 slice registered with set_leader before each make_orders",
        },
        "windows": {"common": "entries 2018-02-01 .. 2021-12-31: every candidate criterion",
                    "pre": "entries before 2018-02-01: reported separately, not a criterion",
                    "years": "2018 (Feb-Dec), 2019, 2020, 2021 by entry date (first fill)",
                    "censored": "a trade still open at the end of the in-sample frame (exit on its last bar) is left "
                                "out of every statistic, baseline and variants alike"},
        "costs": {"fp": "r2.costs(sym) on the stored FP frame",
                  "x1.5": "spread x1.5 around the mid (apply_spread_mult) and r2.costs(sym, 1.5); the rule's orders "
                          "AND the variant's levels are rebuilt on the widened quotes (as r2.run mode 'stress')"},
        "engine": "every leg is one order of the lab simulator (goldlab.sim.simulate), simulated alone (no_overlap=False) "
                  "with the lab's fill, stop, time-exit, slippage and swap rules; the one-position rule is applied on the "
                  "signals' activation bars (the rule's entry_i) exactly as the engine does (skip when activation <= exit "
                  "bar of the previous trade); a signal with a pending order or a confirmation wait keeps the sleeve "
                  "busy until its window ends or it is cancelled (live-implementable; with the original orders the path "
                  "reproduces simulate(no_overlap=True) exactly, baseline.json)",
        "broker_min_stop": "a leg whose initial stop distance (the stop actually used) is under 3 x the spread (ask - bid) "
                           "of its fill bar, in the run's own frame, is not taken (it does not block the sleeve); the "
                           "count is reported per cell",
        "definitions": {
            "P0": "the rule's own fill price: market rules = ask open of the entry bar x (1 + market slippage) for a "
                  "long, bid open x (1 - market slippage) for a short; stop-entry rules = the lab's stop fill at the touch "
                  "(worse of level and open, x (1 +/- stop slippage)); GOLD_FRI_PM uses its limit level L0 as reference",
            "D": "the rule's stop distance: stop_dist where the rule gives one, else |P0 - rule's absolute stop| "
                 "(noise30: band centre; orb: opposite level)",
            "S0": "the rule's stop PRICE = P0 - side x D (= the rule's absolute stop for noise30 and orb; L0 - D for "
                  "GOLD_FRI_PM)",
            "stop_modes": {"price": "the new entry keeps the stop at S0: a better entry risks less per unit (larger "
                                    "position, same money risk); R = pnl / |fill - S0|",
                           "dist": "the new entry keeps the rule's distance: stop = fill - side x D; R = pnl / D"},
            "unchanged": "side, time exit (exit_i), signal exits (noise30 band checks), trailing (donch4h_stop: 2 ATR), "
                         "the rule's signals and parameters",
            "window": "a pending order or a confirmation wait placed at the open of bar a (market rules: the rule's entry "
                      "bar) covers the bars that START in [start(a), start(a) + N minutes) and before the rule's exit bar",
            "LIM": "buy limit at P0 - k x D (sell limit at P0 + k x D) placed at the open of the rule's entry bar, valid "
                   "N minutes (lab limit fill: ask low <= level for a buy, at min(level, ask open); bid high >= level "
                   "for a sell, at max(level, bid open); no slippage); fallback 'skip': no trade if unfilled; fallback "
                   "'market': if unfilled, market entry at the open of the first bar that starts at or after "
                   "start(a) + N minutes (if before the exit bar)",
            "CONF": "no entry at the signal; wait for the first bar of tf minutes (tf = 1: one M1 bar; tf = 5: blocks of "
                    "5 minutes aligned on the signal, [start(a) + 5j, start(a) + 5j + 5)) whose MID close is beyond its "
                    "MID open in the trade's direction, inside the N-minute window; enter at market at the open of the "
                    "next bar (the first bar starting at or after the block's end); cancelled if the rule's stop price "
                    "S0 is touched first (long: bid low <= S0, short: ask high >= S0) or if no such bar comes in the "
                    "window",
            "HALF": "half of the money risk at the signal (the rule's own order, unchanged), half by limit at "
                    "P0 -/+ k x D valid N minutes (no fallback); R of the signal = 0.5 x R(rule leg) + 0.5 x R(pullback "
                    "leg) (each leg in its own risk units), 0.5 x R(rule leg) when the pullback leg is not filled",
            "RT": "donch4h_stop and orb_asia_2d_buf10 only: the rule's breakout trigger is unchanged (its frozen level "
                  "and buffer); instead of buying the touch, a limit order at the broken level itself (the rule's entry "
                  "level) is placed from the bar after the touch bar, valid N minutes (and before the rule's exit "
                  "bar); fallback 'skip' or 'market' (market at the open of the first bar at or after the window's "
                  "end); stop S0 = P0 -/+ D from the rule's own touch fill (orb: the opposite level) or D from the "
                  "retest fill; donch keeps its 2-ATR trailing",
            "HALFRT": "half at the touch (the rule's own order), half on the retest (RT leg, no fallback)",
            "GOLD_FRI_PM": "LIM levels are L0 - k x D (L0 = the rule's limit, the last bid before 13:30 NY); the window is "
                           "the rule's own (to its expiry bar); LIM10_mkt falls back to market at the first bar at or "
                           "after 14:30 NY; CONF waits from the 13:30 bar inside the same window; HALF = half the rule's "
                           "own limit at L0, half the limit at L0 - 0.25 D",
            "neighbours": "one-step neighbours inside the declared grid of the same sleeve and the same stop mode: k "
                          "(0.10 <-> 0.25), fallback (skip <-> market), confirmation size (1 <-> 5 minutes), weight of the "
                          "pullback leg (HALF 0.5 <-> LIM 1.0 at the same k), retest window (adjacent N)",
        },
        "candidate_criteria": {
            "a": "common window, FP costs, against the baseline: expectancy per trade >= baseline + 0.20 x |baseline| "
                 "(route E; where the baseline expectancy is <= 0 the variant's must also be > 0), OR mean R of the "
                 "losing trades at most 0.8 x the baseline's in size with an expectancy at least equal (route L)",
            "b": "total R on the common window, FP costs, not lower than the baseline's",
            "c": "route E: expectancy above the baseline's in at least 3 of the 4 years 2018-2021; route L: |average loss| "
                 "below the baseline's in at least 3 of the 4 years",
            "d": "with costs x1.5 the same route's (a) and (b) hold against the baseline with costs x1.5",
            "e": "every declared neighbour (same stop mode) improves on the baseline in the same direction (route E: "
                 "higher expectancy and total R not lower; route L: smaller |average loss| and expectancy not lower), FP, "
                 "common window",
            "f": "causal: truncation test -- for every signal, each entry decision (limit level, fill bar, fallback, "
                 "confirmation bar, cancellation) recomputed on the price arrays cut right after its decision bar is "
                 "identical; the rule layer (side, stop) is checked on frames cut after the decision bar with "
                 "provisional bars, on a sample of signals",
            "rank": "if several cells of a sleeve qualify: larger common-window FP total-R gain first, then larger x1.5 "
                    "gain; at most one change per sleeve is carried forward",
        },
        "reported_for_every_cell": "share of the signals taken by the chain that are filled; mean R of the filled "
                                   "signals (variant) and, for filled and for missed signals, the R the rule's own "
                                   "entry would have made on them (each signal's original order simulated alone); total "
                                   "R of the sleeve against the baseline; refusals by the 3-spread rule",
        "not_trials": "the baseline runs (fp, x1.5), the part-1 descriptive measures (price path, come-backs, the "
                      "per-trade counterfactual of entering 1, 2 or 5 minutes late on the official trades with the "
                      "set of trades held fixed, first minutes against outcome) and the causality checks are not "
                      "variants; the late-entry counterfactual runs are logged in trials.jsonl with part='part1' and "
                      "counted apart",
        "part1_late_entry": "each official trade re-run alone with a market entry at the open of the first bar starting "
                            "at or after its fill time + d minutes (d = 1, 2, 5), exits unchanged; stop at S0 (void when "
                            "S0 was touched before the late entry or the late price is beyond it) or at D from the late "
                            "fill; the set of trades is held fixed (no chain): a description of what lateness costs, "
                            "not a variant",
        "sleeves": sleeves,
    }
    n = sum(len(s["variants"]) * 2 for s in sleeves.values())
    decl["n_cells"] = n
    assert n == 120
    jdump(decl, os.path.join(RES, "declared.json"))
    print("declared", n, "cells ->", os.path.join(RES, "declared.json"))


if __name__ == "__main__":
    main()
