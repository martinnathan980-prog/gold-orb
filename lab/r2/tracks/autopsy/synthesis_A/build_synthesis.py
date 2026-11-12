"""Lead synthesis A: writes results/r2/autopsy/synthesis_A.json from the in-sample runs of this directory.
No simulation.  IN SAMPLE ONLY."""
import csv
import glob
import hashlib
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = "/home/user/gold-orb/lab"
WORK = os.path.join(HERE, "work")
OUT = os.path.join(LAB, "results", "r2", "autopsy", "synthesis_A.json")

P = json.load(open(os.path.join(WORK, "portfolio.json")))
REH = json.load(open(os.path.join(WORK, "criteria_rehearsal.json")))
DECL = json.load(open(os.path.join(HERE, "declared.json")))
TRIALS = [json.loads(x) for x in open(os.path.join(HERE, "trials.jsonl"))]
TRUNC = {}
for f in sorted(glob.glob(os.path.join(WORK, "truncation_*.json"))):
    for k, v in json.load(open(f)).items():
        if isinstance(v, dict):
            TRUNC[k] = {x: v[x] for x in ("variant", "sampled_acting", "sampled_other", "a_tested", "a_identical",
                                          "b_tested", "b_identical", "c_tested", "c_identical")}
            TRUNC[k]["mismatches"] = len(v["mismatches"])
LOSS = list(csv.DictReader(open(os.path.join(WORK, "loss_composition_main_fp.csv"))))


def sha(p):
    return hashlib.sha256(open(os.path.join(LAB, p), "rb").read()).hexdigest()


FROZEN = {p: sha(p) for p in (
    "r2/tracks/autopsy/synthesis_A/synth.py", "r2/tracks/autopsy/synthesis_A/portfolio.py", "goldlab/sim.py",
    "goldlab/r2.py", "goldlab/data.py", "goldlab/split.py", "r2/recalc.py", "r2/fp_costs.json",
    "r2/tracks/idx_us/strategy.py", "r2/tracks/crypto/strategy.py", "r2/tracks/ml/strategy.py",
    "r2/tracks/ml/models/B1_ridge_full.json", "r2/tracks/leadlag/strategy.py", "r2/tracks/overnight/strategy.py",
    "tracks/trend/strategy.py", "tracks/orb/strategy.py")}

rule2 = {t["sleeve"]: t["rule2"] for t in TRIALS if t.get("kind") == "simulation" and "rule2" in t}
crosscheck = {f'{t["sleeve"]}|{t["variant"]}|{t["mode"]}': t["lens_crosscheck"] for t in TRIALS if t.get("kind") == "simulation"}
n_sim = sum(1 for t in TRIALS if t.get("kind") == "simulation")
n_asm = sum(1 for t in TRIALS if t.get("kind") == "assembly")

M = lambda k, w="main": P["portfolios"][k][w]
FAC = P["equal_swing_factors_frozen"]


def table(k, w):
    m = M(k, w)
    keys = ("n_trades", "expectancy_R", "euros_per_100_risked", "win_rate", "avg_win_R", "avg_loss_R", "profit_factor",
            "total_R", "worst_week_R", "max_drawdown_R_trades_exit_order", "max_drawdown_R_weekly",
            "longest_losing_run_weeks", "losing_weeks_share", "mean_over_sd_per_trade", "weekly_sharpe",
            "by_entry_year_total_R", "weeks")
    return {x: m[x] for x in keys}


portfolio = {
    "convention": "R = pnl / |fill - initial stop actually used|; constant stake = 1 R per trade at each trade's own stop; "
                  "equal swing = each changed sleeve's stake x its frozen factor so that its weekly SD of R equals the "
                  "unchanged sleeve's over 2018-02..2021-12 (FP); weeks = FP server weeks (New York + 7 h, Monday start), "
                  "R booked at the exit, empty weeks = 0; drawdown on cumulative R in exit order (trade by trade) and on "
                  "weekly sums; censored year-end trades excluded everywhere",
    "equal_swing_factors": FAC,
    "main_2018_02_to_2021_12": {lab: {mode: table(f"{lab}|{mode}", "main") for mode in ("fp", "stress")}
                                for lab in ("unchanged", "all_five_constant_stake", "all_five_equal_swing")},
    "early_entries_before_2018_02_not_used_to_pick": {lab: {mode: table(f"{lab}|{mode}", "early") for mode in ("fp", "stress")}
                                                     for lab in ("unchanged", "all_five_constant_stake", "all_five_equal_swing")},
    "each_change_alone_weekly_sharpe": {
        k.split("|")[0]: {w: P["portfolios"][k][w]["weekly_sharpe"] for w in ("main", "early")}
        for k in P["portfolios"] if k.startswith("only_") and k.endswith("|fp")},
    "deltas_vs_unchanged": P["deltas_vs_unchanged"],
}

