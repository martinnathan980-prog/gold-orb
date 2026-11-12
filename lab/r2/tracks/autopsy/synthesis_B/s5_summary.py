"""synthesis_B step 5: writes lab/results/r2/autopsy/synthesis_B.json from out/*.json (this synthesis's own runs), the
texts below (findings, kept / dropped changes, the declaration of the single 2022-2025 look, the summary for the user)
and the verifiers' figures quoted in them. Reads nothing dated 2022 or later.

    NUMBA_CACHE_DIR=/tmp/numba_synthesis_B PYTHONDONTWRITEBYTECODE=1 python3 s5_summary.py
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

D = os.path.dirname(os.path.abspath(__file__))

LOSSES = [
    "Losses are full stops near -1 R, not a fat tail. Ten sleeves, entries 2018-02-01..2021-12-31, FP costs, 5,205 trades "
    "(my re-simulation): 2,864 lost (55 %), average loss -0.65 R, gross loss 1,853 R against a gross gain of 2,642 R "
    "(+788.6 R net). 1,337 losses at the initial stop made -1,358 R (73 % of the gross loss), 1,417 at the clock exit "
    "-432 R, 110 at donch4h's trailing stop -63 R. Only 16 of the 2,864 losses were worse than -1.1 R (worst -1.49 R), "
    "and the worst tenth of the losing trades makes 16 % of the gross loss: there is no 'one big loss' beyond the stop.",
    "Sleeve by sleeve the size of a loss is set by the rule's stop and clock (same window, FP): orb_asia gold -0.99 R per "
    "losing trade (319 losers, 94 % of them full stops, 98 % of its gross loss); ocm4 -0.90 R (291; 83 %, 93 %); brk72 and "
    "F1 on btc and eth -0.73 to -0.74 R (260-300 losers each; 55-61 % full stops, 76-84 % of the gross loss); donch4h "
    "-0.59 R (115, mostly the trailing stop); noise30 -0.44 R (481, 405 at its band or clock exit); nq_btc_follow -0.37 R "
    "(451, 377 at its 60-minute clock); GOLD_FRI_PM -0.16 R (96, never stopped), and flat overall: -0.007 R per trade, "
    "-1.3 R on 183 trades.",
    "The gains come from a few large winners: the best 5 % of the trades carry 144 % of the ten sleeves' total R (orb gold "
    "548 %, ocm4 196 %, noise30 156 %, nq 135 %, crypto breakouts 89-108 %); without them the portfolio loses. The median "
    "winner peaks at +1.2 R and closes at +0.65 R.",
    "The user's first claim does not hold on these rules: cutting at once a trade that starts hard the wrong way loses "
    "money. 19 % of the winners (about 440 trades, 2018-02..2021-12, FP) first went at least 0.5 R against them; together "
    "they made +577 R, 73 % of the ten sleeves' total (ocm4: 37 % of its winners, +89 R; orb gold: 40 %, +106 R; F1 btc: "
    "26 %, +97 R). The quick check (all in-sample years, 7,965 trades, FP): closing a trade that shows -0.25 R or worse "
    "after 5, 15, 30, 60 or 120 minutes costs 98, 231, 180, 84 and 68 R (574 to 930 trades cut, 131 to 211 future winners "
    "killed); at -0.5 R it costs 4 to 28 R; only at -0.75 R does it sometimes save a little (+1.8 to +5.0 R at 3 of 5 "
    "checkpoints, 29 to 47 trades; -3.0 and -5.0 R at the other two). The rest of a trade still earns on average in every "
    "state bucket except the deepest (below -0.75 R: -0.17 to +0.11 R on 29 to 49 trades per checkpoint) and, at 5 "
    "minutes only, the trades already 0.5 R ahead (-0.06 R on 220).",
    "The user's second claim is already built into the rules: they let winners run to the clock exit or the trailing stop, "
    "and the earlier tracks found that taking profits sooner costs money (targets at 0.5 R kept 6-25 % of the expectancy, "
    "break-even at +1 R changed it by -36 % to +7 %) and that adding to winners gave nothing. Only 9.5 % of the losers had "
    "been 1 R ahead (22-23 % on ocm4 and orb gold). Holding winners even longer looked better on 5 of the 10 sleeves in "
    "the payoff lens's in-sample table (trades 1 R ahead held two more sessions: ocm4 +0.11 -> +0.25 R per trade, F1 eth "
    "+0.20 -> +0.41, F1 btc +0.34 -> +0.45, brk72 eth +0.21 -> +0.30, brk72 btc +0.26 -> +0.30) and worse or equal on "
    "noise30, orb gold, nq and GOLD_FRI_PM. Those are the lens's own figures before its attacks; they are judged in the "
    "other synthesis, not here.",
    "When the signals lose (context lens, baseline trades, FP): breakouts taken just after their own volatility unit has "
    "expanded earn much less (highest vs lowest third of vol / 60-day median: brk72 btc +0.07 vs +0.62 R per trade, brk72 "
    "eth -0.06 vs +0.57, F1 btc +0.09 vs +0.77, F1 eth +0.07 vs +0.36, donch4h -0.01 vs +0.39, orb +0.13 vs +0.44), and "
    "crypto breakouts with a stop wide in % of the price lose (brk72 eth widest third -0.18 R per trade on 173 trades, "
    "negative in each year 2018-2021). Clock: nq signals at 09:30-09:46 New York -0.002 R per trade (359), noise30 checks "
    "at 12:00-15:30 -0.003 (547) against +0.10 at 10:00-10:30; Friday entries +0.08 R (1,149) against +0.16 to +0.22 on "
    "Monday-Thursday; entries after 12:00 New York +0.04 R (1,199) against +0.19 (cluster lens).",
    "But those weak contexts are mostly less profitable, not losing, so skipping them rarely pays: in the training years "
    "the high-volatility third of the crypto breakouts still earned +0.04 to +0.33 R per signal; 69 of the 109 declared "
    "filters and models skipped nothing out of fold, and the 31 that acted lost 144.5 R together. One filter survived "
    "(the ETH stop width, K1).",
    "Losses that come together (cluster lens): inside a sleeve a loss does not make the next one more likely (8 of 10 "
    "sleeves |z| <= 1.35; brk72 btc and eth alternate). On one market and one day they do come together (us100: 130 days "
    "with two or more red sleeves against 106 expected, p 0.0005; noise30 and ocm4 daily correlation 0.52), and bitcoin "
    "with ether correlate 0.54 per day (every other pair of markets -0.03 to +0.04). The 10 worst days (-61 R) each had 5 "
    "to 8 red sleeves on 3 to 4 markets. Yet trades opened while another sleeve held the same side of the same market "
    "earned more (+0.24 against +0.14 R), so all 29 guards failed: the best raised the expectancy by 14.7 % while lowering "
    "the total by 9.5 %.",
    "Elsewhere (breadth lens), costs kill most transfers: 117 of 126 new rule x instrument pairs fail; 29 have a gross PF "
    "of 1.15 or more but only 10 keep it after FP costs (GOLD_FRI_PM on FX gross 1.20, net 0.81; nq on 40 shares gross "
    "1.05, net 0.67). The strong passes are crypto trend rules (orb and donch4h on btc and eth), whose profit comes mostly "
    "from positions held over the weekend.",
    "The edge fades with time: the ten sleeves made +0.19, +0.15, +0.21 and +0.07 R per trade in 2018, 2019, 2020 and "
    "2021 (FP, 1,224 to 1,437 trades a year); every crypto sleeve was weakest in 2021; on 2022-2025 the ten average "
    "+0.08 R per trade (task figure, not read here).",
]

KEPT = [
    {"sleeve": "brk72_24h_wd on ethusd (existing sleeve)",
     "change": "K1 (context-ETH-brk72-riskbp): skip a signal when the rule's own 3 x ATR24 stop is at least T(Y) basis "
               "points of the price (riskbp = 10,000 x stop / mid price of the last bar before the decision). T is "
               "refitted every 1 January on the sleeve's earlier signals (each taken alone, FP costs, decided before "
               "1 January minus 7 days; terciles; the losing side is skipped only if it lost): 505.9 bp in 2019, 496.7 "
               "in 2020, 465.1 in 2021, 478.3 for 2022. A skipped signal does not block the next one. Rule and "
               "parameters otherwise unchanged.",
     "effect_in_sample": "My re-run, identical to the author's and the verifier's, FP costs: 2019-2021 (its out-of-fold "
                         "years) 395 -> 304 trades, +0.124 -> +0.210 R per trade, +49.1 -> +63.9 R (+14.8 R), win rate "
                         "43.8 -> 48.4 %, average loss -0.70 -> -0.72 R (not smaller: it removes trades, it does not "
                         "shrink losses); costs x1.5 +40.9 -> +56.4 R. By year +11.2 -> +16.5, +36.2 -> +34.6, +1.7 -> "
                         "+12.8 R. Whole window 2018-02..2021-12: 511 -> 420 trades, +0.209 -> +0.289 R per trade, "
                         "+106.6 -> +121.4 R (2018 unchanged, no fold). 103 baseline trades removed (-20.8 R), 12 new "
                         "ones (-6.0 R). Truncation test: 30 of 30 decisions identical.",
     "verdict_of_the_attack": "weakened. Causal; holds with costs x1.5 and x2, one-minute delays, the 3-spread rule and "
                              "the weekend-gap control. But 11.1 of the 14.8 R come from 2021, whose skip exists only "
                              "because 2018 is in the expanding training window (rolling windows skip nothing in 2021); "
                              "the total-R gain's 90 % interval is -2 to +31 R; no null test stays below 5 % once the "
                              "lens's 109 variants are counted. Verifier's remaining effect: +0.03 to +0.06 R per trade, "
                              "+4 to +9 R over 2019-2021 (1.5 to 3 R a year), possibly zero."},
    {"sleeve": "NEW sleeve: orb_asia_2d_buf10 (frozen gold rule) on ethusd",
     "change": "K2 (breadth B1): the gold Asian-range breakout, parameters unchanged (range 00:00-07:00 London, stop "
               "entries at the range high/low plus 10 % of its width until 12:00 London, stop at the opposite level, exit "
               "16:00 New York two business days later, one position, held through weekends), traded on ethusd.",
     "effect_in_sample": "My run, FP, entries 2018-02..2021-12: 344 trades, win rate 41 %, average win +2.48 R, average "
                         "loss -0.98 R, +0.452 R per trade, PF 1.79, +155.5 R; by year +70.9 / +33.9 / +32.0 / +18.6 R; "
                         "costs x1.5 +0.408 R per trade, +140.3 R; no order refused by the 3-spread rule. One trade "
                         "still open at the end of 2021 is excluded (the lens counted it: 345 trades, +156.0 R). "
                         "Truncation test: 20 of 20 orders identical.",
     "verdict_of_the_attack": "weakened. Causal and broad (all 15 neighbouring settings positive every year), robust to "
                              "delays and costs; but the edge per trade halves from 2018-2019 (+0.695) to 2020-2021 "
                              "(+0.263, t 1.7), 2021 +0.196 (t 0.9); 72 % of its R comes from trades held over the "
                              "weekend; run as the current hands would (entry one minute late, everything closed Friday "
                              "16:50 New York) +0.363 R per trade, +142.1 R on 392 trades (x1.5 +0.326, +127.9 R); its "
                              "excess over random timing is not significant once the 126 pairs are counted; ethusd would "
                              "carry three sleeves for two slots (30 entries refused, -7.6 R). Verifier's judgement: "
                              "+0.15 to +0.25 R per trade forward."},
    {"sleeve": "NEW sleeve: orb_asia_2d_buf10 (frozen gold rule) on btcusd",
     "change": "K3 (breadth B2): the same frozen rule, unchanged, traded on btcusd.",
     "effect_in_sample": "My run, FP, entries 2018-02..2021-12: 375 trades, win rate 38 %, average win +3.01 R, average "
                         "loss -1.00 R, +0.518 R per trade, PF 1.84, +194.3 R; by year +93.6 / +68.3 / +32.1 / +0.4 R; "
                         "costs x1.5 +0.496 R per trade, +185.6 R; no order refused; one trade open at the end of 2021 "
                         "excluded (lens: 376, +194.7 R). Truncation test: 20 of 20 orders identical.",
     "verdict_of_the_attack": "weakened. Real but fragile: 2020-2021 +0.163 R per trade (t 1.0), 2021 +0.007; at the "
                              "bid/ask actually quoted in 2018-2020 (116-181 bp) only +0.05 R per trade; 19 trades make "
                              "all the profit; with the hands' Friday close 2021 turns negative; weekly correlation 0.40 "
                              "with the ethusd pair (largely the same bet). Verifier's forward estimate: at most +0.10 to "
                              "+0.16 R per trade, zero plausible."},
]

DROPPED = [
    "B3 donch4h_stop on ethusd (weakened, still positive: +0.220 R per trade, +53.2 R on 242 trades with costs x1.5, "
    "one-bar delays and the Friday close) is not carried: on ethusd the orb pair keeps the larger total-R gain after the "
    "attacks (+127.9 R under costs x1.5, late entry and the Friday close), ethusd already has two sleeves for two slots, "
    "and donch4h ethusd is largely the same bet (weekly correlation 0.49 with brk72 ethusd). For information (P3, FP): "
    "adding it too gives 6,056 trades, +0.203 R per trade, +1,226.5 R, worst week -17.2 R, drawdown 36.2 R.",
    "B4 brk72_24h_wd on jp225: refuted. 2013-2021 +0.018 R per trade (1,151 trades, t 0.59); a one-minute entry delay "
    "drops its PF to 1.13; random-entry null at the 92nd percentile; its 10 best trades make more than its total.",
    "B5 donch4h_stop on us100: refuted. Random timing with the same structure passes the same bar 22 % of the time; 17.7 "
    "of its 18.7 R come from 5 trades; 2013-2021 +0.028 R per trade; -2.45 bp per trade net (positive in R only).",
    "B7 F1_brk_ridge_filter on xagusd: refuted. With the walk-forward scorecard the protocol requires: +0.030 R per trade, "
    "PF 1.08, -1.75 R with costs x1.5; the filter's lift on silver is 0.000 R.",
    "B6 donch4h_stop jp225, B8 donch4h_stop btcusd, B9 ocm4 btcusd passed the breadth bar but were never attacked, so "
    "they cannot be kept (B8 is a near-duplicate of brk72 btcusd, weekly correlation 0.72; B9 lowers the portfolio's "
    "weekly Sharpe by 0.12).",
    "Cluster lens: none of 29 portfolio guards and adaptive rules raised the expectancy by 20 % (common window, FP): one "
    "position per market and side -3 to -20 % per trade; pausing a sleeve after 2-5 losses -4 to -15 %; no new entry on "
    "a market after one loss that day +14.7 % per trade but -9.5 % total; weights by trailing results +3.7 to +13.1 % "
    "(mostly a fixed tilt to the best in-sample sleeves); trading a sleeve only while its trailing result is positive "
    "+0.5 to +7.6 % at a lower total; daily lock at -4 R +2.2 %; no entry the day after a day at -2 to -4 R +0.6 to "
    "+2.8 %; pausing the portfolio after 4-8 losses -0.5 to -2.5 %. Trades removed by these guards earned as much as "
    "those kept, or more.",
    "Context lens: volatility-regime filters skipped nothing out of fold on the crypto and orb sleeves (donch4h +0.146 -> "
    "+0.226 R per trade but worse in 2018-2019 and its neighbours fail); hour-of-day filters (noise30 +14 % per trade, "
    "total 87.0 -> 84.1 R); trend alignment (orb +0.069 -> +0.027); a ridge model on 8 descriptors (F1 eth +27 % but "
    "+17.7 % with costs x1.5; orb and nq lower); a pause after the previous result (brk72 eth +86 % but 2021 worse); "
    "spread / stop on the other sleeves (brk72 btc +11 %). 330 variants, one passed (K1).",
    "Breadth lens beyond its qualifiers: noise30 on 14 other instruments (0 pass; on FX it loses even before costs, net "
    "PF 0.72), ocm4 on 15 (1 weak, B9), GOLD_FRI_PM outside gold on 11 (0; gross 1.20 on FX, net 0.81), nq_btc_follow "
    "with 54 other followers (0; shares net PF 0.66), F1 on 12 (1, refuted), brk72 on 7 indices and metals (1, refuted), "
    "orb on 5 indices (0), donch4h on us500 and us30 (0).",
    "The user's rule 'cut at once' (quick check): closing at -0.25 R or -0.5 R at any of five checkpoints from 5 to 120 "
    "minutes loses 4 to 231 R over 2013-2021; it does not pay on these rules.",
]

VAL_LOOK = (
    "DECLARATION of one look at 2022-2025 (synthesis_B, written 2026-11-12 before any 2022+ row is read; run once by the "
    "lead; every read logged in results/val_access.log, track 'autopsy_synthesis_B'). "
    "FROZEN. (1) K1, brk72_24h_wd on ethusd: rule and parameters unchanged (n 72, stop 3 x ATR24, exit 24 h after the "
    "decision, weekdays UTC, FP-hours exit wrapper of r2/recalc.py, one position). A signal decided at D is skipped when "
    "riskbp = 10,000 x stop_dist / P >= T(Y), P being the mid close of the last M1 bar starting before D. T(2022) = "
    "478.28 bp (fitted now on the 2,345 in-sample signals decided before 2021-12-25: E_hi -0.131, E_lo +0.342 R). T(2023), "
    "T(2024) and T(2025) are refitted on each 1 January by the same procedure (every signal taken alone with FP costs; "
    "signals decided before 1 January Y minus 7 days; terciles, q = 1/3; the worse side is skipped only if "
    "min(E_lo, E_hi) < 0, otherwise nothing). A skipped signal never blocks a later one. (2) K2 and K3: "
    "orb_asia_2d_buf10 with FINALISTS['orb_asia_2d_buf10'] of lab/tracks/orb/strategy.py, unchanged, as new sleeves on "
    "ethusd and on btcusd, one position each, held through weekends as specified. (3) The other nine sleeves unchanged. "
    "(4) Costs: r2.costs(sym) and the FP frames as they are today, and costs x1.5 (spread and slippage, orders rebuilt); "
    "an order whose stop is closer than 3 spreads of its fill bar is not taken. (5) Frames from their start to "
    "2025-12-31 23:59 UTC (warm-up from in-sample bars), trades entered 2022-01-01..2025-12-31; nothing from 2026. If the "
    "other synthesis carries a change for brk72_24h_wd ethusd, only one of the two (the larger total-R gain after its "
    "attacks) enters this look, chosen before it is run. "
    "COMPARED. (a) brk72_24h_wd ethusd with the skip against the same sleeve without it (both chains re-simulated, one "
    "position), and the skipped signals taken alone against the kept ones; (b) each new sleeve on its own; (c) the ten "
    "unchanged against the ten with K1, K2 and K3, with the metrics of this synthesis (trades, R per trade, win rate, "
    "average win and loss, PF, total R, worst week, drawdown, longest losing run of weeks, mean / sd of R per trade), by "
    "year, FP and x1.5. "
    "CRITERIA, fixed now. K1 is adopted only if, on 2022-2025, the sleeve's expectancy per trade with the skip is higher "
    "than without and its total R is not lower, both with FP costs and with costs x1.5, and the skipped signals taken "
    "alone earn less on average than the kept ones. Each new sleeve is adopted only if, with FP costs, PF >= 1.06, "
    "expectancy > 0, every-signal expectancy > 0, total R positive in at least 3 of the 4 years, and expectancy > 0 with "
    "costs x1.5; and the weekly mean / sd of R of the ten plus that sleeve is at least that of the ten alone. Read beside "
    "it, for the robot as it is (not a criterion of the rule): the same sleeve with entry one minute late and every "
    "position closed on Friday at 16:50 New York; if that version has expectancy <= 0, the sleeve waits for a robot that "
    "holds it over the weekend. Expectations declared now (the verifiers' estimates, not targets): K1 +0.03 to +0.06 R "
    "per trade on about a quarter fewer ETH brk72 trades, possibly zero; orb ethusd +0.15 to +0.25 R per trade; orb "
    "btcusd +0.10 to +0.16, possibly zero. A failure is final: nothing is re-tuned, re-declared or looked at again."
)

SUMMARY_FR = (
    "Couper tout de suite un trade qui part mal ne paie pas avec ces règles : cela fait perdre.\n"
    "2018-2021 : un gagnant sur cinq a d'abord été en perte de la moitié de sa mise ; ces trades ont fait 73 % du gain.\n"
    "Couper à -25 % de la mise après 5 minutes aurait coûté 98 mises sur 2013-2021.\n"
    "Laisser courir les gagnants : les règles le font déjà ; 5 % des trades font plus que tout le gain.\n"
    "Les pertes sont surtout des stops pleins (73 % des pertes), presque jamais plus d'une mise.\n"
    "Après les contrôles, trois changements restent, tous affaiblis par les attaques.\n"
    "Ether, cassure : sauter le signal si le stop dépasse environ 4,8 % du prix ; gain attendu +0,03 à +0,06 mise par trade, peut-être zéro.\n"
    "La règle « Asie » de l'or ajoutée sur ether et bitcoin : forte en 2018-2019, faible en 2020-2021, bitcoin nul en 2021.\n"
    "Portefeuille 2018-2021 : 15 € gagnés pour 100 € risqués avant, 20 € après, surtout grâce aux deux règles ajoutées.\n"
    "Pire semaine : -13 mises avant, -17 après. Et ce sont les années qui ont servi à bâtir les règles : c'est optimiste.\n"
    "En 2022-2025 les règles font 8 € pour 100 € risqués ; il en faudrait 35 pour doubler en un mois : on en reste loin.\n"
    "Prochaine étape : un seul test sur 2022-2025, déclaré d'avance, avant toute décision."
)

CAVEATS = [
    "In sample only (entries before 2022, frames cut while read) and optimistic by construction: every figure comes "
    "from the years that built the rules, and the kept changes were selected from 330 (context) + 29 (cluster) + 126 "
    "(breadth) lens trials. No 2022+ row was read; the validation look is declared, not run.",
    "The portfolio's in-sample gain (P0 -> P2: +0.152 -> +0.198 R per trade) comes mostly from adding the two orb crypto "
    "sleeves, i.e. more trades of a rule that was strong in 2018-2019, not from better trades of the ten: K1 alone moves "
    "the ten from +0.152 to +0.157 R per trade. On 2020-2021 alone the mean / sd of R per trade is 0.107 without and "
    "0.106 with the changes.",
    "K1 rests on its 2021 fold, which skips only because 2018 is in the expanding training window; once the context "
    "lens's search is counted, no null test puts it below 5 %.",
    "The orb crypto sleeves: edge per trade halved between 2018-2019 and 2020-2021 (bitcoin about zero in 2021); 72-83 % "
    "of their R comes from positions held over the weekend, which the current hands close on Friday 23:50 server; ethusd "
    "would carry three sleeves and btcusd four for two positions per symbol (30 and 27 entries refused in the verifiers' "
    "runs); orb btcusd was not tradable at the 2018-2020 quoted spreads (+0.05 R per trade there); the two pairs are "
    "largely the same bet (weekly correlation 0.40) and correlate with the existing crypto sleeves; the ethusd FP spread "
    "is marked uncertain.",
    "Ideal constant-stake account: 1 R per trade, no compounding, no minimum lot, no cap on simultaneous positions (the "
    "cluster lens's caps 6 / 2 remove 329 trades, -4.7 R, from the ten). The worst week grows from -12.5 to -16.9 R and "
    "the drawdown from 29.1 to 32.1 R because there are more trades; per unit of swing (weekly mean / sd 0.40 -> 0.46) "
    "it is better, in sample.",
    "One trade per new sleeve still open at the end of 2021 is excluded (the lens counted it): 344 instead of 345 trades "
    "on ethusd, 375 instead of 376 on btcusd (-0.5 and -0.3 R); the gold donch4h and orb trades entered on 2021-12-31 are "
    "excluded the same way.",
    "The statements about holding winners longer quote the payoff lens's in-sample table before its attacks; those "
    "candidates (and the path and entry lenses) are judged in the other synthesis. If it keeps a change for "
    "brk72_24h_wd ethusd, at most one change may go forward on that sleeve.",
    "The FP frames' spread uses a day-median shape that is not causal; K1's descriptor does not use the spread, but its "
    "training labels and every simulated fill do (the verifier bounds the effect at about 0.03 R for wide stops).",
    "The F1 sleeves' in-sample results are inflated (their scorecard was fitted on these years); this flatters P0 and P2 "
    "alike.",
    "Trials of this synthesis: 9 declared variant lines (R0, C1, N1, N2, I3, P0-P3), each in FP and x1.5, plus 2 "
    "truncation tests and 1 descriptive anatomy; nothing tuned. One change to the declaration before it ran (two "
    "provisional bars in T1), recorded in declared_addendum.json.",
    "During this session another job (track stake, growth paths) appended lines to results/val_access.log; none of them "
    "comes from this synthesis, whose code never calls a validation cut.",
]


def main():
    s1 = json.load(open(os.path.join(C.OUT, "s1_info.json")))
    s2 = json.load(open(os.path.join(C.OUT, "s2_portfolio.json")))
    s3 = json.load(open(os.path.join(C.OUT, "s3_truncation.json")))
    keys = ("n", "exp", "eur_per_100_risked", "win", "avg_win", "avg_loss", "pf", "total", "worst_week_R",
            "max_dd_R_trade_by_trade", "max_dd_R_weekly", "longest_losing_run_weeks", "mean_over_sd", "sd",
            "week_mean_over_sd", "weekly_sharpe_annualised", "winning_weeks_pct", "worst_day_R", "by_year",
            "half_2018_02_2019_12", "half_2020_2021", "by_sleeve")
    port = {mode: {p: {k: s2[mode][p][k] for k in keys} for p in ("P0", "P1", "P2", "P3")} for mode in ("fp", "stress")}
    repro = {k: {kk: v[kk] for kk in ("n_mine", "n_official", "totR_mine", "totR_official", "rows_differing",
                                      "official_exits_in_2022", "reproduced", "differing")}
             for k, v in s1.items() if not k.startswith("frame") and "reference" in v}
    out = {
        "what": "PROTOCOL_V3 Addendum H, synthesis_B: lead analyst for the lenses context, cluster and breadth. In sample "
                "only (entries before 2022-01-01; price frames read with ts < 2022-01-01; official trades with "
                "entry_time < 2022-01-01). No validation look.",
        "first_check_rule2": {"all_ten_reproduced": all(v["reproduced"] for v in repro.values()), "per_sleeve": repro,
                              "note": "8 sleeves identical row by row; donch4h_stop and orb_asia_2d_buf10 identical except "
                                      "the trade entered on 2021-12-31, open at the end of the slice (excluded)"},
        "where_the_losses_come_from": LOSSES,
        "user_claim": {
            "cut_at_once_a_trade_that_goes_hard_the_wrong_way": "does not pay on these rules (see where_the_losses_come_from[3])",
            "let_run_the_one_that_goes_well": "already done by the rules; holding winners longer looked better on 5 of 10 "
                                              "sleeves in the payoff lens's unattacked in-sample table (judged in the "
                                              "other synthesis)",
            "anatomy_ten_sleeves_fp_window": s2["anatomy_fp"]},
        "kept_changes": KEPT,
        "dropped": DROPPED,
        "sleeve_runs": {"C1_K1_riskbp_brk72_ethusd": s1["C1_brk72_24h_wd_riskbp__ethusd"],
                        "N1_K2_orb_ethusd": s1["N1_orb_asia_2d_buf10__ethusd"],
                        "N2_K3_orb_btcusd": s1["N2_orb_asia_2d_buf10__btcusd"],
                        "I3_info_donch4h_ethusd": s1["I3_donch4h_stop__ethusd"]},
        "portfolio": {"window": s2["window"], "stake": s2["stake"],
                      "sets": {"P0": "ten unchanged", "P1": "ten with K1", "P2": "ten with K1 + K2 + K3 (kept)",
                               "P3": "information only: P2 + donch4h_stop ethusd (dropped B3)"},
                      "weeks": "FP server weeks (New York + 7 h, Monday-Sunday) booked at the exit; empty weeks = 0",
                      "max_dd": "trade by trade on the cumulative R in exit order, and on the weekly sums",
                      "results": port},
        "truncation": {k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in s3.items()},
        "proposed_validation_look": VAL_LOOK,
        "summary_for_the_user_fr": SUMMARY_FR,
        "caveats": CAVEATS,
        "trials": {"this_synthesis_variant_lines": 9, "file": os.path.join(D, "trials.jsonl"),
                   "lens_trials": {"context": 330, "cluster": 29, "breadth": 126}},
        "files": [os.path.join(D, f) for f in ("declared.json", "declared_addendum.json", "trials.jsonl", "common.py",
                                               "s1_run.py", "s2_portfolio.py", "s3_truncation.py", "s4_trials.py",
                                               "s5_summary.py", "out/")] + [C.RESULT],
    }
    C.jdump(out, C.RESULT)
    print("written", C.RESULT)


if __name__ == "__main__":
    main()
