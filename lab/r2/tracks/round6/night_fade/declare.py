"""Writes results/r2/round6/night_fade/declared.json BEFORE any return of night_fade is computed (PROTOCOL_V3 Addendum L).

It copies the frozen text of Addendum L (checked identical to the text committed in d7009aa, read-only git), lists the
seven configurations exactly as the addendum names them, the crosses kept by the coverage pre-check (precheck.json), and
every reading of a detail the text leaves open (READINGS L1..L34, decided from the text, the design record committed with
it and Addendum K's implementation). It records the sha256 of every code file (run.py, null.py, correlation.py,
verdict.py and handcheck.py refuse to run if one changed), of the twelve frames, of the design record and of the pre-run
evidence (precheck, synthetic, truncation and entry-side hand check). No price is read here and nothing is simulated.
The sha256 of declared.json is written next to it (declared.sha256).

    python3 -I declare.py      # once, after the review of the code and of the pre-run evidence
"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import pandas as pd  # noqa: E402

REPO = os.path.dirname(C.LAB)
PROTO = os.path.join(C.LAB, "PROTOCOL_V3.md")
COMMIT = "d7009aa"
HEAD = "## Addendum L (2026-11-14; written BEFORE any run)"
OUT = os.path.join(C.OUT, "declared.json")
SHA_FILE = os.path.join(C.OUT, "declared.sha256")

READINGS = {
    "L1_in_sample_frames": (
        "Frames are built by frames.py from the 216 files of data/raw_r6 (2013-2021; no later file exists for the crosses). "
        "Each file is read with pyarrow.dataset and the row filter timestamp < 2022-01-01 00:00 UTC inside the read call "
        "(to_table(filter=...)); bid and ask are merged by prep_round3._merge itself (imported; its _read is replaced at call "
        "time by a reader with _read's semantics plus the filter: files in sorted order, duplicates keep the first, sorted), "
        "then prep_round3.fx's weekday rule ((New York time + 7 h).dayofweek < 5) is applied; the frame is written to "
        "data/r6/<cross>_m1.parquet. Every later read uses pandas.read_parquet(filters=[('ts', '<', 2022-01-01 UTC)]) and "
        "asserts max(ts) < 2022-01-01. goldlab.r2.load/run/evaluate/null_test and r2/tracks/fx/common.load_is are never "
        "used (whole-file reads; r2.costs has no crosses): the run calls goldlab.sim.simulate directly. The hand check reads "
        "the raw csv.gz with Python's csv module and skips rows >= 2022-01-01 in its read loop. results/val_access.log is "
        "hashed before and after the run and must be unchanged; lab/holdout_raw is never opened."),
    "L2_base_frame": (
        "The base frame is not stored: common.load_base builds it in memory from the merged frame: h = 0.5 x c x 1e-4 x "
        "(bc + ac) / 2 of the same M1 bar (before folding), bid - h and ask + h on open, high, low and close; c in bp of "
        "price round trip exactly as listed (0.5714 for the five EUR crosses, 0.5000 for the three GBP crosses, 0.9231 for "
        "AUDCAD and AUDNZD, 1.0000 for NZDCAD, 0.8571 for CADCHF). Every decision quantity (bars, bands, D, C, the refused-"
        "target check, H1 ranges) and every base fill is computed on this frame (reading a: on its x1.5 version). The fold "
        "leaves the mid unchanged up to the last bit of floating point."),
    "L3_calendar": (
        "Candidate evenings: New York dates E from Monday to Thursday, 2013-01-01 to 2021-12-30. Skipped, first reason "
        "counted: E from 24 December to 1 January inclusive; E an NYSE full holiday; E+1 one (idxus_lib.us_holidays(year)[0] "
        "minus SPECIAL_CLOSURES: 2018-12-05 is a normal day; half days are normal days). Result 1,753 evenings, 2013-01-02 "
        "to 2021-12-22 (48 / 52 / 26 Monday-Thursday dates skipped by these reasons). Clock times are New York wall clock "
        "(America/New_York, tz database); no daylight-saving switch falls on a Monday-Thursday evening."),
    "L4_tradable_evenings": (
        "A calendar evening is tradable for a cross when at least 480 H1 bars of that cross are completed at 17:15 New York "
        "(goldlab.data.bars(base, '1h'), start + 60 min <= 17:15), counted from the frame's first bar (2013-01-01 22:00 UTC "
        "or a few minutes later). There is no per-evening quote test: missing minutes act through the band's span rule, the "
        "5-minute entry rule and exit_index."),
    "L5_coverage": (
        "Before the run (precheck.json), a cross with at least one M1 bar starting in [17:15, 21:00) New York (merged frame, "
        "timestamps only) on fewer than 90 % of the 1,753 calendar evenings is dropped; declared.json lists the crosses kept. "
        "With crosses dropped, the basket bars use the crosses kept: crosses with a positive expectancy >= 65 % of the kept "
        "crosses rounded up (8 of 12 when none is dropped); the 25 % share bar is unchanged."),
    "L6_bars": (
        "Signal bars: goldlab.data.bars(frame, '5min') ('15min' for m15), clock buckets on the UTC grid (the New York grid: "
        "its offsets are whole hours), labelled by their start, a bucket with no M1 bar has no bar; mid close = (bc + ac) / 2 "
        "of the bucket's last M1 bar; bar end = bucket start + bar length (not goldlab's t_close); C = ac - bc of the bucket's "
        "last M1 bar. H1 bars: goldlab.data.bars(frame, '1h'), mid high = (max bh + max ah) / 2, mid low = (min bl + min al) / "
        "2, range = mid high - mid low, hours with no M1 bar absent."),
    "L7_band": (
        "For signal bar j: the 20 existing bars j-19 .. j (positions among existing bars, the signal bar included); mu = their "
        "mean, sigma = their population standard deviation (ddof 0), both from plain sequential sums over exactly these 20 "
        "values (so a band depends only on its 20 closes: truncation test, hand check). Usable only if bar j-19 starts at or "
        "after (end of bar j) - 120 minutes (360 for m15); fewer than 20 bars: not usable. Bands mu +/- band_k x sigma."),
    "L8_decisions": (
        "Decision times t_k = 17:15 + k x 5 minutes New York on E, k = 0..32 (main: 17:15 .. 19:55, 33 a night; first_hour "
        "9: 17:15 .. 17:55; m15: 17:15 + 15k, k = 0..10, to 19:45). The signal bar is the bar of the bucket [t_k - bar length, "
        "t_k); no bar, or a band not usable: no signal."),
    "L9_signal": (
        "Strict: buy if close < mu - band_k x sigma, sell if close > mu + band_k x sigma (band_k 2.0; 2.5 in width_2.5); "
        "equality is no signal, so sigma = 0 never signals. D = |close - mu|."),
    "L10_cost_filter": (
        "The signal is kept only if D >= 2.0 x C (equality kept), C of the frame the orders are built on (base: Dukascopy "
        "spread + c x mid; reading a: 1.5 x that)."),
    "L11_entry": (
        "Entry bar = the first M1 bar starting at or after t_k (goldlab.data.entry_index; a bar starting at t_k has delay 0). "
        "Dropped if there is none or it starts more than 5 minutes after t_k (exactly 5 is kept), or if its open already "
        "reached the target (buy: ask open >= mu; sell: bid open <= mu; quotes of the frame the orders are built on). A "
        "dropped order does not block later signals. Fill = goldlab.sim market entry (etype 0): ask open x (1 + 0.1 x 1e-4) "
        "for a buy, bid open x (1 - 0.1 x 1e-4) for a sell."),
    "L12_target": (
        "Target = mu of the signal bar, frozen as an absolute price (goldlab.sim 'target'): a resting limit without slippage, "
        "filled at the target, or at a better open when a later bar gaps through it (engine rule), possibly on the entry bar; "
        "stop first when stop and target are both touched in one bar (engine rule)."),
    "L13_stop": (
        "Stop distance = 2.0 (3.0 in stop_3.0) x the mean range of the 480 most recent H1 bars completed at the DECISION time "
        "t_k (start + 60 min <= t_k), set from the fill (goldlab.sim stop_dist) and fixed; filled at the stop with 0.3 bp of "
        "slippage, or at the worse open on a gap (engine rule). An order with a stop distance <= 0 is dropped (counted; none "
        "expected)."),
    "L14_time_exit": (
        "exit_i = goldlab.data.exit_index(frame, 21:00 New York of E, max_gap_min=30): the first bar starting at or after "
        "21:00 if it starts at most 30 minutes after it, else the last bar before 21:00; a market exit with 0.1 bp. An order "
        "whose exit bar is not after its entry bar is dropped (counted; none expected), as Addendum K did."),
    "L15_positions": (
        "goldlab.sim.simulate per cross with no_overlap=True: orders sorted by entry bar; an order whose entry bar is at or "
        "before the open trade's exit bar is skipped (no queue, no reversal, no adding); later orders of the evening trade on "
        "either side; crosses are independent; no cap across crosses or currencies (reported)."),
    "L16_swap_and_clock_asserts": (
        "Engine swap rates are 0. Asserted on every trade (common.check_trades): entry and exit in one trading day "
        "(goldlab.data.trading_day), the day E+1 its evening opens, so no 17:00 New York rollover is crossed and the swap is 0; "
        "entry at or after 17:15 and by 20:00 New York (20:05 for null replays, which may enter 5 minutes after a 20:00 "
        "clock time); exit by 21:30 New York; swap column 0; no end-of-data exit."),
    "L17_R": (
        "R = goldlab.sim pnl / risk = side x (exit fill - entry fill) / |entry fill - stop| (the engine's commission is 0 "
        "because the commission is in the quotes; swap 0)."),
    "L18_costs_x1.5": (
        "Frame = goldlab.sim.apply_spread_mult(base, 1.5) (each bar's close spread, commission included, x 1.5 around the "
        "mid, applied to its four prices: the lab's transform); slippage x 1.5 (0.15 bp market, 0.45 bp stop). Reading a: "
        "orders rebuilt on that frame: the filter sees 1.5 C and the refused-target check uses the widened open; the bands "
        "use the same mid closes up to the last bit, while the H1 ranges (and so the stop distances) are recomputed on the "
        "widened quotes and differ from the base frame's when the spread varies inside the hour (each minute is widened by "
        "its own close spread, so the bid and ask extremes can move by different amounts; Addendum K's attack found the "
        "same, I1). Reading b: the base order frame replayed through the same simulate call (no_overlap=True) on the "
        "widened frame, so the one-position rule acts on the stressed exits; fills already past the target follow the "
        "engine's first-bar rule and are counted. Bar: pooled PF >= 1.04 in both."),
    "L19_gross": (
        "The base order frame replayed on goldlab.sim.apply_spread_mult(base, 0.0) (each bar's close spread removed around "
        "the mid on its four prices: the lab's 'gross' frame of r2.run, which Addendum K called mid quotes; the open, high "
        "and low are the mid only where their own spread equals the close spread) with zero slippage, no_overlap=True: "
        "the gross bp of the base reading and of reading b (the same orders). Reading a's gross "
        "bp comes from its OWN rebuilt orders replayed the same way on the same gross frame (reading 'gross_a'), so every "
        "reading's cost bp is the gross bp of its own orders minus its net bp. Information only."),
    "L20_every_signal": (
        "Every order of the configuration (after the filters and entry checks, before the one-position rule), base costs, "
        "goldlab.sim.simulate no_overlap=False. Judged on the main only."),
    "L21_moving_mid": (
        "The main's orders (same drops) without a resting target; exit_i = min(21:00 exit bar, the first M1 bar starting at "
        "or after the end of the first usable M5 bar whose end is after the entry bar's start and whose mid close is >= "
        "(long) / <= (short) its own middle band); equality counts; with no such bar, the 21:00 exit. No gap rule applies to "
        "this moving exit: the text gives the 30-minute rule to the 21:00 exit only (which keeps it), and a 'last bar before' "
        "would take the exit price at the open of a minute whose own close is the trigger, before the exit signal exists. "
        "The exit bar therefore always starts at or after the trigger bar's end, which is after the entry bar's start, so it "
        "is always after the entry bar. Stop and 21:00 exit unchanged. These exits are counted apart (exit kind "
        "'moving_mid', L30)."),
    "L22_one_per_night": (
        "The earliest order (smallest decision time) of each cross and evening among the main's orders after all filters "
        "and entry checks; the later orders of that evening are not sent (status 'not_first_order_of_evening')."),
    "L23_m15": (
        "goldlab.data.bars(frame, '15min'), band period 20, span limit 360 minutes, decisions at the ends of the 15-minute "
        "buckets 17:15 .. 19:45 (11); C from the M15 bucket's last M1 bar; filter, entry, H1 stop and 21:00 exit unchanged."),
    "L24_other_neighbours": (
        "first_hour changes only the last decision (17:55: 9 decisions); width_2.5 only band_k (2.5); stop_3.0 only the "
        "stop multiple (3.0). first_hour's and one_per_night's orders are exact subsets of the main's orders."),
    "L25_drop_order": (
        "Counted in this order, the first failed test of a decision wins: no signal bar; band not usable; no band crossing; "
        "cost filter; entry more than 5 minutes late (or no bar); open already at the target; stop distance <= 0; exit bar "
        "not after the entry bar; (one_per_night: not the first order of the evening); then the engine's one-position skip."),
    "L26_criteria": (
        "Main only, base costs unless stated: n = pooled trades >= 250; PF on R (sum of positive R / |sum of negative R|; no "
        "trade 0; no loss inf) >= 1.12; t = mean / (sd ddof 1 / sqrt(days)) of the daily sums of R per goldlab.trading_day("
        "entry_time), days with a trade, >= 2.5; at least 6 of the 9 UTC entry years 2013-2021 with sum R > 0 (a year without "
        "a trade is not positive); pooled PF >= 1.04 in reading a AND reading b; crosses with mean R > 0 (no trade = not "
        "positive) >= ceil(0.65 x crosses kept) = 8 of 12; max over crosses of (cross sum R / pooled sum R) <= 0.25, a pooled "
        "sum <= 0 fails; numpy median of the six neighbours' pooled base PFs >= 1.06; every-signal expectancy > 0; max hold "
        "<= 192 h (goldlab.r2.is_criteria's 5 trading days); null percentile >= 97.5; |weekly rho with the sum of the ten| "
        "<= 0.30. Pass = all twelve. Every bar is read on the UNROUNDED figure ('<name>_raw' in run.json: pf, t_daily, "
        "expectancy_R, total_R, max_cross_share, max_hold_h; 'percentile_raw' in null.json; 'corr_with_sum_of_ten_raw' in "
        "correlation.json; the neighbours' median of their unrounded PFs); the rounded figures are for display only."),
    "L27_null": (
        "null.py: the main's base trades (trades_01_main_base.parquet); for each of 200 replays (numpy default_rng(0)), for "
        "each cross in basket order, rng.integers(0, n tradable evenings of the cross, size=(n trades of the cross, 20)), "
        "trades by entry time; a trade uses the first of its 20 candidate evenings whose first M1 bar at or after the New "
        "York clock time (hh:mm) of its entry bar starts at most 5 minutes late (none of 20: dropped and counted); same side; "
        "stop distance = (risk / entry fill) x the replay bar's mid open (bid open + ask open) / 2 of the base frame; target "
        "distance = ((target - entry fill) x side / entry fill) x that mid open, resting, none if <= 0; time exit at 21:00 "
        "New York of the drawn evening (exit_index, 30-minute rule; dropped and counted if not after the entry bar); base "
        "costs; no_overlap=False. Statistic: pooled mean R of a replay; percentile = 100 x share of the 200 means strictly "
        "below the main's pooled mean R."),
    "L28_correlation": (
        "correlation.py, exactly round5/gold_reopen/correlation.py's convention: the ten's official trades "
        "(results/r2/recalc/trades/{name}__{sym}.parquet) read with entry_time < 2022-01-01 in the read statement, exits in "
        "2022 dropped; weekly sums of R by W-SUN exit week (UTC), every week from the week of 2014-01-01 to that of 2021-12-31 "
        "(418), empty = 0; Pearson with the main's pooled base trades; also each cluster and sleeve; bar |rho| <= 0.30, read "
        "on the unrounded rho (correlation.py's 'pass' and the verdict)."),
    "L29_trials": (
        "results/r2/round6/night_fade/trials.jsonl: one line per configuration and cross (84) and one pooled line per "
        "configuration (7) = 91, each with the base, stress_a, stress_b, gross, gross_a and every-signal figures and the drop "
        "counts, whatever the result. run.py refuses to start if trials.jsonl exists and computes everything without "
        "printing a result; run.json and trials.jsonl are serialised in memory first; then run.json is written (atomically), "
        "then trials.jsonl once, in exclusive-create mode and atomically (a temporary file hard-linked to the final name, "
        "which fails if the name exists); then the val_access.log hashes, both recorded in run.json, must be equal. run.json "
        "records trials.jsonl's sha256 and line count, and verdict.py checks them. A failure before the writes leaves "
        "neither file (nothing was logged and the declared run can be started again)."),
    "L30_reported_conventions": (
        "pips = price difference / 0.0001; bp = of the entry fill; net bp from pnl / entry fill; gross bp from the gross "
        "replay of the reading's own orders (L19: 'gross' for base and reading b, 'gross_a' for reading a); cost bp = that "
        "gross bp - the reading's net bp; exits by the engine's reason and by kind (the engine's 'time' split into "
        "'time_21_00', the exit at the 21:00 exit bar, and 'moving_mid', a moving_mid market exit before it); target "
        "distance = |mu - entry fill|; winning days "
        "by trading day, weeks by W-SUN exit week (of weeks with a trade and of all weeks 2013-2021), months by exit month; "
        "worst evening = lowest daily sum; maximum drawdown on R cumulated by exit time; crosses open at once by a sweep over "
        "[entry, exit) (an exit frees its slot before an entry at the same minute); currency stacking: a long cross is long "
        "its base and short its quote; account check: 70 EUR (7 % of 1,000 EUR) at the stop per trade, quote and base "
        "currencies converted to EUR with the five EUR crosses' mid close at the entry, lots floored to 0.01 (a trade below "
        "0.01 lot reported with its real risk at 0.01), margin at 1:500, peak margin of all open trades; break-even extra "
        "cost per round trip x = sum R / sum(entry / risk) (bp of price, and as a multiple of the modelled cost); the named "
        "tail evenings listed with their R (all stay in the test)."),
    "L31_precheck": (
        "precheck.py (counts and costs only): close spread ac - bc of every M1 bar starting in [17:15, 21:00) and in [16:55, "
        "17:30) New York on the calendar evenings, Dukascopy spread from the merged frame and all-in cost from the base frame "
        "(spread + c x mid), median and 90th percentile in pips and in bp of the mid close, by cross and New York year; "
        "signals and drops = decision-table counts per configuration and cross on the base frame and on the x1.5 rebuilt "
        "frame; the moving_mid exits, stops and every exit are not computed before the run."),
    "L32_truncation": (
        "truncation.py: at least 50 decisions per cross (40 with a band crossing and 20 with a usable band and none, drawn "
        "with numpy default_rng(0), crosses in basket order) recomputed on the base frame cut at the decision time (rows with "
        "ts < t_k); mu, sigma, side, D, C, the filter result, the stop distance, has_bar and usable must be exactly equal."),
    "L33_hand_check": (
        "handcheck.py: the first main order of 2013, 2015, 2017, 2019 and 2021 = the earliest entry bar among the main's "
        "orders in that UTC year over the twelve crosses (ties in basket order); it is always a trade (every earlier trade of "
        "its cross exits by 21:30 of an earlier evening). Its entry side is recomputed from the raw csv.gz with independent "
        "code (own merge, calendar from the holidays package, M5 buckets and UTC hours by integer division, plain sums), "
        "scanning every cross's evenings of that year up to the engine's evening, before the run; its exit side after the run."),
    "L34_code_frozen": (
        "declared.json records the sha256 of every code file of lab/r2/tracks/round6/night_fade (every top-level .py file, "
        "asserted), of the twelve frames and of the pre-run evidence, whose recorded code hashes must equal the declared "
        "code; run.py, null.py, correlation.py, verdict.py and 'handcheck.py exit' refuse to run if a code file changed, "
        "and run.py and null.py also check the frames."),
}

# The independent review of the code and of the pre-run evidence (before this declaration) and what was done; each fix
# is proven by a synthetic case of test_synthetic.py (synthetic.json).
REVIEW_FIXES = {
    "R6-1 (major)": "moving_mid's exit took exit_index's 30-minute gap rule, which could put the exit at the open of the "
                    "minute whose close is the trigger (look-ahead): now the first M1 bar at or after the trigger bar's "
                    "end, no gap rule (L21); 21:00 exit unchanged. Proof: world A 2019-02-06 (exit 18:40, not 18:04), "
                    "worlds C and E (planted holes, a gap of more than 30 minutes).",
    "R6-2 (minor)": "the bars were read on rounded figures: every judged figure is now stored unrounded and the bars, the "
                    "neighbours' median and correlation.py's pass read the unrounded values (L26, L28). Proof: world D "
                    "(PF 1.119951, t 2.4997, share 0.25004, total +0.0004, median 1.059955, every-signal +2e-6, hold "
                    "192.0004 h, rho 0.30004) and world C's verdict.",
    "R6-3 (minor)": "reading a's gross and cost bp mixed two trade sets: reading a's own orders are now replayed on the "
                    "gross frame ('gross_a') for its gross and cost bp (L19, L30). Proof: worlds A and C.",
    "R6-4 (minor)": "the wording of L18 said reading a's H1 ranges had the same mids up to the last bit: reworded (the H1 "
                    "ranges and stop distances are recomputed on the widened quotes and can differ). Proof: world A (two "
                    "minutes: 42.4 vs 57.35 pips).",
    "R6-5 (minor)": "trials.jsonl was written before the val-log assertion and before run.json: now both files are "
                    "serialised first, run.json written, then trials.jsonl (exclusive, atomic), then the assertion; "
                    "run.json records trials.jsonl's sha256 (L29). Proof: world C (val log touched during the run; a "
                    "failure during the computation).",
    "R6-6 (minor)": "moving_mid's band exits carried the engine reason 'time' like the 21:00 exits: an exit kind now "
                    "separates 'moving_mid' from 'time_21_00' in run.json and trials.jsonl (L30). Proof: worlds A and C.",
}

CRITERIA = {   # the twelve bars of the main (verdict.criteria uses these names); every bar read on unrounded figures
    "n>=250": "pooled trades of the main at base costs >= 250",
    "pf>=1.12": "pooled PF on R >= 1.12",
    "t_daily>=2.5": "t of the daily sums of R (trading day of entry, days with a trade) >= 2.5",
    "years_pos>=6/9": "at least 6 of the 9 UTC entry years 2013-2021 with sum R > 0 (no trade = not positive)",
    "stress_pf>=1.04_both_readings": "pooled PF >= 1.04 at costs x1.5 in reading a (rebuilt) and in reading b (same orders)",
    "crosses_positive": "crosses with mean R > 0 >= ceil(0.65 x crosses kept) (8 of 12; no trade = not positive)",
    "max_cross_share<=25%": "no cross above 25 % of the pooled net R; a pooled total <= 0 fails",
    "neighbours_median_pf>=1.06": "median of the six neighbours' pooled base PFs >= 1.06",
    "every_signal_exp>0": "mean R of every order of the main (overlaps allowed, base costs) > 0",
    "max_hold<=5_trading_days": "longest hold of the main <= 192 h",
    "null>=97.5pct": "share of the 200 null replay means strictly below the main's pooled mean R >= 97.5 %",
    "abs_weekly_corr_with_ten<=0.30": "|Pearson rho| of the weekly R with the sum of the ten (418 weeks) <= 0.30",
}


USD_PER_BASE = {"EUR": 1.05, "GBP": 1.20, "AUD": 0.65, "NZD": 0.60, "CAD": 0.70}   # Addendum L, fixed low-end values
COMMISSION_USD_PER_100K_ROUND_TRIP = 6.0


def addendum_text(src):
    i = src.index(HEAD)
    return src[i:].rstrip("\n") + "\n"


def evenings_block(pre):
    """The calendar evenings (common.calendar: no price read), checked against the pre-check's own count."""
    cal = C.calendar()
    E = C.evenings()
    blk = {"count": int(len(E)), "first": str(E[0].date()), "last": str(E[-1].date()),
           "per_year": {int(y): int(v) for y, v in pd.Series(E.year).value_counts().sort_index().items()},
           "mon_thu_candidates_2013_01_01_to_2021_12_30": int(len(cal)),
           "skipped_by_reason": {r: int((cal.status == r).sum()) for r in C.CAL_REASONS},
           "tradable_after_warm_up_by_cross": {c: pre["warm_up"][c]["tradable_evenings"] for c in C.CROSSES},
           "first_tradable_evening_by_cross": {c: pre["warm_up"][c]["first_tradable_evening"] for c in C.CROSSES}}
    assert blk["count"] == 1753 == pre["calendar"]["evenings"]
    assert blk["per_year"] == {int(k): v for k, v in pre["calendar"]["per_year"].items()}
    assert sum(blk["skipped_by_reason"].values()) + blk["count"] == blk["mon_thu_candidates_2013_01_01_to_2021_12_30"]
    return blk