sleeves = {}
for key, d in P["changed_sleeves"].items():
    e = {"change": d["change"], "equal_swing_factor": d["equal_swing_factor"]}
    for k in ("unchanged_fp_main", "changed_fp_main", "unchanged_stress_main", "changed_stress_main",
              "unchanged_fp_early", "changed_fp_early", "unchanged_stress_early", "changed_stress_early"):
        if k in d:
            e[k] = d[k]
    for k in list(d):
        if k.startswith("gain_") or k.startswith("changed_equal_swing"):
            e[k] = d[k]
    sleeves[key] = e

where = [
    "Overall (entries 2018-02-01..2021-12-31, ten sleeves, 5,205 trades, FP costs; my simulator runs equal the official trades): 2,864 losing trades (55.0 %) lose 1,853 R and 2,341 winners make +2,642 R, net +788.6 R. Average loss -0.65 R against average win +1.13 R; the best 10 % of winners make 40 % of the gross gain.",
    "Most of the money lost is full stops: 1,447 losers end on their stop at -0.98 R on average and carry 1,421 R, 77 % of all losses; the other 1,417 losers leave by the clock at -0.31 R on average. The worst trade of the four years is -1.49 R (a time exit at the reopening after the 2018 Christmas closure, beyond the stop) and only 3 of 5,205 trades lost more than 1.2 R: every loser is already cut at about one risk unit; there is no rare big loss to remove.",
    "By sleeve, share of the loss that comes from full stops (same window, FP): orb_asia 98 % (301 of 319 losers; win rate 31 %, average win +2.37 R), ocm4 93 % (241 of 291), F1 ETH 84 %, F1 BTC 81 %, brk72 BTC 79 %, brk72 ETH 76 %; nq_btc_follow 44 % and noise30 36 %, whose losses are mostly small clock exits (377 of 451 at -0.25 R; 405 of 481 at -0.33 R); donch4h_stop 100 % on its trailing stop, at -0.59 R on average; GOLD_FRI_PM 0 % (stop never touched, average loss -0.16 R, -1.3 R over 183 trades against +15.2 R over 231 trades in 2013-2018/01).",
    "Losing trades do not look bad at the start (path lens, minute by minute): 27 % of losers had been at least +0.5 R ahead and 9.5 % at least +1 R (ocm4 47 % and 22 %, orb 44 % and 23 %) before falling to the stop; losers reach their best point early (median 23 minutes) and their worst at the end.",
    "Winners often start badly: 44 % of winners were at -0.25 R or worse at some point, 19 % at -0.5 R or worse and 6 % at -0.75 R (orb 67/40/16 %, ocm4 63/37/14 %), with their worst point early (median 19 minutes). A cut at -0.5 R would also cut about one winner in five.",
    "The user's first claim does not hold on these rules. Of 665 trades first seen at -0.5 R or worse in their first two hours, the rest of the trade still earned +0.078 R each (t 2.1) and 12 % still ended as winners: cutting them would have cost about 52 R in four years. Only from -0.75 R (147 trades) is the rest about zero (-0.017 R), and cutting would have saved 2.6 R in four years, because the stop is only 0.25 R further. The 45 declared early-cut rules moved the total by -11.3 to +6.3 R (sum -25.7 R); none passed; the earlier years 2013/14-2017 say the same.",
    "The second claim, letting winners run, holds only partly and mostly as longer exposure. Holding F1 ETH trades that are at least +1 R at the 15:55 exit two more days earned +0.21 R per trade in 2018-2021 (+0.10 to +0.16 after the trial-count correction); the same rule on F1 BTC earns nothing once risk is counted, and extending a random set of trades there earns about two thirds as much (every open trade, more). On ocm4, trailing for up to four days instead of closing at 15:55 earned +0.25 R per trade at a constant stake (mostly longs held in a rising index), but per unit of swing +0.55 of weekly Sharpe in 2018-2021 and +0.006 in 2014-2018. Trailing exits in place of the clock did not qualify on 7 of the 9 sleeves where they were tried (of the two that qualified, nq T1 was refuted and ocm4 T1 is kept with an expected gain near zero); break-even after +1.5 R lowered the expectancy on 6 of the 8 sleeves where it acts; targets and half exits gave small effects (shape study).",
    "Getting in better does not help: losers come back through the entry price in 95-100 % of cases, but so do 33-91 % of winners; a limit order on a pullback fills the losers and misses the runners (total R lower in 28 of 28 cells); the only entry gain, the gold retest, equals the 1 bp stop slippage the lab assumes.",
]

