"""Writes results/r2/autopsy/path/declared.json: the variants of part 2, fixed BEFORE any of them is simulated.

Chosen from part 1 (anatomy_rest.csv, anatomy_cut_below.csv, 2018-2021, FP costs).  At most 12 per sleeve.
Refuses to overwrite an existing declaration (the declaration is written once).
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


def ck(s):
    return {"minutes": int(s[:-1])} if s.endswith("m") else {"frac": float(s[:-1]) / 100}


PLAN = {
    # sleeve: (EC checkpoints, EC x, NP checkpoints, NP y, HC checkpoints, why)
    "noise30:us100": (["5m", "15m", "10%"], [0.25, 0.5], ["60m", "120m"], [0.0, 0.25], ["5m", "10%"],
                      "part 1: the only cells where cutting losers paid at first order are 5m state<=-0.5 (+3.0 R, 14 "
                      "trades, 4/4 years) and 10% (about 30 min) state<=-0.25 (+5.4 R, 68 trades, 4/4 years); the only "
                      "no-progress cell that paid is 60m y=0 (+2.3 R). Earlier years (2014-2017) show the opposite sign "
                      "in those cells (-3.0 R, -2.8 R)."),
    "ocm4:us100": (["5m", "15m", "30m"], [0.5, 0.75], ["120m", "50%"], [0.25, 0.5], ["5m", "50%"],
                   "part 1: early-cut cells that paid: 5m state<=-0.5 (+6.3 R, 38 trades, 3/4 years), 30m state<=-0.75 "
                   "(+2.7 R, 15 trades, 4/4); no-progress at 50% of planned life (about 12:45 New York): y=0.25 +11.6 R "
                   "(101 trades), y=0.5 +23.0 R (128 trades, 4/4 years), at 120m y=0.5 +5.3 R. In 2014-2017 the same "
                   "50% cells are negative (-3.1 R, -4.5 R)."),
    "brk72_24h_wd:btcusd": (["10%", "25%", "50%"], [0.25, 0.5], ["25%", "50%"], [0.0, 0.25], ["10%", "50%"],
                            "part 1: early-cut cells that paid: 10% (144 min) state<=-0.25 +6.8 R (114 trades, 3/4), "
                            "50% state<=-0.5 +4.8 R (38 trades, 4/4); 25% state<=-0.5 lost 14.9 R. Every no-progress "
                            "cell lost (tested to document it)."),
    "nq_btc_follow:btcusd": (["5m", "15m", "30m"], [0.5, 0.75], ["15m", "30m"], [0.0, 0.25], ["5m", "15m"],
                             "part 1: early-cut cells that paid: 5m state<=-0.5 +1.7 R (13 trades), 30m state<=-0.75 "
                             "+0.6 R (6 trades); 15m and 30m state<=-0.5 lost 5.6 and 6.8 R; every no-progress cell "
                             "lost 25-60 R (tested to document it)."),
    "F1_brk_ridge_filter:btcusd": (["10%", "25%", "50%"], [0.5, 0.75], ["25%", "50%"], [0.0, 0.25], ["10%", "50%"],
                                   "part 1: cutting lost in almost every cell (-5 to -206 R); the exceptions are tiny "
                                   "(25% state<=-0.75 +0.5 R, 50% state<=-0.25 +3.0 R). Tested to document the user's "
                                   "rule on the sleeve with the highest expectancy."),
    "brk72_24h_wd:ethusd": (["10%", "25%", "50%"], [0.25, 0.5], ["25%", "50%"], [0.0, 0.25], ["25%", "50%"],
                            "part 1: early-cut cells that paid: 25% (6 h) state<=-0.5 +6.7 R (43 trades, 4/4 years), "
                            "50% state<=-0.25 +6.4 R; no-progress 25% y=0 +11.9 R (245 trades, 3/4), 50% y=0 +6.9 R, "
                            "y=0.25 +6.2 R."),
    "F1_brk_ridge_filter:ethusd": (["10%", "25%", "50%"], [0.5, 0.75], ["25%", "50%"], [0.0, 0.25], ["10%", "50%"],
                                   "part 1: early-cut cells that paid are small: 10% state<=-0.75 +1.0 R (4/4), 50% "
                                   "state<=-0.5 +2.2 R (3/4); every no-progress cell lost (-1.6 to -131 R)."),
    "GOLD_FRI_PM:xauusd": (["30m", "60m", "120m"], [0.25, 0.5], ["10%", "30m"], [0.0, 0.25], ["30m", "60m"],
                           "part 1: the stop (3 x ATR) is far from the price over a 3-hour hold: at most 2 trades in 4 "
                           "years reach -0.5 R and 2-16 reach -0.25 R; every cell is within +-3.1 R. Tested to document it "
                           "(x=0.5 is expected to be almost a no-op)."),
    "donch4h_stop:xauusd": (["30m", "60m", "120m"], [0.5, 0.75], ["10%", "25%"], [0.0, 0.25], ["60m", "10%"],
                            "part 1: early-cut cells that paid: 30m state<=-0.5 +1.9 R (7 trades, 3/4), 60m state<=-0.5 "
                            "+2.2 R (14 trades, 4/4); no-progress 10% y=0 +0.4 R; all else lost."),
    "orb_asia_2d_buf10:xauusd": (["60m", "120m", "10%"], [0.25, 0.5], ["25%", "50%"], [0.25, 0.5], ["120m", "10%"],
                                 "part 1: early-cut cells that paid: 120m state<=-0.25 +26.2 R (112 trades, 3/4 years; "
                                 "but 60m -4.2 R and 2013-2017 -6.4 R), 10% (about 6 h) state<=-0.5 +6.5 R (31 trades, "
                                 "3/4); no-progress 50% y=0.25 +3.3 R, y=0.5 +5.6 R (85 trades; 2013-2017 -36.7 and "
                                 "-44.2 R)."),
}

RULES = {
    "EC": "early cut: at the checkpoint, if the trade is still open and its open result u <= -x R, close it at the "
          "open of the next bar (time exit, market slippage); otherwise nothing changes",
    "NP": "no-progress exit: at the checkpoint, if the trade is still open and u < y R (not ahead by y), close it at "
          "the open of the next bar; otherwise nothing changes",
    "HC": "half cut: at the checkpoint, if the trade is still open and u <= 0 (not ahead), close HALF of it at the open "
          "of the next bar; the other half keeps the original exits. Trade result in R of the full planned risk = "
          "0.5 x R(half kept) + 0.5 x R(half cut); the sleeve stays busy until the kept half exits",
}

DEFINITIONS = {
    "checkpoint": "minutes t after the fill time (start of the fill bar), or a fraction f of the planned life "
                  "(planned end - fill time, calendar time); the decision bar is the last M1 bar that STARTED before "
                  "fill + t (it is closed at fill + t); the exit is executed at the open of the next bar in the frame",
    "planned_end": "the scheduled time exit of the order (its exit_i bar); noise30: 15:55 New York of the session "
                   "(its band exits are signal exits)",
    "state_u": "open result at the close of the decision bar on the quote that would close the trade: long "
               "(bid close - entry) / risk, short (entry - ask close) / risk; entry = the simulated fill incl. "
               "slippage; risk = |entry - initial stop|",
    "still_open": "the trade has not been stopped and has not reached its time exit by the close of the decision bar",
    "simulation_EC_NP": "1) every signal run independently (no_overlap False) on the same frame and costs: each "
                        "order's own fill and path; 2) for every order where the rule fires, exit_i := decision bar + 1 "
                        "(never later than the original exit); 3) run with no_overlap True (an earlier exit frees the "
                        "sleeve for its next signal). Same in the x1.5 cost run (decisions recomputed on its quotes).",
    "simulation_HC": "the official trade set (no_overlap True, original exits); each trade rerun alone with "
                     "exit_i := decision bar + 1 where the rule fires; R = 0.5 R_orig + 0.5 R_cut",
    "broker_min_stop": "an order whose stop distance is under 3 spreads at its fill bar is not taken (removed from "
                       "the order list before any run, in each cost mode with that mode's spread)",
    "costs": "FP costs (r2.costs(sym), frame as stored) and x1.5 (spread x1.5 around the mid, both slippages x1.5, "
             "orders rebuilt on the widened quotes, swaps unchanged)",
    "window": "criteria on entries 2018-02-01 .. 2021-12-31; earlier in-sample years reported separately",
}

CRITERIA = {
    "a": "exp_var >= exp_base + 0.20 x |exp_base|  OR  (|avg_loss_var| <= 0.80 x |avg_loss_base| AND exp_var >= "
         "exp_base); where exp_base <= 0 (GOLD_FRI_PM, 2018-2021 expectancy -0.007 R) the expectancy route also "
         "requires exp_var > 0",
    "b": "total_R_var >= total_R_base",
    "c": "the improvement used in (a) (expectancy per trade, or average loss for the loss route) is better than the "
         "base in at least 3 of the 4 years 2018-2021",
    "d": "(a) and (b) also hold with costs x1.5 (variant x1.5 against base x1.5)",
    "e": "every one-step neighbour of the variant in its declared grid (same rule; next checkpoint or next threshold) "
         "has exp_var > exp_base and total_R_var >= total_R_base (FP, 2018-2021); for HC the other checkpoint",
    "f": "truncation test: for every order where the rule is evaluated, the decision recomputed from the frame cut "
         "right after the decision bar is identical",
    "rank": "if several variants of one sleeve qualify: larger 2018-2021 FP total-R gain first, then larger x1.5 gain",
}


def main():
    path = os.path.join(C.RES, "declared.json")
    if os.path.exists(path):
        raise SystemExit("declared.json exists: the declaration is written once")
    variants = []
    for sl, (ec_t, ec_x, np_t, np_y, hc_t, why) in PLAN.items():
        n0 = len(variants)
        for i, t in enumerate(ec_t):
            for j, x in enumerate(ec_x):
                variants.append({"id": f"{sl}|EC|t={t}|x={x}", "sleeve": sl, "rule": "EC", "checkpoint": t,
                                 "ck": ck(t), "x": x, "grid": [i, j]})
        for i, t in enumerate(np_t):
            for j, y in enumerate(np_y):
                variants.append({"id": f"{sl}|NP|t={t}|y={y}", "sleeve": sl, "rule": "NP", "checkpoint": t,
                                 "ck": ck(t), "y": y, "grid": [i, j]})
        for i, t in enumerate(hc_t):
            variants.append({"id": f"{sl}|HC|t={t}", "sleeve": sl, "rule": "HC", "checkpoint": t, "ck": ck(t),
                             "grid": [i, 0]})
        assert len(variants) - n0 <= 12
    out = {"written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "status": "declared before any variant was simulated; chosen from part 1 (2018-2021 anatomy, FP costs)",
           "budget": "at most 12 variants per sleeve", "n_variants": len(variants),
           "rules": RULES, "definitions": DEFINITIONS, "candidate_criteria": CRITERIA,
           "why_per_sleeve": {k: v[5] for k, v in PLAN.items()}, "variants": variants}
    C.jdump(out, path)
    print(len(variants), "variants declared")


if __name__ == "__main__":
    main()