def costs_block():
    """Every cost constant of the run (Addendum L 'Costs'), with the commission table checked against its formula."""
    for c in C.CROSSES:
        v = USD_PER_BASE[C.BASE[c]]
        assert C.COMM_BP[c] == round(COMMISSION_USD_PER_100K_ROUND_TRIP / (100_000 * v) * 1e4, 4), c
    m = C.MAIN
    return {"base_quotes": "Dukascopy M1 bid and ask, unclipped, merged as prep_round3._merge (data/r6 frames)",
            "commission_usd_per_100k_base_round_trip": COMMISSION_USD_PER_100K_ROUND_TRIP,
            "usd_value_of_base_currency": USD_PER_BASE,
            "commission_bp_round_trip": C.COMM_BP,
            "commission_fold": "h = 0.5 x c x 1e-4 x (bc + ac) / 2 of the same M1 bar; bid - h and ask + h on o, h, l, c",
            "engine_commission": 0.0, "swap_rates": 0.0,
            "slippage_bp": {"market_entry_and_time_exit": m["slip_mkt_bps"], "stop": m["slip_stop_bps"], "target": 0.0},
            "costs_x1.5": {"spread_mult": 1.5, "slippage_mult": 1.5, "transform": "goldlab.sim.apply_spread_mult(base, 1.5)",
                           "readings": {"a": "orders rebuilt on the widened frame", "b": "the base orders replayed"},
                           "bar": "pooled PF >= 1.04 in both readings"},
            "gross": {"spread_mult": 0.0, "slippage_bp": 0.0, "transform": "goldlab.sim.apply_spread_mult(base, 0.0)",
                      "readings": {"gross": "the base orders", "gross_a": "reading a's own orders"}}}