survive = [
    {"sleeve": "ocm4 us100", "change": "T1: no 15:55 NY exit; trailing stop at 1 daily ATR14 (simple mean) from the best price since the fill, used from the next minute; initial stop unchanged at 0.3 ATR; time cap at 15:55 NY of the entry's NY date + 4 business days; one position at a time.",
     "effect_in_sample": "My simulator, entries 2018-02..2021, FP: 492 -> 350 trades, +0.109 -> +0.364 R per trade, total +53.8 -> +127.4 R (x1.5: +50.8 -> +125.0 R); sleeve weekly Sharpe 0.89 -> 1.44; at equal weekly swing (stake x0.68) +33.2 R; ten-sleeve weekly Sharpe at equal swing 2.873 -> 3.042. Earlier years 2014-2018/01 (507 -> 370 trades): sleeve weekly Sharpe 1.142 -> 1.148, +3.3 R at equal swing, portfolio 2.406 -> 2.385.",
     "verdict_of_the_attack": "weakened (13:15 round): like-for-like +0.21 R per trade in both 2014-18 and 2018-21, mostly longs held for days in a rising index; per unit of swing 'nothing demonstrated' (best of 10 p 0.30-0.37); as the live program would run it +0.111 R per trade and +0.05 of portfolio weekly Sharpe. Kept with an expected gain close to zero."},
    {"sleeve": "F1_brk_ridge_filter ethusd", "change": "H2: a trade still open and at least +1 x its initial risk ahead (bid close for a long, ask close for a short) at the close of the bar before its 15:55 NY exit is held to 15:55 NY two business days later, never past the Friday 23:54 server bar; stop unchanged; one position at a time.",
     "effect_in_sample": "My simulator, 2018-02..2021, FP: 516 -> 463 trades (100 extended), +0.200 -> +0.412 R per trade, total +103.0 -> +190.6 R (x1.5: +85.9 -> +178.1 R); sleeve weekly Sharpe 1.75 -> 2.43; at equal swing (stake x0.75) +40.1 R, gain in 3 of 4 years (2019 -3.2 R); ten-sleeve weekly Sharpe at equal swing 2.873 -> 3.048. No earlier years (ETH data starts 2018).",
     "verdict_of_the_attack": "weakened: causal, executable, not an isolated peak, not made by the one-position rule; after the trial-count haircut +0.10 to +0.16 R per trade (+35 to +65 R); rests on a handful of multi-day continuations (capped at +3 R per trade only +0.04 R per trade remains), 2019 flat, three quarters of the gain with each year's ETH direction; the BTC twin gives nothing once risk is counted."},
    {"sleeve": "brk72_24h_wd btcusd", "change": "S0.75r: initial stop at 0.75 x the rule's distance (3 x ATR24) from the fill, same money risk (a 1.33x position), exits unchanged, one position at a time over all signals.",
     "effect_in_sample": "My simulator, 2018-02..2021, FP: 549 -> 563 trades, +0.256 -> +0.365 R per trade, total +140.7 -> +205.4 R (x1.5: +135.5 -> +199.4 R); sleeve weekly Sharpe 1.78 -> 2.01; at equal swing (x0.77) +17.9 R, gain in 4 of 4 years; ten-sleeve weekly Sharpe at equal swing 2.873 -> 2.933. Earlier months 2017-05..2018-01 (96 -> 101 trades): sleeve weekly Sharpe 2.51 -> 2.19, -5.0 R at equal swing.",
     "verdict_of_the_attack": "weakened (13:15 round): about 4/5 of the R gain is leverage; at equal swing +0.025 R per trade in the lab and +0.004 (+7.1 R) as the live program would run it; studentized best-of-13 p 0.12. Kept with an expected gain close to zero."},
    {"sleeve": "donch4h_stop xauusd", "change": "S0.75r: initial stop and trailing distance at 0.75 x 2 ATR14(4h) = 1.5 ATR; same money risk; entries and the 5-day time exit unchanged; one position at a time over all touched brackets.",
     "effect_in_sample": "My simulator, 2018-02..2021, FP: 207 -> 251 trades, +0.145 -> +0.222 R per trade, total +30.0 -> +55.8 R (x1.5: +27.3 -> +51.4 R); sleeve weekly Sharpe 0.86 -> 1.41; at equal swing (x0.89) +19.4 R, gain in 4 of 4 years; ten-sleeve weekly Sharpe at equal swing 2.873 -> 2.941. Earlier years 2013-2018/01 (287 -> 379 trades): sleeve weekly Sharpe 1.21 -> 1.11, -4.2 R at equal swing.",
     "verdict_of_the_attack": "weakened by two verifiers: honest expectation +0.00 to +0.02 R per trade; the gain per unit of swing comes from the tighter trail; best of 8 p 0.2-0.4; negative on the earlier years."},
    {"sleeve": "orb_asia_2d_buf10 xauusd", "change": "S0.75r: initial stop at 0.75 x the distance from the stop-entry fill to the opposite range level, same money risk, exits unchanged, one position at a time over all signals.",
     "effect_in_sample": "My simulator, 2018-02..2021, FP: 464 -> 498 trades, +0.058 -> +0.140 R per trade, total +27.1 -> +69.5 R (x1.5: +15.1 -> +52.5 R); sleeve weekly Sharpe 0.32 -> 0.63; at equal swing (x0.76) +26.1 R, gain in 3 of 4 years, almost all of it in 2020-2021 (+25.8 of +26.1 R); ten-sleeve weekly Sharpe at equal swing 2.873 -> 2.980. Earlier years 2013-2018/01 (574 -> 626 trades): sleeve weekly Sharpe 1.50 -> 1.63, +22.5 R at equal swing (on the same orders only +0.01 R per trade; the rest is the one-position chain).",
     "verdict_of_the_attack": "weakened (13:15 round): 'the direction is real, the size is not'; neighbours give about +27 R at a constant stake and +0.05 to +0.09 of portfolio weekly Sharpe; best of 14 p about 0.7; everything in 2020-2021."},
]

