"""Writes results/r2/autopsy/breadth/declared.json BEFORE any new pair is simulated.

Every pair of inventory_pairs.csv whose status is "never tried -> PART 2" is one trial; nothing else is run on a new
instrument.  The list, the windows, the costs, the criteria, the ranking rule and the tests are fixed here.
"""
import datetime as dt
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402

import common as C  # noqa: E402


def main():
    inv = pd.read_csv(os.path.join(C.RES, "inventory_pairs.csv"))
    new = inv[inv.status == "never tried -> PART 2"]
    pairs = [{"id": i + 1, "rule": r.rule, "instrument": r.instrument} for i, r in enumerate(new.itertuples())]
    reg = C.registry()
    decl = {
        "written": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "lens": "breadth (PROTOCOL_V3 Addendum H): the frozen rules of the ten sleeves, parameters unchanged, on instruments never tried",
        "status_before_any_new_simulation": "only the ten official sleeves have been simulated (repro.py, first check, all ten reproduced)",
        "budget_trials": len(pairs),
        "pairs": pairs,
        "frozen_rules": {k: {"track": v[0], "params": v[2]} for k, v in reg.items()},
        "rule_notes": {
            "brk72_24h_wd": "with the FP-hours exit wrapper of lab/r2/recalc.py (a time exit inside a closure is done on the last bar before it), as recalculated and as the fx track transferred it",
            "nq_btc_follow": "leader us100 (in-sample slice registered with set_leader before every call); the instrument is the follower",
            "GOLD_FRI_PM": "finalist_params('GOLD_FRI_PM', ...) has no per-symbol variant: same dict on every instrument",
            "F1_brk_ridge_filter": "frozen scorecard models/B1_ridge_full.json['frozen'] (trained on us100+ger40+xauusd+btcusd in-sample candidates); not refitted",
        },
        "data": "in-sample slices only: price frames read with a filter ts < 2022-01-01 (last bar 2021-12-31 23:59 UTC at most); each rule is run on the whole in-sample slice of its instrument (warm-up), from the frame start",
        "jp225_frame": "built in memory from lab/data/raw_jp (2013-2021 CSVs only) with the prep_round2 cleaning and the build_fp_frames cost construction",
        "costs": {
            "fp": "goldlab.r2.costs(sym) on the FP frame (fp_costs.json); jp225 and shares: declared rows in common.py (JP225_SPEC: 12 points at 50,000 = 2.4 bp, slip 0.5/0.2 bp, swap long 5.5 %; STOCK_SPEC of the stocks track)",
            "stress": "spread and slippage x1.5, orders rebuilt on the widened quotes (goldlab.r2.run mode 'stress' logic)",
            "gross": "bid = ask = mid, no slippage, no swap (information only)",
            "broker_min_stop": "a trade whose initial stop is closer than 3 spreads of its fill bar (or already crossed at the fill) is not taken: its order is removed and the sleeve re-simulated; applied in fp and stress (not in gross); the count is reported",
        },
        "judging_window": "trades entered 2018-02-01 .. 2021-12-31 (the common in-sample window of the ten sleeves); earlier in-sample years are reported separately and judge nothing",
        "criterion_breadth": "PF >= 1.15 (net of FP costs, window above), total R positive in at least 3 of the 4 calendar years 2018-2021, total R positive with costs x1.5, parameters unchanged",
        "reported_for_every_pair": ["n, trades per year, win rate, average win and loss in R, expectancy, t, PF, total R, max drawdown in R, long/short R, years",
                                    "the same with costs x1.5 and gross", "the earlier in-sample years separately", "trades refused by the 3-spread rule",
                                    "weekly R correlation (calendar week of the exit, every week of the window, empty weeks = 0) with each of the ten official sleeves (rows entry < 2022) and with their sum",
                                    "PROTOCOL_V2 sleeve bars for information (n >= 250, PF >= 1.12, t >= 2.5, >= 60 % years, stress PF >= 1.04)"],
        "ranking_of_qualifiers": "by the change of the annualised Sharpe ratio of the weekly sum of R of the ten sleeves when the pair is added at the same risk per trade (window above); ties by the extra total R per year; the correlation with the sum and the extra R per year are shown beside it",
        "tests_for_qualifiers": ["truncation test: for up to 40 trades (fixed seed) the frame is cut right after the decision bar (stop-entry rules: right after the touch bar), 3 flat provisional bars are appended, the orders are rebuilt and the order of the trade must be identical (entry time, side, stop or stop distance, level)",
                                 "random-entry null (PROTOCOL_V2 mode 'day', information only): the same trades re-entered at market on a random day at the same New-York time with the same side, stop and holding time, 200 draws, percentile of the rule's mean R"],
        "pooled_readings_information_only": "per rule: FX basket (8 pairs), shares basket (nq_btc_follow), metals, indices -- with the PROTOCOL_V3 basket t on daily sums",
        "multiple_testing": "with this many trials some pairs can pass the loose breadth bar by chance; each qualifier is shown with its t and its null percentile, and the number of passes is compared with the number expected from pairs with no edge",
        "nothing_else": "no parameter, clock, filter, exit or cost variant is run on any new instrument; a pair is run once (fp, stress, gross)",
    }
    C.jdump(decl, os.path.join(C.RES, "declared.json"))
    print(len(pairs), "pairs declared")
    print(new.groupby("rule").size().to_dict())


if __name__ == "__main__":
    main()
