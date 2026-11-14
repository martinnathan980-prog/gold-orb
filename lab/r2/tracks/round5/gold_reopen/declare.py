"""Writes results/r2/round5/gold_reopen/declared.json BEFORE any run of this rule (PROTOCOL_V3 Addendum K, round 5).

It copies the frozen text of Addendum K (checked identical to the text committed in 4950eeb, read-only git), lists the
seven configurations exactly as the addendum gives them, and writes down every reading of a detail the text leaves open,
decided from the text and the lab's conventions only. No price is read here and nothing is simulated.
The sha256 of declared.json is written next to it (declared.sha256); run.py refuses to start if declared.json changed.

    python3 declare.py
"""
import datetime as dt
import hashlib
import json
import os
import subprocess

LAB = "/home/user/gold-orb/lab"
REPO = os.path.dirname(LAB)
PROTO = os.path.join(LAB, "PROTOCOL_V3.md")
COMMIT = "4950eeb"
HEAD = "## Addendum K (2026-11-14; written BEFORE any run)"
OUT_DIR = os.path.join(LAB, "results", "r2", "round5", "gold_reopen")
OUT = os.path.join(OUT_DIR, "declared.json")
SHA_FILE = os.path.join(OUT_DIR, "declared.sha256")

MAIN = {"name": "main", "entry": "18:15", "hold_min": 120, "stop_k": 2.0, "n_h1": 480}


def cfg(i, name, role, **chg):
    p = dict(MAIN)
    p.update(chg)
    p["name"] = name
    return {"id": i, "name": name, "role": role, "params": p}


CONFIGS = [
    cfg(1, "main", "verdict (the only configuration judged)"),
    cfg(2, "n_entry_1810", "neighbour: entry 18:10 New York", entry="18:10"),
    cfg(3, "n_entry_1830", "neighbour: entry 18:30 New York", entry="18:30"),
    cfg(4, "n_hold_96", "neighbour: hold 96 minutes", hold_min=96),
    cfg(5, "n_hold_144", "neighbour: hold 144 minutes", hold_min=144),
    cfg(6, "n_stop_1.6", "neighbour: stop 1.6 x mean H1 range", stop_k=1.6),
    cfg(7, "n_stop_2.4", "neighbour: stop 2.4 x mean H1 range", stop_k=2.4),
]