ideas = [
    "Cutting at once a trade that goes hard the wrong way (the user's rule): 45 declared variants (cut at -0.5 or -0.75 R after 5, 15 or 30 minutes or at 10/25/50 % of the planned life), total R from -11.3 to +6.3 R, sum -25.7 R, none passes; trades at -0.5 R or worse early still earned +0.078 R each on the rest of the trade (665 trades, 2018-2021).",
    "No-progress exits (leave when not ahead after a fixed time): 40 variants, 27 lower the total (F1 BTC -77 R, F1 ETH -53 R, orb -38 R, nq -32 R); the one non-degenerate pass (ocm4 closed at mid-day unless +0.5 R ahead, +23 R in 2018-2021) loses 4.6 R in 2014-2017 and its verifier puts it at about zero.",
    "Half cuts when not ahead: the average loss is lower in all 20 variants but the expectancy is lower in 13 (F1 BTC -58 R); the one pass (brk72 ETH at 6 h, +5.9 R) is refuted: best of 48 screened cells in 93 % of null draws, BTC twin -8.2 R, -2.8 R with a one-minute entry delay.",
    "Much tighter stops at the same money risk (0.25-0.5 x): only a bigger position. noise30 0.25x: +0.245 R per trade but -0.0024 R per trade at equal weekly swing and -1.6 % of portfolio weekly Sharpe (refuted twice); brk72 BTC 0.25x: -0.038 R per trade at equal per-trade swing; brk72 ETH 0.5x: +0.010 R at FP and -0.004 R at x1.5 at equal SD.",
    "Wider stops (1.5 x): expectancy and total lower on 9 of 10 sleeves.",
    "Trailing exits in place of the clock on the four crypto breakouts, noise30, orb and GOLD_FRI_PM: none qualifies (lower expectancy, or below the +20 % bar); on nq_btc_follow (T1) refuted: +0.010 R per trade at equal swing, portfolio weekly Sharpe +0.003, best of 14 p 0.58.",
    "Break-even after +1.5 R: lower on 6 of the 8 sleeves where it acts (orb +0.058 -> -0.019 R per trade); after +1 R: lower on brk72 ETH and F1 ETH, +5.6 % on nq.",
    "Holding winners longer on F1 BTC (H2): +29 % in R, but about 0 per unit of risk (equal per-trade SD 0.342 vs 0.345 R), and random extensions earn about two thirds of it.",
    "Pullback limit entries: total R lower in 28 of 28 cells (they fill the losers and miss the runners); waiting for a confirming close: lower in 22 of 28; entering in two halves: lower in 14 of 14; donch retest entries: lower in 12 of 12.",
    "Gold retest entries (orb): the gain equals the assumed 1 bp stop-entry slippage; the skip forms lose 37-45 R on 2013-2018/01; the market-fallback forms are worth 0 to +0.02 R per trade (not carried: one change per sleeve, and S0.75r has the larger remainder).",
    "GOLD_FRI_PM: nothing works (0 of 11 payoff variants; the shorter holds destroy its 2013-2018/01 edge, +15.2 R -> -2.7 or -5.6 R, and the half-size entry halves it, +8.3 R).",
]

