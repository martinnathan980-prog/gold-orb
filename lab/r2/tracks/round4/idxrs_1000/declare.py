"""Round 4 (PROTOCOL_V3 Addendum J), rule 1: IDXRS_1000.  Writes results/r2/round4/idxrs_1000/declared.json
BEFORE any run: the judge's frozen `rule` and `test_plan` texts (copied verbatim from results/r2/round4_ideas.json,
judge.ranking[0], whose sha256 is checked against Addendum J), the 12 declared configurations as parameters, and the
readings chosen where the text leaves a detail open (the most conservative / most literal one each time).

    PYTHONDONTWRITEBYTECODE=1 python3 declare.py
"""
import datetime as dt
import hashlib
import json
import os

LAB = "/home/user/gold-orb/lab"
SRC = os.path.join(LAB, "results", "r2", "round4_ideas.json")
OUT = os.path.join(LAB, "results", "r2", "round4", "idxrs_1000")
SHA_ADDENDUM_J = "c81387985baf8e43d64caa339c75daf4d3ff936a925ef28d97ff94755b5e225a"

MAIN = dict(entry_min=600, exit_min=955, q=0.75, win=60, minv=40, k=1.5, cost_mult=1.0)


def cfg(cid, name, **over):
    c = dict(MAIN)
    c.update(over)
    return {"id": cid, "name": name, "params": c}


CONFIGS = [
    cfg(1, "main"),
    cfg(2, "n_entry_0955", entry_min=595),
    cfg(3, "n_entry_1015", entry_min=615),
    cfg(4, "n_q67", q=0.67),
    cfg(5, "n_q80", q=0.80),
    cfg(6, "n_win40", win=40, minv=27),
    cfg(7, "n_win80", win=80, minv=54),
    cfg(8, "n_stop125", k=1.25),
    cfg(9, "n_stop175", k=1.75),
    cfg(10, "n_exit_1559", exit_min=959),
    cfg(11, "stress_x1.5", cost_mult=1.5),
    {"id": 12, "name": "null_200", "params": dict(MAIN, n_seeds=200, seed=0, of="main")},
]