def main():
    now = open(PROTO, encoding="utf-8").read()
    old = subprocess.run(["git", "-C", REPO, "show", f"{COMMIT}:lab/PROTOCOL_V3.md"], check=True, capture_output=True,
                         text=True).stdout
    txt = addendum_text(now)
    assert txt == addendum_text(old), "Addendum L differs from the text committed in " + COMMIT
    assert txt.count("\n## ") == 0, "Addendum L is expected to be the last section of PROTOCOL_V3.md"
    assert not os.path.exists(OUT), "declared.json already exists: it is never overwritten"
    assert not os.path.exists(SHA_FILE), "declared.sha256 already exists: it is never overwritten"
    assert not os.path.exists(os.path.join(C.OUT, "trials.jsonl")), "the run has already happened"
    on_disk = sorted(f for f in os.listdir(C.HERE) if f.endswith(".py"))
    assert sorted(C.CODE_FILES) == on_disk, f"code files not covered by the hashes: {set(on_disk) ^ set(C.CODE_FILES)}"
    pre = json.load(open(os.path.join(C.OUT, "precheck.json"), encoding="utf-8"))
    syn = json.load(open(os.path.join(C.OUT, "synthetic.json"), encoding="utf-8"))
    tru = json.load(open(os.path.join(C.OUT, "truncation.json"), encoding="utf-8"))
    hce = json.load(open(os.path.join(C.OUT, "handcheck_entry.json"), encoding="utf-8"))
    assert syn["all_pass"] and tru["all_equal"] and hce["all_match"], "pre-run evidence not clean"
    code = C.code_hashes()
    for name, ev in (("synthetic", syn), ("precheck", pre), ("truncation", tru), ("handcheck_entry", hce)):
        assert ev.get("code_sha256") == code, f"the code changed after the {name} evidence was produced: regenerate it"
    kept = pre["crosses_kept"]
    assert kept == [c for c in C.CROSSES if pre["coverage"][c]["share"] >= 0.90]
    out = {
        "_written_utc": None,                                   # stamped just before the file is written
        "_note": ("Written BEFORE any return of night_fade was computed: on real data only frames, calendar and coverage "
                  "counts, warm-up, signal and drop counts, spreads and costs, the clock, the truncation test and the entry "
                  "side of five hand-checked orders were computed; no exit, no R, no PnL. IN SAMPLE ONLY (2013-2021)."),
        "addendum": f"PROTOCOL_V3.md Addendum L (round 6), committed in {COMMIT} before any run",
        "short_name": "night_fade", "track": C.TRACK,
        "frozen_text_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(), "frozen_text": txt,
        "design_record_sha256": {f: C.sha256(os.path.join(C.OUT, f)) for f in ("design.json", "sources.md")},
        "crosses": C.CROSSES, "crosses_kept": kept, "crosses_dropped_by_coverage": pre["crosses_dropped_by_coverage"],
        "coverage_shares": {c: pre["coverage"][c]["share"] for c in C.CROSSES},
        "cross_bars_on_kept": pre["cross_bars_on_kept"],
        "evenings": evenings_block(pre),
        "commission_bp_round_trip": C.COMM_BP, "pip": C.PIP, "costs": costs_block(),
        "configurations": C.CONFIGS, "verdict_on": "configuration 1 (main) only",
        "readings_of_open_details": READINGS, "criteria": CRITERIA,
        "review_fixes_before_this_declaration": REVIEW_FIXES,
        "null": {"script": "null.py", "replays": 200, "seed": 0, "max_draws": 20, "max_late_min": 5, "no_overlap": False,
                 "of": "main, base costs", "statistic": "pooled mean R of a replay",
                 "bar": "percentile = 100 x share of the 200 means strictly below the main's >= 97.5 (read unrounded)"},
        "correlation": {"script": "correlation.py", "convention": "round5/gold_reopen/correlation.py", "weeks": 418,
                        "bar": "|rho| <= 0.30 (read on the unrounded rho)"},
        "code_sha256": code,
        "frames_sha256": {c: C.sha256(C.frame_path(c)) for c in C.CROSSES},
        "frames_info_sha256": C.sha256(os.path.join(C.R6, "frames_info.json")),
        "pre_run_evidence_sha256": {f: C.sha256(os.path.join(C.OUT, f)) for f in
                                    ("precheck.json", "synthetic.json", "truncation.json", "handcheck_entry.json")},
        "units": "R = multiples of the initial risk |entry fill - stop|; bp = basis points of the entry fill; pip = 0.0001 "
                 "of the quote currency; times New York wall clock unless UTC is written",
    }
    out["_written_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with open(OUT, "x", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False, default=C._default)
    sha = C.sha256(OUT)
    with open(SHA_FILE, "x") as f:
        f.write(f"{sha}  declared.json  (sha256 of declared.json, written {out['_written_utc']})\n")
    print("wrote", OUT)
    print("sha256", sha, "written", out["_written_utc"])


if __name__ == "__main__":
    main()