decl_text = (
    "Addendum H, synthesis A - declaration of ONE look at 2022-2025 for the five kept changes (written 2026-11-12 before any 2022+ row of these changes is read; to be appended to PROTOCOL_V3.md by the lead and run once, by the lead only). "
    "1. WHAT: exactly five changes, each on its own sleeve, nothing else: (1) ocm4 us100 T1: the 15:55 NY exit removed, trailing stop at 1 x the daily ATR14 (simple mean; = the rule's stop distance / 0.3) from the best bid high (long) / ask low (short) since the fill, updated at each M1 close and used from the next bar, initial stop unchanged at 0.3 ATR, time cap at the open of the first bar at/after 15:55 NY on the entry's NY date + 4 business days; "
    "(2) F1_brk_ridge_filter ethusd H2: a trade still open at the close of the bar before its 15:55 NY exit bar and at least +1 x its initial risk ahead there (bid close for a long, ask close for a short) is held to the first bar at/after 15:55 NY on the decision's NY date + 2 business days, never past the Friday 23:54 server bar, stop unchanged; "
    "(3) brk72_24h_wd btcusd, (4) donch4h_stop xauusd (stop and trailing distance) and (5) orb_asia_2d_buf10 xauusd, each S0.75r: initial stop at 0.75 x the rule's distance from the fill, same money risk, exits unchanged. All with one position per sleeve over all of the rule's signals and a stop closer than 3 spreads of the fill bar not sent. The other five sleeves are unchanged and enter only the portfolio reading. "
    "2. FROZEN: the functions change_T1, h2_decision, change_H2, change_S, make_variant, refused and censored of lab/r2/tracks/autopsy/synthesis_A/synth.py (sha256 " + FROZEN["r2/tracks/autopsy/synthesis_A/synth.py"] + ") and measures() of portfolio.py (sha256 " + FROZEN["r2/tracks/autopsy/synthesis_A/portfolio.py"] + "); the rules as lab/r2/recalc.py sleeves() registers them (sha256 " + FROZEN["r2/recalc.py"] + "; strategy files and the F1 model as hashed in results/r2/autopsy/synthesis_A.json); goldlab/sim.py (sha256 " + FROZEN["goldlab/sim.py"] + "); costs r2/fp_costs.json (sha256 " + FROZEN["r2/fp_costs.json"] + ") through r2.costs, FP on the stored frame and x1.5 on the spread-x1.5 frame with the orders rebuilt on it; "
    "the equal-swing stake factors fixed on 2018-02..2021-12: ocm4 " + str(FAC["ocm4:us100"]) + ", F1 ETH " + str(FAC["F1_brk_ridge_filter:ethusd"]) + ", brk72 BTC " + str(FAC["brk72_24h_wd:btcusd"]) + ", donch " + str(FAC["donch4h_stop:xauusd"]) + ", orb " + str(FAC["orb_asia_2d_buf10:xauusd"]) + "; "
    "R = pnl / |fill - initial stop actually used|; weeks = FP server weeks (New York + 7 h, Monday start), R booked at the exit, empty weeks counted as 0; weekly Sharpe = mean / sd x sqrt(52); drawdown on cumulative R in exit order. Frames lab/data/fp/<sym>_m1.parquet read through 2025-12-31 and simulated from their first bar (warm-ups and one-position chains continue from the in-sample years); the nq leader from the same us100 frame. Window: entries 2022-01-01 to 2025-12-31 (entry year for the yearly split); a trade still open when the 2025 data ends is excluded on both sides. "
    "3. CHECK FIRST: the unchanged sleeves recomputed by this pipeline must equal the official recalc trades of 2022-2025 (count, total R, trade by trade); otherwise stop and report. "
    "4. COMPARED: each change against the same sleeve unchanged (same frame, costs and refusal rule), and the ten-sleeve portfolio with that one change at its frozen factor against the unchanged portfolio; then the changes that pass, together, against the unchanged portfolio. "
    "5. A CHANGE PASSES only if all hold: V1 the sleeve's weekly Sharpe is higher with the change AND the ten-sleeve portfolio's weekly Sharpe with the change at its frozen factor is higher (FP); V2 the sleeve's total R at a constant stake (1 R per trade at its own stop) is not lower (FP); V3 V1 and V2 also hold with costs x1.5; V4 the sleeve's gain at equal swing (total R with the change x its factor minus total R unchanged) is positive in at least 3 of the 4 entry years 2022, 2023, 2024, 2025 (FP); V5 the changed sleeve has an expectancy above 0 and a profit factor of at least 1.06 (FP). "
    "6. REPORTED, deciding nothing alone: for the unchanged portfolio, for all five changes and for the passing ones, at a constant stake and at equal swing, FP and x1.5: trades, expectancy in R and euros earned per 100 euros risked, win rate, average win and loss, profit factor, total R, worst week, maximum drawdown, longest run of losing weeks, share of losing weeks, mean/sd of R per trade, weekly Sharpe; every failing change is shown too. "
    "7. AFTER: a passing change goes to the demo account staked at its equal-swing factor and is described as what it is (a longer hold or a tighter stop, part of whose R is size or exposure), never as more R per trade; a failing change is dropped for good: no neighbour, no re-tuning, no substitute on its sleeve (the orb retest entry is not promoted). 'Nothing passes' is a valid outcome. Every 2022+ read goes through goldlab.split.cut(..., 'val', track='autopsy_synthesis_A', label=...) and is logged in results/val_access.log; no second look; the 2026 holdout stays untouched. The live program (entry one minute late, Friday 16:50 NY close-all, two positions per symbol, market orders only) is not part of this look; it is tested on the demo account. "
    "8. SAID IN ADVANCE: the verifiers put what is left at about +0.10 to +0.16 R per trade for F1 ETH H2 and close to zero for the four others. Rehearsed on the earlier in-sample years, which did not pick them, the same criteria pass for 1 of the 4 changes that can be tested there (orb S0.75r, whose equal-swing gain is positive in 3 of the 5 full years 2013-2017; ocm4 T1, brk72 BTC S0.75r and donch S0.75r fail V1), and the four together leave the portfolio's weekly Sharpe unchanged at equal swing (2.41 -> 2.40). The expected outcome is that few or none pass, and with five changes one may pass by chance.")