READINGS = {
    "D1_in_sample_only": (
        "The frame lab/data/fp/xauusd_m1.parquet is read with the parquet row filter ts < 2022-01-01 00:00 UTC "
        "(pandas.read_parquet(filters=[('ts', '<', CUT)])), its index converted to nanoseconds, and max(ts) < CUT is "
        "asserted. That slice is installed in goldlab.r2's frame cache before any r2 call, and goldlab.r2.load is wrapped "
        "so that it raises instead of reading a file for a symbol that is not cached and checks that every frame it returns "
        "ends before CUT; r2.evaluate, r2.run and r2.null_test (the lab's tools, used the same way by the round-3 fx track) "
        "therefore only ever see the in-sample slice. (goldlab.r2.load itself reads the whole file, to 2025-12-31, before "
        "slicing, so it is never allowed to read here.) Trades are kept with entry time in [2013-01-01, 2022-01-01) UTC "
        "(goldlab.split.cut 'is'); every exit is asserted before CUT. The bars of 2012-12-31 serve only as warm-up of the H1 "
        "ranges. The official trades of the ten sleeves are read with the filter entry_time < 2022-01-01 in the read "
        "statement and trades exiting in 2022 are dropped. Nothing of 2022-2025 is read, so no line is written to "
        "results/val_access.log (its sha256 is recorded before and after the run)."),
    "D2_sessions": (
        "A session is the daily gold reopen at 18:00 New York (America/New_York wall clock, daylight saving from the tz "
        "database) on the evening of a New York calendar date E that is a Monday, Tuesday, Wednesday or Thursday; it opens "
        "the 17:00-New-York trading day E+1 (Tuesday to Friday, goldlab.data.trading_day). Sunday evenings (the weekly "
        "reopen) are never sessions; Friday and Saturday evenings have no reopen. Candidate evenings: 2012-12-31 to "
        "2021-12-30 (the last Thursday before the cut)."),
    "D3_holidays_and_early_closes": (
        "US holiday closures and early closes of gold are those of the robot's built-in gold calendar (lab/robot/SPEC.md "
        "section 2.1 and lab/robot/src/CR_Clock.mqh; its independent Python reading is gold_kinds in "
        "lab/robot/check/test_clock.py, built on the NYSE rule calendar r2/tracks/idx_us/idxus_lib.us_holidays; the robot's "
        "test T1 checked it against the in-sample gold bars of every NYSE holiday and half day of 2013-2021): "
        "(i) closure: the NYSE's observed Good Friday, Christmas and New Year, gold shut from 17:00 New York the day before "
        "to 18:00 on the day; (ii) early close at 13:00 New York: the other NYSE full holidays (Martin Luther King, "
        "Presidents', Memorial, Independence, Labor and Thanksgiving days; the special NYSE closure of 2018-12-05 is a normal "
        "gold day); (iii) early close at 13:45 New York: the Friday after Thanksgiving and a Monday-Thursday Christmas Eve. "
        "July 3 half days are normal gold days. An evening E is skipped when E itself is such a day (the 18:00 reopen then "
        "ends a holiday closure or an early close, or does not happen at all) OR when the trading day that the reopen opens "
        "(the next weekday, E+1) is such a day (the session itself is a holiday closure or an early close; for a closure "
        "there is no reopen at all). The text can be read either way ('skip US holiday closures and early closes' after a "
        "list of reopens, with sessions named by their trading days), so both are applied together: no evening that either "
        "reading skips is traded. Expected: about 12 to 14 evenings a year (precheck.json counts them by reason)."),
    "D4_quote_test": (
        "'No gold quote between 18:00 and 18:15' means: no M1 bar in the frame whose start time lies in [18:00:00, 18:15:00) "
        "New York on evening E (the FP frame has a bar only for a minute in which the market quoted). For the 18:10 "
        "neighbour the window ends at its entry time, [18:00, 18:10), so that the test never uses bars after the entry; for "
        "the main and the 18:30 neighbour it is exactly [18:00, 18:15). The calendar of D3 is the same for all seven "
        "configurations."),
    "D5_entry": (
        "Market buy at the OPEN of the first M1 bar starting at or after 18:15:00 New York on evening E (18:10 and 18:30 for "
        "the two entry neighbours; goldlab.data.entry_index), filled at the FP ask open plus 0.3 bp of market slippage "
        "(r2.costs('xauusd').slip_mkt_bps). If no bar starts between that time and 17:00 New York of E+1, the evening is "
        "skipped (counted; none expected). No limit on the delay (literal text); entries starting more than 0 and more than "
        "5 minutes after the target time are counted."),
    "D6_h1_bars": (
        "H1 bars are goldlab.data.bars(frame, '1h'), the lab's convention: clock hours on the UTC grid (the same hours on "
        "the New York and server clocks, whose offsets are whole hours), labelled by their start, bid and ask aggregated "
        "separately, mid high = (max bid high + max ask high) / 2, mid low = (min bid low + min ask low) / 2, hours without "
        "any M1 bar absent (no filler bars; gold has no bar in its 17:00-17:59 New York daily closure except 20 bars on "
        "2012-12-31, which stay as they are in the lab frame). Range = mid high - mid low, in USD per ounce. 'Completed' at "
        "the entry: an H1 bar whose clock hour has ended at or before the start of the entry bar (bar start + 60 minutes <= "
        "entry bar start); at 18:15 the 18:00 bar is still forming and is excluded, so the last completed bar is normally "
        "the 16:00-16:59 New York one. Mean range = plain mean of (high - low) over the 480 most recent completed bars (not "
        "ATR: no gap across closures). With fewer than 480 completed bars (the frame starts 2012-12-31 00:00 UTC, so until "
        "about late January 2013) the evening is skipped (counted). Mid prices are identical in the base, stressed and "
        "gross frames (apply_spread_mult moves bid and ask symmetrically), so the stop distance does not depend on the cost "
        "scenario."),
    "D7_stop": (
        "Stop distance = k x mean H1 range, k = 2.0 (1.6 and 2.4 for the two stop neighbours), fixed in price at the entry; "
        "stop = entry fill - distance (goldlab.sim stop_dist). It is a resting sell stop on the bid, active from the entry "
        "bar to the bar before the exit bar: hit when a bar's bid low <= stop, filled at the stop, or at the bid open when a "
        "later bar opens below it (gap), minus 1.0 bp of stop slippage (r2.costs slip_stop_bps). No target."),
    "D8_exit": (
        "Time exit scheduled at entry bar start + 120 minutes (96 and 144 for the hold neighbours), executed at the OPEN of "
        "the first M1 bar starting at or after that time, at the bid open minus 0.3 bp. If that bar starts more than 30 "
        "minutes after the scheduled time (a closure or a data hole), the exit is done at the open of the last bar before "
        "the gap (goldlab.data.exit_index, the lab's convention for time exits; identical to the text whenever a bar exists "
        "within 30 minutes; exits moved are counted). An evening whose exit bar is not after its entry bar is skipped "
        "(counted; none expected)."),
    "D9_one_position": (
        "One order per session, long only; goldlab.sim.simulate with no_overlap=True (one position at a time). It never "
        "binds: sessions are about 24 hours apart and a trade lasts at most 144 minutes (checked)."),
    "D10_costs": (
        "FP Markets Raw: the FP frame's bid and ask (gold spread 0.19 USD at 4,080 USD = 0.47 bp of price, commission "
        "included, applied with Dukascopy's intraday shape, which is wider around the 17:00-18:00 New York rollover) and "
        "goldlab.r2.costs('xauusd'): market slippage 0.3 bp per side, stop slippage 1.0 bp, swap 5.5 % a year on longs per "
        "17:00 New York rollover crossed. Every trade lies between 18:10 and 20:39 New York of one trading day, so no "
        "rollover is crossed and the swap is zero (asserted)."),
    "D11_stress": (
        "Costs x1.5 = goldlab.r2.run mode 'stress' (the lab's stress, the one r2.evaluate reports): spread x1.5 around the "
        "mid (goldlab.sim.apply_spread_mult, orders rebuilt on the widened frame) and slippage x1.5 (r2.costs(sym, 1.5)); "
        "swap rates unchanged (zero for these trades anyway, so the swap question of round 4 does not arise)."),
    "D12_R_and_bp": (
        "R = (exit fill - entry fill - swap) / (entry fill - stop) = goldlab.sim pnl / risk per ounce; both fills include "
        "spread and slippage. Net bp per trade = mean of pnl / entry fill x 10,000. Gross bp per trade = the same rule on "
        "mid quotes with no cost at all (r2.run mode 'gross', as r2.evaluate)."),
    "D13_every_signal": (
        "r2.evaluate's every-signal run (no_overlap=False). With one trade per session and holds far shorter than the "
        "24 hours between sessions it must equal the main run trade for trade (same n, same expectancy): checked and "
        "reported."),
    "D14_null": (
        "goldlab.r2.null_test(sym='xauusd', main, n_seeds=200, mode='time', period='is', no_overlap=True, seed=0) on the "
        "in-sample slice (D1). Why mode 'time': r2.null_test's doc says mode 'time' (random day and random time) is for "
        "calendar and time-of-day rules; PROTOCOL_V2 section 4 asks for an entirely random moment for a calendar rule; "
        "Addendum K says 'random-time null'; round 4's calendar rule (fomc_cycle, D10) used it. Mode 'day' "
        "(same New York time, random day) would re-enter at 18:15 New York on other days, i.e. replay the rule's own clock, "
        "and could not test the claim that 18:15-20:15 New York beats other times. Each filled trade of the main (FP "
        "costs) is re-entered at market at the open of a uniformly drawn M1 bar of the slice, long, with its stop distance "
        "as a fraction of price (risk / entry x mid close of the drawn bar) and its time-exit delay in M1 bars (exit bar - "
        "fill bar), no target; replays entering before 2013-01-01 are cut; one position at a time (r2.null_test's default, "
        "as the rule). 200 replays (PROTOCOL_V2 section 4: '200 rejeux'; r2.null_test's default), numpy default_rng(0). "
        "Statistic: mean R per trade; percentile = share of the 200 replay means strictly below the main's mean R; pass if "
        ">= 97.5. The 200 replay means are recorded by a recording wrapper around r2.simulate during the call (r2's code is "
        "not changed) and saved."),
    "D15_correlation": (
        "Exactly the convention of r2/tracks/round4/fomc_cycle/correlation.py: official trades of the ten in "
        "results/r2/recalc/trades/{name}__{sym}.parquet (noise30 and ocm4 on us100; brk72_24h_wd and F1_brk_ridge_filter on "
        "btcusd and ethusd; nq_btc_follow on btcusd; GOLD_FRI_PM, donch4h_stop and orb_asia_2d_buf10 on xauusd) read with "
        "the filter entry_time < 2022-01-01 in the read statement, trades exiting in 2022 dropped; weekly sums of R by exit "
        "week (W-SUN periods of the UTC exit time); every calendar week from the week of 2014-01-01 to the week of "
        "2021-12-31 counted (418 weeks; a week without an exit counts 0); Pearson correlation of the main's weekly R with "
        "the sum of the ten. Also reported: the three clusters (us100 opening momentum, gold, crypto) and each sleeve. "
        "Bar: |rho| <= 0.30, the reading round 4's ger40_noise30_xetra declared for the same 'at most 0.30' condition; it "
        "implies rho <= 0.30, so it is the stricter of the two readings."),
    "D16_criteria": (
        "Read on configuration 1 (main) only, PROTOCOL_V2 section 4 (= PROTOCOL_V3 section 4) single-sleeve bars: n >= 250; "
        "PF >= 1.12 (on R); t >= 2.5 (mean R / (sd R, ddof 1) x sqrt(n), goldlab.metrics.report); at least 60 % of calendar "
        "years positive (sum of R by entry year; 2013-2021 = 9 years, so at least 6); PF of the main at costs x1.5 >= 1.04; "
        "median PF of the six neighbours (2)-(7) >= 1.06 (numpy median: mean of the 3rd and 4th values); every-signal "
        "expectancy > 0; hold <= 5 trading days (r2.is_criteria: max_hold_h <= 192; a hold of at most 144 minutes); "
        "random-time null percentile >= 97.5; plus Addendum K's condition |weekly correlation with the sum of the ten| <= "
        "0.30. main_pass = all of them."),
    "D17_trials": (
        "Seven lines in results/r2/round5/gold_reopen/trials.jsonl, one per declared configuration, written by "
        "goldlab.r2.log_trial (track 'round5/gold_reopen') from goldlab.r2.evaluate (FP costs, costs x1.5, gross, every "
        "signal), whatever the result; run.py refuses to run twice. Nothing else is simulated except the trade frames of "
        "these same runs (r2.run, the same code path, checked equal to r2.evaluate's reports), the 200 null replays of the "
        "main, and the hand check of five trades."),
    "D18_reported_not_judged": (
        "For every configuration: the lab's report fields, R by year, net and gross bp per trade, mean stop distance in bp, "
        "stop-outs, entry delays and moved exits, results by weekday of the evening and by New York daylight-saving regime. "
        "For the main: the comparison with what Addendum K said before the run (about +0.8 bp gross for the two hours "
        "after the reopen from the lab's 2013-2021 hour table, about +2.5 bp needed for t >= 2.5 after costs)."),
}