READINGS = {
    "R1_period_and_sessions": (
        "In sample only: every frame is read with the parquet filter ts < 2022-01-01. Sessions = NYSE full sessions from "
        "the rule-based calendar already used by noise30/ocm4 (r2/tracks/idx_us/idxus_lib.us_holidays, imported read-only): "
        "weekdays that are neither a full closure nor a 13:00 early close. Early-close days are not sessions at all (not "
        "traded and not counted in any look-back window). The three frames are needed for a ranking, so the first possible "
        "session is the first one on which us30 has data (2013-09-30); after the warm-up the first trade falls in 2014."),
    "R2_bars": (
        "'the 09:30 bar' / 'the 09:59 bar' / 'the 10:00 bar' / 'the 15:55 bar' = the M1 bar that STARTS at that New York "
        "minute (bars are labelled by their start). A day has a ranking only if the 09:30 bar and the (T-1) bar exist for "
        "all three indices; otherwise D, the returns and the pair return of that day are missing (no trade, and the day "
        "gives no value to the look-back windows). Ties for the maximum or the minimum of r: no ranking that day."),
    "R3_threshold": (
        "Q = the q-quantile (numpy/pandas linear interpolation) of D over the finite values among the previous `win` "
        "sessions (the current day excluded), at least `minv` values; trade if D >= Q."),
    "R4_hedge_and_windows": (
        "sd_i = sample standard deviation (ddof=1) of index i's log return from the mid OPEN of the entry bar to the mid "
        "OPEN of the exit bar (10:00 -> 15:55 in the main; each neighbour uses its own entry / exit clock) over the finite "
        "values among the previous `win` sessions, at least `minv` values (the rule states 'at least 40 values' for the "
        "quantile only; the same minimum is applied to every window); a day's return is missing if either bar is "
        "missing. h = sd_S / sd_W with today's S and W. A day trades only if D >= Q and h and sd_pi are defined (and R11 "
        "holds)."),
    "R5_sd_pi": (
        "pi_j (mid) of each previous session j = ret_S(j) - h_j * ret_W(j), with day j's own ranking S_j / W_j and day j's "
        "own h_j (from day j's own trailing windows), computed for every session that has a ranking, traded or not. sd_pi = "
        "sample sd (ddof=1) of pi over the finite values among the previous `win` sessions, at least `minv` values."),
    "R6_min_values_of_other_windows": (
        "The rule states 'at least 40 values' for 60-session windows; the 40- and 80-session neighbours keep the same "
        "two-thirds share: at least 27 and 54 values. All three windows (quantile, sd for h, sd_pi) take the neighbour's "
        "length."),
    "R7_entry": (
        "Both legs need an M1 bar starting exactly at T; otherwise the signal is not entered ('if one leg fails'). Fills: "
        "BUY S at the ask open x (1 + 0.2 bp), SELL W at the bid open x (1 - 0.2 bp), same minute, notionals N and h x N."),
    "R8_stop_monitoring": (
        "Hard rule 3 (decisions on closed bars, execution at the next open): on the close of every M1 bar from the entry "
        "bar to the bar before the exit bar, pi is marked at exit-side closes (S at its bid close, W at its ask close; the "
        "last known close of a leg that has no bar in that minute). If pi <= -k x sd_pi, both legs are closed at the open "
        "of the next bar (for each leg its first bar at or after the next minute): S at bid x (1 - 0.5 bp), W at ask x "
        "(1 + 0.5 bp). A stop decided on the close of the last bar before the exit bar is executed at the exit bar's open "
        "and pays the stop slippage. No intrabar trigger is assumed (an M1 frame cannot order the two legs' extremes)."),
    "R9_time_exit": (
        "Both legs at the open of the first bar at or after the exit minute (15:55 in the main): S at bid x (1 - 0.2 bp), "
        "W at ask x (1 + 0.2 bp). No position crosses the 17:00 New York rollover, so no swap."),
    "R10_R_unit": (
        "net pi = ln(P_S,exit / P_S,fill) - h x ln(P_W,exit / P_W,fill) at the actual fill prices (spread and slippage "
        "inside them), as the rule writes it; R = net pi / (k x sd_pi), k = the stop multiple (1.5 in the main; 1.25 / 1.75 "
        "in neighbours 8 / 9, i.e. R per unit of the initial pair risk as goldlab defines R; a constant k does not change "
        "PF or t). The money result with simple returns (N x (P_S,exit/P_S,fill - 1) - hN x (P_W,exit/P_W,fill - 1)) is "
        "reported beside it, not judged."),
    "R11_stop_floor": (
        "Hard rule 4: the pair is refused if k x sd_pi < 3 x (spread_S + h x spread_W), spreads = quoted (ask - bid) / mid "
        "at the open of the entry bar, on the frame of the run (widened in the stress run)."),
    "R12_stress": (
        "Configuration 11: each leg's frame is widened with goldlab.sim.apply_spread_mult(frame, 1.5) (the lab's transform, "
        "mid unchanged, so the signals are unchanged) and both slippages x 1.5 (0.3 bp market, 0.75 bp stop)."),
    "R13_every_signal": (
        "The rule takes every signal (one pair a day, intraday, no overlap possible): the every-signal run is the main run."),
    "R14_null": (
        "Configuration 12: each of the main's filled pairs is replayed with the same legs and sides (BUY S, SELL W), the "
        "same hedge ratio h, the same stop level -1.5 x sd_pi and R unit 1.5 x sd_pi of the original trade (the stop kept "
        "in sd_pi units of that trade, as the lab's null keeps a trade's own stop distance), entry at the open of the "
        "10:00 bar and time exit at 15:55 (the main's holding time), FP costs, same fill and stop rules, on a session drawn "
        "uniformly with replacement among all in-sample full sessions (2013-09-30 to 2021-12-31) on which both legs have a "
        "10:00 bar. 200 replays (numpy default_rng(0)); statistic = mean R; percentile = share of replays whose mean R is "
        "below the main's; pass >= 97.5. The replays are not re-filtered (no threshold, no stop floor): they replay the "
        "main's filled pairs."),
    "R15_weekly_correlation": (
        "Weekly sums of R booked at the exit week (pandas weekly periods W-SUN of the UTC exit time, as goldlab.metrics), "
        "every calendar week from the week of 2014-01-01 to the week of 2021-12-31 counted (weeks without a trade = 0), "
        "Pearson correlation. ocm4 and noise30 = their official trades (results/r2/recalc/trades, read with the filter "
        "entry_time < 2022-01-01; any trade exiting in 2022 dropped). The condition 'at most 0.30' is read as |rho| <= 0.30 "
        "(stricter than rho <= 0.30)."),
    "R16_pair_types": (
        "Expectancy of a pair type (us100/us500, us100/us30, us500/us30, whichever side is long) = mean R of the main's "
        "trades of that type; a type without trades counts as not positive."),
    "R17_years": "Years positive = calendar years of entry with at least one trade whose summed R > 0; bar >= 60 %.",
    "R18_exit_1559": (
        "Neighbour 10 'exit 15:59' = both legs at the open of the 15:59 bar (the rule's convention: exits at bar opens); "
        "its windows use the 10:00 -> 15:59 returns."),
    "R19_neighbour_median": "Neighbours = configurations 2-10 (nine); their median PF must be >= 1.06.",
    "R20_reproduction_check": (
        "Not a trial: the same grid and two-leg code with h = 1, no stop, no cost, entry at the mid open of the 10:00 bar, "
        "exit at the mid close of the 15:59 bar, on desc_rs.py's own sample (weekdays 2014-2021 with the 09:30 and 10:00 "
        "opens present and closes forward-filled up to 3 minutes, as its grid does), dispersion cuts at the whole-sample "
        "quantiles; must give +2.69 bp (all days) and +8.06 bp (top quartile)."),
    "R21_account_run_reported_only": (
        "1,000 EUR account, 1 % of the current balance per pair, compounding; position sizes at TODAY's price level "
        "(r2/fp_costs.json spread_ref_price: us100 27000, us500 7377, us30 51286; Addendum E convention), USD -> EUR 0.89 "
        "(r2/tracks/stake/account.py), lot 1 index unit, minimum lot and step 0.1. N = budget / (1.5 x sd_pi); lots rounded "
        "down; a leg below 0.1 lot is raised to 0.1 if the pair's risk at those lots (1.5 x sd_pi x max(N_S, N_W / h)) is "
        "within 1.5 % of the balance, else the signal is skipped; pairs with us30 are skipped while the balance is below "
        "4,000 EUR; the money result uses each leg's own simple return and lots."),
    "R22_reported_not_judged": (
        "Gross bp per pair (a separate run on mid prices, no slippage), cost per pair, results by pair type and by side of "
        "us100, the 1,000 EUR run, the correlation with the sum of the ten and with each cluster, and the money result."),
}