CAVEATS = [
    "In sample and optimistic by construction: the five changes were picked on 2018-2021 from about 360 lens variants (plus a post-hoc ranking by per-trade Sharpe in the 13:15 round). On the earlier in-sample years, which did not take part in picking them, the four changes that can be tested there leave the portfolio's weekly Sharpe unchanged at equal swing (2.406 -> 2.401) and lower the equal-swing total in 4 of the 5 full years 2013-2017 (+17.1 R overall, the whole gain from 2015); three of the four fail the declared V1 criterion there.",
    "Three of the five kept changes (ocm4 T1, brk72 BTC S0.75r, orb S0.75r) come from the supplementary payoff round of the 13:15 clarification (results/r2/autopsy/complement_verdicts.json), not from the relayed JSON; that round chose them by per-trade Sharpe after the lens's table was seen (post hoc, said so in the protocol).",
    "Qualifiers that no verifier attacked have no verdict and were not kept: nq_btc_follow T3 and orb_asia S0.25n (ranks 1 of the payoff lens's declared ranking) and every lower-ranked qualifier.",
    "Size and exposure: S0.75r is a 1.33x position at the same money risk; T1 turns ocm4 from an intraday rule into one held up to 4 business days (overnight and weekend gaps; worst T1 trade -3.05 R); H2 adds up to two days to 100 F1 ETH trades (+82 % time in market). The constant-stake figures overstate the gain; the equal-swing figures (stakes x0.68 to x0.89) are the fair comparison and are what the declared look judges.",
    "The live program differs: entry one minute late, Friday 16:50 NY close-all, two positions per symbol (three sleeves on BTC and three on gold), market orders only. The verifiers' live readings were much smaller (ocm4 T1 +0.111 instead of +0.255 R per trade; brk72 BTC S0.75r +0.004 R per trade at equal swing; the lab orb rule loses its weekend holds).",
    "Two official in-sample trades entered on 2021-12-31 (donch4h_stop, orb) have recorded exits in 2022; they are excluded from every statistic (their R appears only in the rule-2 total comparison: 84.24 vs 85.06 R and 230.07 vs 232.78 R; without them both totals match exactly).",
    "Costs are modelled: bid/ask = mid -/+ a half-spread built from the day's median spread (not causal, the same for every run), stop slippage 0.5-2 bp, swaps as annual rates; tighter stops are more exposed to real spread spikes and stop slippage than the model shows.",
    "The equal-swing factors were fitted on 2018-02..2021-12 FP; they bring each changed sleeve's weekly swing back to the unchanged one's and optimise nothing; the same factors are used for x1.5 and for the earlier years, and are frozen for the look.",
    "F1 ETH H2, the strongest change, cannot be checked on any earlier year (ETH data starts in 2018); on F1 BTC the same rule gives nothing once risk is counted, so its gain may be ETH's 2018-2021 trends.",
    "Five changes in one look: with no real effect any one of them can pass by chance; the declared criteria are a conjunction (V1-V5, FP and x1.5) to limit that, and a single pass should still be read with caution.",
    "Scale: taken at face value the five changes move the portfolio from 15 to 18 euros per 100 risked at equal swing on the years that picked them; the user's target needs about 35 on validation, where the unchanged rules make about 8.",
    "Addendum I's outcome, appended to PROTOCOL_V3.md by another job during this run, quotes an Addendum H kept set 'K1 + K2 + K3' that is not this synthesis's (synthesis_B.json was not read, for independence); the kept sets must be reconciled before the single look is declared.",
    "Process: nothing dated 2022 or later was read or simulated; no existing file was modified; I ran no git command that changes anything (the session's own 'Agents' work in progress' commit at 15:20 UTC included my files of that time); NUMBA_CACHE_DIR under /tmp and PYTHONDONTWRITEBYTECODE set.",
]