CRITERIA = {
    "n>=250": "n of (1)",
    "pf>=1.12": "PF on R of (1)",
    "t>=2.5": "t of (1)",
    "years_pos>=60%": "years 2013-2021 of (1) with sum R > 0: at least 6 of 9",
    "stress_pf>=1.04": "PF of (1) at costs x1.5",
    "neighbours_median_pf>=1.06": "median PF of (2)-(7)",
    "every_signal_exp>0": "expectancy of (1), every signal taken",
    "max_hold<=5d": "max hold of (1) <= 192 h (r2.is_criteria)",
    "null>=97.5pct": "percentile of (1) in its random-time null (200 replays)",
    "abs_weekly_corr_with_ten<=0.30": "|Pearson rho| of weekly R of (1) with the sum of the ten, 2014-2021",
}


def addendum_text(src):
    i = src.index(HEAD)
    return src[i:].rstrip("\n") + "\n"


def main():
    now = open(PROTO, encoding="utf-8").read()
    old = subprocess.run(["git", "-C", REPO, "show", f"{COMMIT}:lab/PROTOCOL_V3.md"], check=True, capture_output=True,
                         text=True).stdout
    txt = addendum_text(now)
    assert txt == addendum_text(old), "Addendum K differs from the text committed in " + COMMIT
    assert txt.count("## ") == 1, "Addendum K is expected to be the last section of PROTOCOL_V3.md"
    os.makedirs(OUT_DIR, exist_ok=True)
    assert not os.path.exists(OUT), "declared.json already exists: it is never overwritten"
    out = {
        "_written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "_note": ("Written BEFORE any run of this rule: of the gold frame only the parquet schema and the row-group "
                  "timestamp statistics had been read (no price, no bar count, no return); no order built, nothing "
                  "simulated. IN SAMPLE ONLY (2013-2021)."),
        "addendum": "PROTOCOL_V3.md Addendum K (round 5), committed in 4950eeb before any run",
        "short_name": "gold_reopen",
        "frozen_text_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
        "frozen_text": txt,
        "market": "xauusd (lab/data/fp/xauusd_m1.parquet, FP Markets Raw cost model, M1 bid/ask)",
        "configurations": CONFIGS,
        "verdict_on": "configuration 1 (main) only",
        "readings_of_open_details": READINGS,
        "criteria": CRITERIA,
        "null": {"function": "goldlab.r2.null_test", "mode": "time", "n_seeds": 200, "seed": 0, "no_overlap": True,
                 "period": "is", "of": "main"},
        "correlation": {"script": "correlation.py", "convention": "round4/fomc_cycle/correlation.py", "weeks": "2014-2021",
                        "bar": "|rho| <= 0.30"},
        "units": "R = multiples of the initial risk (entry fill - stop); bp = basis points of the entry fill price; prices "
                 "in USD per troy ounce; times in UTC unless New York is written",
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    sha = hashlib.sha256(open(OUT, "rb").read()).hexdigest()
    with open(SHA_FILE, "w") as f:
        f.write(f"{sha}  declared.json  (sha256 of declared.json, written {out['_written_utc']})\n")
    print("wrote", OUT)
    print("sha256", sha, "written", out["_written_utc"])


if __name__ == "__main__":
    main()
