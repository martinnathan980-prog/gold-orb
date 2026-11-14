"""Attack step 3 and 4: compare my independent implementation with the engineer's trades and results, trade by trade
and criterion by criterion, check the specific points of the attack brief on the engineer's own trades, and write
results/r2/round5/gold_reopen/attack.json. In sample only: it reads my outputs, the engineer's outputs (2013-2021
trades and JSON files), and the in-sample gold frame through acommon.load_is (parquet filter ts < 2022-01-01).
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acommon as A  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

E, M = A.ENG, A.OUT
J = lambda p: json.load(open(p, encoding="utf-8"))  # noqa: E731
PAIRS = ["01_main", "01_main_costs_x1.5", "01_main_gross", "02_n_entry_1810", "03_n_entry_1830", "04_n_hold_96",
         "05_n_hold_144", "06_n_stop_1.6", "07_n_stop_2.4"]


def trade_compare(name):
    e = pd.read_parquet(os.path.join(E, f"trades_{name}.parquet"))
    m = pd.read_parquet(os.path.join(M, f"trades_{name}.parquet"))
    for x in (e, m):
        A.assert_is(x.entry_time)
        A.assert_is(x.exit_time)
    ek = e.set_index(pd.DatetimeIndex(e.evening).date)
    mk = m.set_index(pd.DatetimeIndex(m.evening).date)
    only_e = sorted(set(ek.index) - set(mk.index))
    only_m = sorted(set(mk.index) - set(ek.index))
    com = sorted(set(ek.index) & set(mk.index))
    ec, mc = ek.loc[com], mk.loc[com]
    d = lambda a, b: float(np.abs(ec[a].to_numpy(float) - mc[b].to_numpy(float)).max())  # noqa: E731
    dR = np.abs(ec.R.to_numpy() - mc.R.to_numpy())
    return {"engineer_n": int(len(e)), "attack_n": int(len(m)), "sessions_only_in_engineer": [str(x) for x in only_e],
            "sessions_only_in_attack": [str(x) for x in only_m],
            "same_entry_time": bool((ec.entry_time.to_numpy() == mc.entry_time.to_numpy()).all()),
            "same_exit_time": bool((ec.exit_time.to_numpy() == mc.exit_time.to_numpy()).all()),
            "same_exit_reason": bool((ec.reason.to_numpy() == mc.reason.to_numpy()).all()),
            "max_abs_entry_diff_usd": d("entry", "entry"), "max_abs_stop_diff_usd": d("stop", "stop"),
            "max_abs_exit_diff_usd": d("exit", "exit"), "max_abs_R_diff": float(dR.max()),
            "trades_with_R_diff_over_1e-12": int((dR > 1e-12).sum()),
            "max_abs_mean_h1_range_diff_usd": float(np.abs(ec.h1_mean_range.to_numpy() - mc.mean_h1_range.to_numpy()).max()),
            "engineer_swap_total": float(e.swap.abs().sum())}


def main():
    att, nul, hand, pre = J(os.path.join(M, "attack_results.json")), J(os.path.join(M, "anull.json")), \
        J(os.path.join(M, "ahand.json")), J(os.path.join(M, "aprecheck.json"))
    eres, erun, enul, ecor, epre, ehc = (J(os.path.join(E, f)) for f in ("results.json", "run.json", "null.json",
                                                                        "correlation.json", "precheck.json", "handcheck.json"))
    edecl = J(os.path.join(E, "declared.json"))
    trials = [json.loads(x) for x in open(os.path.join(E, "trials.jsonl"))]
    out = {"what": "Attack (independent re-implementation) of PROTOCOL_V3 Addendum K, gold daily-reopen drift, in sample "
                   "2013-2021; engineer's test in lab/r2/tracks/round5/gold_reopen/, attack code in its attack/ folder",
           "written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "units": "R = multiples of the initial risk (entry fill - stop); bp = basis points of the entry fill; prices in "
                    "USD per troy ounce; times in UTC unless New York is written"}
    # ------------------------------------------------------------------ trade by trade
    tb = {n: trade_compare(n) for n in PAIRS}
    out["trade_by_trade"] = tb
    # ------------------------------------------------------------------ criteria side by side
    mc, ms = att["configs"]["main"]["fp"], att["configs"]["main"]["x1.5"]
    my_null = nul["mine_clock_independent_with_swap"]
    ec = eres["criteria"]
    rows = []

    def add(name, ev, ep, av, ap, diff):
        rows.append({"criterion": name, "engineer_value": ev, "engineer_pass": ep, "attack_value": av, "attack_pass": ap,
                     "same_verdict": ep == ap, "difference": diff})

    add("n >= 250", ec["n>=250"]["value"], ec["n>=250"]["pass"], mc["n"], mc["n"] >= 250, "none (same 1,737 sessions)")
    add("PF >= 1.12", ec["pf>=1.12"]["value"], ec["pf>=1.12"]["pass"], mc["pf"], mc["pf"] >= 1.12, "none (0.8106 both before rounding)")
    add("t >= 2.5", ec["t>=2.5"]["value"], ec["t>=2.5"]["pass"], mc["t"], mc["t"] >= 2.5, "none (-2.931)")
    yp, yn = (int(x) for x in mc["years_pos"].split("/"))
    add(">= 60 % of years positive", ec["years_pos>=60%"]["value"], ec["years_pos>=60%"]["pass"], mc["years_pos"],
        yp >= 0.6 * yn, "none (same R in every year)")
    add("PF at costs x1.5 >= 1.04", ec["stress_pf>=1.04"]["value"], ec["stress_pf>=1.04"]["pass"], ms["pf"], ms["pf"] >= 1.04,
        "0.72763 engineer vs 0.72765 attack: the engineer's H1 range is recomputed on the x1.5 frame (issue I1)")
    add("neighbours' median PF >= 1.06", ec["neighbours_median_pf>=1.06"]["value"], ec["neighbours_median_pf>=1.06"]["pass"],
        att["neighbours_median_pf"], att["neighbours_median_pf"] >= 1.06, "none (six neighbours identical trade for trade)")
    add("every-signal expectancy > 0", ec["every_signal_exp>0"]["value"], ec["every_signal_exp>0"]["pass"],
        att["every_signal"]["expectancy_R"], att["every_signal"]["expectancy_R"] > 0, "none (no overlap: every signal = main)")
    add("hold <= 5 trading days", ec["max_hold<=5d"]["value"], ec["max_hold<=5d"]["pass"], f"{mc['max_hold_min']} min",
        mc["max_hold_min"] <= 5 * 24 * 60, "none")
    add("random-time null >= 97.5th percentile", ec["null>=97.5pct"]["value"], ec["null>=97.5pct"]["pass"],
        my_null["percentile"], my_null["percentile"] >= 97.5,
        "engineer 61.0 (r2.null_test seed 0, reproduced exactly on my orders); my own null 56.5-63.0 over variants and "
        "seeds; 49-50 if the replays' swap is not charged (my first run): fails in every case")
    add("|weekly correlation with the sum of the ten| <= 0.30", ec["abs_weekly_corr_with_ten<=0.30"]["value"],
        ec["abs_weekly_corr_with_ten<=0.30"]["pass"], att["correlation"]["rho"], abs(att["correlation"]["rho"]) <= 0.30,
        "0.067 (3 decimals) vs 0.0675")
    out["criteria_comparison"] = rows
    out["criteria_verdicts_differ"] = [r["criterion"] for r in rows if not r["same_verdict"]]
    out["engineer_main_pass"] = eres["main_pass"]
    out["attack_main_pass"] = bool(all(r["attack_pass"] for r in rows))
    # ------------------------------------------------------------------ my numbers
    nb = {c["name"]: {k: att["configs"][c["name"]]["fp"][k] for k in ("n", "pf", "t", "expectancy_R", "total_R", "years_pos")}
          for c in A.CONFIGS[1:]}
    for c in A.CONFIGS[1:]:
        nb[c["name"]]["pf_costs_x1.5"] = att["configs"][c["name"]]["x1.5"]["pf"]
    out["attack_numbers"] = {
        "main_fp": mc, "main_costs_x1.5": ms, "main_gross": att["configs"]["main"]["gross"],
        "main_gross_bp_mean": att["configs"]["main"]["gross_bp_mean"], "neighbours": nb,
        "neighbours_median_pf": att["neighbours_median_pf"], "every_signal": att["every_signal"],
        "null_main": my_null, "null_variants": {k: {q: v[q] for q in ("duration", "swap_charged", "one_position_at_a_time",
                                                                       "null_mean_R", "null_p975_R", "percentile")}
                                                for k, v in nul.items() if k.startswith("mine_") and isinstance(v, dict) and "percentile" in v},
        "null_other_seeds": nul["mine_clock_independent_with_swap_other_seeds"],
        "null_first_run_without_replay_swap": {"clock": {k: att["null_clock"][k] for k in ("null_mean_R", "percentile")},
                                               "bars": {k: att["null_bars"][k] for k in ("null_mean_R", "percentile")}},
        "engineer_null_call_reproduced_on_my_orders": nul["r2_null_test_seed0_on_my_orders"],
        "engineer_null_call_other_seeds": nul["r2_null_test_other_seeds"],
        "correlation_2014_2021": att["correlation"]}
    # per-year agreement
    ey = eres["main"]["by_year_R"]
    out["per_year_R"] = {y: {"engineer": ey[str(y)] if str(y) in ey else ey.get(y), "attack": v} for y, v in mc["per_year_R"].items()}
    # ------------------------------------------------------------------ specific checks on the engineer's trades
    df = A.load_is()
    fr = A.Frame(df)
    h1 = A.H1(fr)
    et = pd.read_parquet(os.path.join(E, "trades_01_main.parquet"))
    ny = et.entry_time.dt.tz_convert(A.NY)
    off_h = (ny.apply(lambda x: x.utcoffset().total_seconds() / 3600)).to_numpy()
    nodelay = et.entry_delay_min.to_numpy() == 0
    utc_hm = et.entry_time.dt.strftime("%H:%M").to_numpy()
    srv = (ny.dt.tz_localize(None) + pd.Timedelta(hours=7)).dt.strftime("%H:%M").to_numpy()
    edt = off_h == -4
    chk = {}
    chk["dst"] = {"entries_without_delay": int(nodelay.sum()),
                  "all_at_18_15_new_york": bool((ny.dt.strftime("%H:%M").to_numpy()[nodelay] == "18:15").all()),
                  "summer_time_entries_at_22_15_utc": bool((utc_hm[nodelay & edt] == "22:15").all()),
                  "winter_time_entries_at_23_15_utc": bool((utc_hm[nodelay & ~edt] == "23:15").all()),
                  "n_summer": int((nodelay & edt).sum()), "n_winter": int((nodelay & ~edt).sum()),
                  "fp_server_time_all_01_15": bool((srv[nodelay] == "01:15").all()),
                  "switch_evenings_checked": [r for r in pre["dst_evenings"] if r["status"] == "ok"][:12],
                  "verdict": "correct: New York wall clock from the tz database on both sides of every switch"}
    wd = pd.DatetimeIndex(et.evening).dayofweek
    chk["sunday_reopen_excluded"] = {"evening_weekdays": {int(k): int(v) for k, v in pd.Series(wd).value_counts().sort_index().items()},
                                     "no_sunday_friday_saturday": bool((wd <= 3).all())}
    ms_ = pd.read_parquet(os.path.join(M, "sessions_main.parquet"))
    mine_hol = set(str(e) for e in ms_.evening[ms_.status == "holiday"])
    eng_hol = set(r["evening"] for r in epre["calendar_skipped_evenings"])
    mine_nq = set(str(e) for e in ms_.evening[ms_.status == "no_quote_1800_1815"])
    eng_nq = set(r["evening"] for r in epre["no_quote_evenings"])
    chk["holiday_and_early_close_evenings"] = {
        "attack_skipped": len(mine_hol), "engineer_skipped": len(eng_hol), "identical_sets": mine_hol == eng_hol,
        "per_year": pre["sessions_union"]["by_year"],
        "frame_disagreements_with_rule_calendar": pre["calendar_vs_frame"]["disagreements"],
        "verdict": "same 108 evenings; the calendar is the US market rule calendar mapped to gold; the frame itself shows "
                   "two Columbus Day halts not in it and a normal 2019-07-04 (issue I2)"}
    chk["no_quote_18_00_18_15"] = {"attack": len(mine_nq), "engineer": len(eng_nq), "identical_sets": mine_nq == eng_nq,
                                   "evenings": sorted(mine_nq),
                                   "note": "18 of the 21 are 2014-03-10..2014-04-16 and 2015-03-09, when the feed reopened "
                                           "at 19:00 New York; 2015-06-30 is the leap-second evening (reopen 20:00); "
                                           "2013-12-26 reopens at 19:00"}
    last_ok = (pd.to_datetime(et.h1_last_utc).dt.tz_localize("UTC") + pd.Timedelta(hours=1) <= et.entry_time).all()
    hs = h1.start_ns
    f_i = np.searchsorted(hs, pd.DatetimeIndex(et.h1_first_utc).tz_localize("UTC").as_unit("ns").asi8)
    l_i = np.searchsorted(hs, pd.DatetimeIndex(et.h1_last_utc).tz_localize("UTC").as_unit("ns").asi8)
    assert (hs[f_i] == pd.DatetimeIndex(et.h1_first_utc).tz_localize("UTC").as_unit("ns").asi8).all()
    assert (hs[l_i] == pd.DatetimeIndex(et.h1_last_utc).tz_localize("UTC").as_unit("ns").asi8).all()
    chk["h1_480_completed_before_entry"] = {
        "every_last_h1_bar_ends_at_or_before_entry_bar_start": bool(last_ok),
        "every_window_is_480_existing_hours": bool(((l_i - f_i + 1) == 480).all()),
        "last_h1_bar_new_york_hour_counts": epre["h1_window_last_bar_new_york_hour"],
        "verdict": "no look-ahead: the forming 18:00 bar is never used except on the six 19:00 entries, where it has ended"}
    chk["costs"] = {"fp": "identical fills (ask open +0.3 bp, stop or gapped bid open -1.0 bp, bid open -0.3 bp; spread from "
                          "the FP frame = 0.19 USD at 4,080 USD x Dukascopy shape); swap 0 on every trade (no 17:00 New York "
                          "rollover crossed, asserted in both codes)",
                    "x1.5": "spread x1.5 around the mid and slippage x1.5 (0.45 bp market, 1.5 bp stop) in both; same "
                            "trades; R within 0.0011 because of issue I1",
                    "gross": "mid quotes, no cost, same trades; R within 0.0012 (issue I1); gross mean -0.0075 bp engineer, "
                             "-0.0076 bp attack"}
    chk["null"] = {"declared_mode": edecl["null"]["mode"], "mode_is_right": edecl["null"]["mode"] == "time",
                   "statistic": "mean R per trade of the rule vs the 200 replay means, percentile = share strictly below "
                                "(PROTOCOL_V2 section 4: the rule's expectancy must beat 97.5 % of 200 replays)",
                   "engineer_value_reproduced_exactly": nul["r2_reproduces_engineer"],
                   "engineer": {k: enul[k] for k in ("rule_mean_R", "null_mean_R", "null_p975_R", "percentile")},
                   "verdict": "right mode (random day and time for a time-of-day rule), right statistic, right percentile"}
    chk["correlation"] = {"engineer_rho": ecor["main"]["corr_with_sum_of_ten"], "attack_rho": att["correlation"]["rho"],
                          "n_weeks": att["correlation"]["n_weeks"], "weeks_with_an_exit": att["correlation"]["weeks_with_an_exit"],
                          "engineer_weeks_with_an_exit": ecor["main"]["weeks_with_an_exit"],
                          "each_sleeve_engineer": ecor["main"]["corr_with_each_sleeve"],
                          "each_sleeve_attack": att["correlation"]["each_sleeve"],
                          "verdict": "same convention as round4/fomc_cycle/correlation.py; same value"}
    chk["trial_logging"] = {"engineer_trials_lines": len(trials), "names": [t["params"]["name"] for t in trials],
                            "declared_seven_only": [t["params"]["name"] for t in trials] == [c["name"] for c in edecl["configurations"]],
                            "attack_log": "results/r2/round5/gold_reopen/attack/attack_trials.jsonl (my 7 configurations at "
                                          "FP and x1.5, the main gross, and 7 readings-sensitivity runs of the same rule; "
                                          "the engineer's trials.jsonl is not touched)"}
    vl = os.path.join(A.LAB, "results", "val_access.log")
    import hashlib
    chk["in_sample_only"] = {
        "engineer_reads": "gold frame: pandas.read_parquet(filters=[('ts','<',2022-01-01)]) + max < cut asserted (common.load_is), "
                          "used by precheck, run, handcheck, verdict; goldlab.r2.load wrapped to raise on any uncached "
                          "symbol (r2.load reads whole files) and to assert every returned frame ends before the cut; the "
                          "ten sleeves' trades read with filter entry_time < 2022-01-01 and exits >= 2022 dropped; "
                          "test_synthetic.py uses a made-up frame and checks the guard refuses r2.load('us100') before "
                          "any read; idxus_lib reads no file; every trade's entry and exit asserted < 2022-01-01",
        "attack_reads": "the same parquet filter in acommon.load_is (max < cut asserted), the ten sleeves with the same "
                        "filter, the engineer's 2013-2021 outputs; r2.null_test only on the installed in-sample slice with "
                        "r2.load unable to read a file",
        "val_access_log_sha256_now": hashlib.sha256(open(vl, "rb").read()).hexdigest(),
        "val_access_log_sha256_engineer_before_after": [erun["val_access_log_sha256_before"], erun["val_access_log_sha256_after"]],
        "val_access_log_unchanged": hashlib.sha256(open(vl, "rb").read()).hexdigest() == erun["val_access_log_sha256_after"],
        "holdout_or_2022_files_opened": False}
    out["checks"] = chk
    # ------------------------------------------------------------------ extra sensitivity: entries delayed > 5 min
    mt = pd.read_parquet(os.path.join(M, "trades_01_main.parquet"))
    keep = mt[mt.entry_delay_min <= 5]
    R = keep.R.to_numpy()
    by = keep.groupby(keep.entry_time.dt.year).R.sum()
    sens = dict(att["sensitivities"])
    sens["without_the_7_entries_delayed_over_5_min"] = {"n": int(len(R)), "pf": round(A.pf(R), 4), "t": round(A.tstat(R), 3),
                                                        "expectancy_R": round(float(R.mean()), 5),
                                                        "years_pos": f"{int((by > 0).sum())}/{len(by)}"}
    out["sensitivities_main"] = {k: {q: v[q] for q in ("n", "pf", "t", "expectancy_R", "years_pos")} for k, v in sens.items()}
    out["sensitivities_note"] = ("other readings of the open details, same rule, not new configurations: none moves PF above "
                                 "0.85, t above -2.3 or the years above 2/9, so no criterion verdict depends on them")
    # ------------------------------------------------------------------ judgement of the declared choices (step 1)
    out["declared_choices_judged"] = {
        "timing": "declared.json written 2026-11-14 04:09:10 UTC (sha256 3bb98b52... matches today), 3 h 48 min after "
                  "Addendum K's commit 4950eeb (00:21:38 UTC) and 8 min before the first trades file (04:17:26); its note "
                  "says only the parquet schema and row-group time statistics had been read; the precheck (04:12) computed "
                  "no return; nothing in it could have been chosen after seeing a result",
        "D1 in sample": "natural and stricter than the brief (r2.load never allowed to read)",
        "D2 sessions": "natural (Mon-Thu evenings, trading days Tue-Fri, Sunday never)",
        "D3 holidays": "defensible: the US market rule calendar mapped to gold, and the union of the two readings of 'skip "
                       "US holiday closures and early closes' (the evening's own day, or the trading day it opens); the "
                       "union is the conservative choice; single readings give PF 0.818 / 0.821",
        "D4 quote test": "natural; the 18:10 neighbour's shorter window avoids looking past the entry (one evening, "
                         "2017-01-09, PF 0.8458 vs 0.8457)",
        "D5 entry": "literal text (no delay limit); see issue I3",
        "D6 H1 range": "lab convention (goldlab bars, mid, UTC clock hours, completed before the entry bar); the claim "
                       "that the stop distance does not depend on the cost scenario is slightly wrong (issue I1); a bid "
                       "range (MetaTrader chart) gives PF 0.8106 too",
        "D7 stop, D8 exit": "natural; the 30-minute gap rule never fires (no exit moved, none late over 30 min)",
        "D9 one position": "natural; never binds",
        "D10-D12 costs and R": "the lab's FP model; verified fill by fill",
        "D13 every signal": "natural; identical to the main",
        "D14 null": "the right mode and statistic; the replays pay the 5.5 %/yr swap when they cross 17:00 New York and the "
                    "rule never does (issue I4, the lab's convention, not stated in D14)",
        "D15 correlation": "exactly round 4's convention; |rho| reading is the stricter one",
        "D16 criteria": "PROTOCOL_V2 section 4 plus Addendum K's correlation bar, on the main only: correct"}
    # ------------------------------------------------------------------ differences explained
    out["differences_explained"] = [
        {"what": "costs x1.5 and gross runs: same 1,737 trades, same entry and exit bars and reasons, R different by at "
                 "most 0.0011 (x1.5) and 0.0012 (gross)",
         "why": "the engineer's make_orders rebuilds the 480-bar H1 range on the re-spread frame r2.run passes it; the "
                "lab's mid high = (max bid high + max ask high)/2 is not invariant when the half-spread (constant within an "
                "M1 bar, different across bars) is scaled, so the mean range moves by up to 0.0015 USD (of about 3.5 USD); "
                "I compute it once on the FP frame",
         "whose_reading_is_right": "both defensible: the text fixes the stop from H1 bars and says nothing about the stress "
                                   "scenario; r2.run's documented contract is to rebuild orders on the stressed quotes. "
                                   "Effect: stress PF 0.72763 vs 0.72765, gross -0.0075 vs -0.0076 bp; no verdict",
         "size": "PF difference 0.00002"},
        {"what": "random-time null: my first null mean -0.0231 R (percentile 49-50) vs engineer -0.0279 R (61.0)",
         "why": "my first null did not charge the long swap that a random replay pays when it crosses the 17:00 New York "
                "rollover (about 9 % of replays; 0.03 R a night, x3 on Wednesday); goldlab.sim charges it from "
                "fp_costs.json. With the swap added my null mean is -0.0269 to -0.0276 R and the percentile 56.5-63.0 over "
                "variants and seeds; the engineer's own call reproduced on my orders gives exactly 61.0",
         "whose_reading_is_right": "the engineer's (the lab's cost model applied to the replays); my first run was my error, "
                                   "corrected before writing this file",
         "size": "no verdict: the rule's mean R -0.0243 is near the middle of every null, the 97.5th percentile is -0.0039 "
                 "to +0.0005 R"},
        {"what": "correlation 0.067 vs 0.0675", "why": "rounding to 3 decimals in the engineer's file", "size": "none"}]
    # ------------------------------------------------------------------ issues
    out["issues"] = [
        {"id": "I1", "severity": "minor",
         "what": "declared.json D6 says the stop distance does not depend on the cost scenario; it does, slightly: r2.run "
                 "'stress' and 'gross' rebuild the H1 range on re-spread quotes and the lab's bid/ask-aggregated mid range "
                 "changes",
         "evidence": "every one of the 1,737 evenings has a mean H1 range different by up to 0.0013 USD (x1.5) and 0.0015 "
                     "USD (gross); R up to 0.0011 / 0.0012 apart; stress PF 0.72763 vs 0.72765",
         "fix": "say so in D6, or compute the stop distance once on the FP frame and pass it to the stressed run"},
        {"id": "I2", "severity": "minor",
         "what": "the holiday calendar (US market rules) and the frame disagree on four days: Columbus Day 2013-10-14 and "
                 "2014-10-13 show a 13:00 New York gold halt (not skipped; their H1 windows end at the 13:00 bar) and "
                 "2019-07-04 is a normal full day in the frame (it and its eve are skipped)",
         "evidence": "aprecheck.json calendar_vs_frame; sensitivity: PF 0.8135 (Columbus evenings skipped), 0.8122 "
                     "(2019-07-03/04 traded)",
         "fix": "none needed for this verdict; for the robot, decide whether the calendar follows the rules or the broker's "
                "actual hours"},
        {"id": "I3", "severity": "minor",
         "what": "six evenings (2014-03-13, 03-20, 03-26, 04-08, 04-09 and 2017-03-13) pass the quote test on a single stray "
                 "M1 bar at 18:00 while the feed really reopened at 19:00 New York; the trade enters 45 minutes late at "
                 "19:00 and its H1 window ends with the near-empty 18:00 hour",
         "evidence": "bars 16:59, 18:00, 19:00, 19:01... on each of these evenings; precheck.json entry_delays_main; "
                     "sensitivity without the 7 entries delayed over 5 min (the six plus 2013-03-11, 8 min): n 1,730, PF 0.8048, "
                     "t -3.02, 2/9 years positive",
         "fix": "literal text followed by both implementations; a robot should cap the entry delay"},
        {"id": "I4", "severity": "minor",
         "what": "the null replays pay the long swap when they cross the 17:00 New York rollover while the rule's trades "
                 "never do; this lowers the null by about 0.004 R and so favours the rule; D14 does not state it",
         "evidence": "null percentile 61.0 with it (engineer, reproduced), 49-50 without it (attack first run)",
         "fix": "state it in D14; it cannot change this verdict (fail either way)"}]
    # ------------------------------------------------------------------ verdict
    same = not out["criteria_verdicts_differ"] and (eres["main_pass"] == out["attack_main_pass"])
    out["verdict"] = "confirmed" if same else "not_confirmed"
    out["verdict_text"] = (
        "CONFIRMED: every criterion verdict of the engineer's main configuration stands under my independent "
        "implementation. The main fails in sample (PF 0.811, t -2.93, 2 of 9 years positive, PF 0.728 at costs x1.5, "
        "neighbours' median PF 0.810, every-signal expectancy -0.0243 R, null percentile 56-64); n, hold and correlation "
        "pass. The 1,737 main trades and all six neighbours are identical trade for trade; the only numeric differences "
        "are 0.00002 in the stressed PF and the null's seed and swap convention, none near a threshold." if same else
        "NOT CONFIRMED: see criteria_verdicts_differ and issues")
    out["files"] = {
        "attack_code": ["lab/r2/tracks/round5/gold_reopen/attack/acommon.py", "lab/r2/tracks/round5/gold_reopen/attack/aprecheck.py",
                        "lab/r2/tracks/round5/gold_reopen/attack/arun.py", "lab/r2/tracks/round5/gold_reopen/attack/ahand.py",
                        "lab/r2/tracks/round5/gold_reopen/attack/anull.py", "lab/r2/tracks/round5/gold_reopen/attack/acompare.py"],
        "attack_outputs": "lab/results/r2/round5/gold_reopen/attack/ (attack_results.json, anull.json, ahand.json, aprecheck.json, "
                          "attack_trials.jsonl, trades_*.parquet, sessions_main.parquet, null_means_*.npy)"}
    out["hand_check"] = {"n_checked": hand["n_checked"], "all_match": hand["all_match"], "max_abs_R_diff": hand["max_abs_R_diff"],
                         "lab_engine_on_my_orders": hand["lab_engine_on_my_orders"],
                         "engineer_hand_check": {k: ehc[k] for k in ("n_checked", "all_match", "max_abs_R_diff")}}
    A.jdump(out, os.path.join(E, "attack.json"))
    print(json.dumps({"verdict": out["verdict"], "criteria_verdicts_differ": out["criteria_verdicts_differ"],
                      "sensitivities_main": out["sensitivities_main"], "checks_dst": {k: v for k, v in chk["dst"].items() if k != "switch_evenings_checked"},
                      "holidays": {k: chk["holiday_and_early_close_evenings"][k] for k in ("attack_skipped", "engineer_skipped", "identical_sets")},
                      "no_quote": {k: chk["no_quote_18_00_18_15"][k] for k in ("attack", "engineer", "identical_sets")},
                      "h1": {k: v for k, v in chk["h1_480_completed_before_entry"].items() if k != "verdict"},
                      "sunday": chk["sunday_reopen_excluded"], "val_log_unchanged": chk["in_sample_only"]["val_access_log_unchanged"],
                      "per_year": out["per_year_R"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