SUMMARY_FR = "\n".join([
    "Réponse : couper tout de suite un trade qui part mal ne rapporte rien sur ces règles ; laisser courir aide un peu, sans preuve solide.",
    "Les pertes viennent surtout des stops : 77 % de l'argent perdu, à environ -1 fois la somme risquée ; pas de grosse perte rare (la pire : -1,5 fois).",
    "Un trade déjà à mi-chemin de son stop dans ses 2 premières heures rapporte encore +0,08 fois la mise ensuite, en moyenne ; les couper aurait coûté environ 52 mises en 4 ans.",
    "Un gagnant sur cinq passe d'abord par la moitié du chemin vers son stop.",
    "Sur 360 variantes testées, les meilleures refaites et attaquées par un second analyste : 5 changements gardent un petit effet : laisser courir plus longtemps (ETH, indice US) et un stop un peu plus serré (BTC, or).",
    "Sur 2018-2021, avec ces 5 changements : 21 € gagnés pour 100 € risqués au lieu de 15 ; à secousses égales, 18 au lieu de 15.",
    "Mais ces années ont servi à les choisir : sur 2013-2017, à secousses égales, le rapport gain/secousses ne bouge pas (2,4 avant et après).",
    "Sur 2022-2025, les règles actuelles font environ 8 € pour 100 € risqués ; pour doubler en un mois il en faudrait environ 35 : l'écart reste entier.",
    "Proposition : un seul contrôle sur 2022-2025, écrit d'avance ; un changement n'est gardé que s'il améliore le gain à secousses égales.",
    "Le plus probable : peu ou aucun ne passe.",
])
BEFORE = ("Ten sleeves unchanged, entries 2018-02-01..2021-12-31, my simulator runs (= the official trades), FP costs: 5,205 trades; expectancy +0.152 R per trade; win rate 45.0 %; average win +1.13 R, average loss -0.65 R; profit factor 1.43; total +788.6 R; worst week -12.5 R; maximum drawdown 29.1 R at 1 R per trade (21.0 R on weekly sums); longest losing run 7 weeks; losing weeks 41.5 %; mean/sd of R per trade 0.108; weekly Sharpe 2.87. "
          "Costs x1.5 (5,207 trades): +0.137 R, win rate 44.3 %, PF 1.38, total +711.1 R, worst week -12.7 R, drawdown 30.8 R, run 7 weeks, mean/sd 0.098, weekly Sharpe 2.61. "
          "Earlier in-sample years (entries before 2018-02, sleeves that trade then, 2,758 trades, FP): +0.176 R, PF 1.45, total +485.8 R, worst week -8.1 R, drawdown 27.3 R, run 6 weeks, mean/sd 0.114, weekly Sharpe 2.41.")
AFTER = ("Same window with the five kept changes, FP. At a constant stake (1 R per trade at each trade's own stop): 5,102 trades; expectancy +0.212 R; win rate 43.2 %; average win +1.37 R, average loss -0.67 R; PF 1.56; total +1,082.8 R; worst week -15.5 R; maximum drawdown 26.4 R (22.1 R weekly); longest losing run 5 weeks; losing weeks 36.6 %; mean/sd 0.123; weekly Sharpe 3.44. Costs x1.5: +0.197 R, PF 1.51, total +1,002.9 R, worst week -17.0 R, drawdown 27.6 R, run 5 weeks, mean/sd 0.115, weekly Sharpe 3.21. "
         "Part of this is size and exposure: with each changed sleeve staked back to its old weekly swing (x0.68 ocm4, x0.75 F1 ETH, x0.77 brk72 BTC, x0.89 donch, x0.76 orb): +0.181 R per trade, average win +1.17 R, average loss -0.57 R, PF 1.56, total +925.2 R, worst week -12.6 R, drawdown 23.2 R (16.7 R weekly), run 4 weeks, losing weeks 35.6 %, mean/sd 0.127, weekly Sharpe 3.48 (x1.5: +0.168 R, PF 1.51, total +855.1 R, worst week -14.1 R, drawdown 24.5 R, run 4 weeks, weekly Sharpe 3.23). "
         "Earlier in-sample years, which did not pick the changes (2,770 trades; F1 ETH H2 absent there): at the old swing +0.182 R per trade, total +502.9 R, worst week -7.7 R, drawdown 20.5 R, run 6 weeks, weekly Sharpe 2.40 against 2.41 unchanged; at a constant stake +0.227 R, total +628.1 R, worst week -9.0 R, weekly Sharpe 2.36.")