CRITERIA = {
    "n>=250": "main n >= 250",
    "pf>=1.12": "main PF on R >= 1.12",
    "t>=2.5": "main t on per-trade R >= 2.5",
    "years_pos>=60%": "share of positive entry years >= 60 %",
    "stress_pf>=1.04": "configuration 11 PF >= 1.04",
    "neighbours_median_pf>=1.06": "median PF of configurations 2-10 >= 1.06",
    "every_signal_exp>0": "every-signal expectancy > 0 (= main, R13)",
    "max_hold<=5d": "hold <= 5 trading days",
    "null>=97.5": "configuration 12 percentile >= 97.5",
    "extra_corr_ocm4_noise30<=0.30": "|weekly R correlation with ocm4 + noise30| <= 0.30 over 2014-2021 (R15)",
    "extra_pair_types>=2": "at least 2 of the 3 pair types with positive expectancy (R16)",
}


def main():
    raw = open(SRC, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == SHA_ADDENDUM_J, f"round4_ideas.json changed: {sha}"
    j = json.loads(raw)["judge"]["ranking"][0]
    assert j["name"].startswith("IDXRS_1000")
    out = {
        "_written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "_note": ("Written BEFORE any run of this rule (no simulation, no signal, no reproduction check had been run). "
                  "IN SAMPLE ONLY: every frame is read with ts < 2022-01-01; nothing dated 2022 or later is read."),
        "addendum": "PROTOCOL_V3.md Addendum J, rule 1",
        "short_name": "idxrs_1000",
        "source_file": "results/r2/round4_ideas.json", "source_sha256": sha, "source_key": "judge.ranking[0]",
        "frozen_name": j["name"],
        "frozen_rule": j["rule"],
        "frozen_test_plan": j["test_plan"],
        "frozen_instruments": j["instruments"],
        "prior_pass_validation_pct": j["prior_pass_validation_pct"],
        "configurations": CONFIGS,
        "param_legend": {"entry_min": "New York minute of the entry bar = ranking time (rank on the bar before)",
                         "exit_min": "New York minute of the exit bar", "q": "quantile of D", "win": "look-back sessions",
                         "minv": "minimum finite values in a window", "k": "pair stop in sd_pi units",
                         "cost_mult": "spread and slippage multiplier"},
        "costs": {"spread": "inside the FP frames (lab/data/fp, r2/fp_costs.json: 0.37 / 0.54 / 0.35 bp for us100 / us500 / us30 "
                            "at the reference price, Dukascopy intraday shape)",
                  "slip_market_bp_per_side_per_leg": 0.2, "slip_stop_bp_per_leg": 0.5, "swap": 0.0,
                  "stress": "spread and slippage x 1.5"},
        "readings_of_open_details": READINGS,
        "pass_criteria_main": CRITERIA,
        "files": {"code": "r2/tracks/round4/idxrs_1000/", "results": "results/r2/round4/idxrs_1000/",
                  "trials": "results/r2/round4/idxrs_1000/trials.jsonl (one line per configuration, 12 lines)"},
    }
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "declared.json")
    assert not os.path.exists(p), "declared.json already exists: never rewritten"
    with open(p, "w") as f:
        json.dump(out, f, indent=1)
    print("written", p, sha)


if __name__ == "__main__":
    main()