EUR_BEFORE = ("15.15 euros earned per 100 euros risked (entries 2018-02..2021, 5,205 trades, FP costs); 13.66 with costs x1.5; 17.61 on the earlier in-sample years (2,758 trades). For reference, the same unchanged rules earned about 8 per 100 on 2022-2025.")
EUR_AFTER = ("21.22 per 100 risked at a constant stake (5,102 trades, FP; 19.65 with costs x1.5), part of it from larger positions and longer holds; 18.13 at the old weekly swing (16.75 with x1.5). On the earlier in-sample years: 22.68 at a constant stake, 18.15 at the old swing against 17.61 unchanged, with no gain per unit of swing. Expected out of sample: close to the unchanged rules (about 8 per 100 on 2022-2025); the target needs about 35.")

out = {
    "written": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "what": "Lead synthesis A of PROTOCOL_V3 Addendum H, lenses path, payoff and entry and their independent attacks (including the supplementary payoff round of the 13:15 UTC clarification, results/r2/autopsy/complement_verdicts.json). In sample only.",
    "in_sample_discipline": "Frames read with the parquet row filter ts < 2022-01-01; official trades and the lens's stored trades read with entry_time < 2022-01-01 in the same call; the nq leader from the in-sample us100 slice; nothing dated 2022 or later was simulated or looked at; results/val_access.log was not written; synthesis_B.json was not read. The official in-sample rows hold two trades entered on 2021-12-31 (donch4h_stop, orb) whose recorded exits fall in 2022: their R entered only the rule-2 total comparison and they are excluded from every statistic.",
    "baseline_reproduction_rule2": rule2,
    "crosscheck_against_the_lens_stored_trades": crosscheck,
    "trials": {"simulation_runs": n_sim, "portfolio_assemblies": n_asm, "trials_jsonl_lines": len(TRIALS),
               "declared_budget": "30 simulation runs + 26 assemblies; no re-run was needed",
               "truncation_checks": "330 (150 inside-trade cuts, 150 after-exit cuts, 30 H2 decision cuts), 0 mismatches; the gold test was run twice (the first draw had only 15 donch trades because every donch exit is a stop or trail; the second draws 30), both with 0 mismatches",
               "lens_and_verifier_trials_behind_this_synthesis": "path 120 variants, payoff 120, entry 120, plus the verifiers' own declared runs"},
    "loss_composition_main_fp": LOSS,
    "summary_for_the_user_fr": SUMMARY_FR,
    "portfolio_in_sample_before": BEFORE,
    "portfolio_in_sample_after": AFTER,
    "earned_per_100_risked_before": EUR_BEFORE,
    "earned_per_100_risked_after": EUR_AFTER,
    "where_the_losses_come_from": where,
    "users_claims": {
        "cut_at_once_a_trade_that_goes_hard_the_wrong_way": "does not pay on these rules (see where_the_losses_come_from[5])",
        "let_the_winner_run": "pays a little on some sleeves in 2018-2021, mostly as longer exposure; not established per unit of swing on the earlier years (see where_the_losses_come_from[6])"},
    "keep_rule": DECL["keep_rule"],
    "verdicts_classified": DECL["verdicts_classified"],
    "changes_that_survive": survive,
    "changed_sleeves_detail": sleeves,
    "truncation_tests": TRUNC,
    "portfolio": portfolio,
    "criteria_rehearsal_in_sample": REH,
    "ideas_that_do_not_work": ideas,
    "proposed_validation_look": decl_text,
    "caveats": CAVEATS,
    "frozen_files_sha256": FROZEN,
    "files": sorted([os.path.join(HERE, f) for f in ("declared.json", "synth.py", "portfolio.py", "truncation.py", "rehearsal.py",
                                                      "build_synthesis.py", "trials.jsonl")] +
                    [os.path.join(WORK, f) for f in ("portfolio.json", "criteria_rehearsal.json", "loss_composition_main_fp.csv")] +
                    sorted(glob.glob(os.path.join(WORK, "truncation_*.json"))) + [os.path.join(WORK, "<name>__<sym>__<variant>__<mode>.parquet (30 trade files)")]
                    + [OUT]),
}
json.dump(out, open(OUT, "w"), indent=1, default=str)
print("written", OUT, os.path.getsize(OUT), "bytes;", n_sim, "simulations,", n_asm, "assemblies")
