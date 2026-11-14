"""Verdict of the gold daily-reopen drift (PROTOCOL_V3 Addendum K) on the MAIN configuration, in sample only.
Collects run.json, null.json, correlation.json, handcheck.json and precheck.json into results.json; nothing is
simulated here. The bars are PROTOCOL_V2 section 4 (declared.json D16) plus Addendum K's weekly correlation bar (D15);
main_pass = all of them. Also cross-checked with goldlab.r2.is_criteria on the logged r2.evaluate output.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import numpy as np  # noqa: E402

from goldlab import r2  # noqa: E402


def J(name):
    return json.load(open(os.path.join(C.OUT, name), encoding="utf-8"))


def mid_moves():
    """Information only (added after the first numbers, not judged): pure mid-price moves on the main's evenings, the
    same kind of number as the hour table quoted by Addendum K. Mid = (bid open + ask open) / 2 at bar opens; the
    18:15 -> 20:15 move ignores the stop; 'first bar at or after' for every clock time, with exit_index's gap rule."""
    import pandas as pd
    from goldlab.data import exit_index
    m1 = C.load_is()
    ins = m1.index.as_unit("ns").asi8
    mid = (m1.bo.to_numpy() + m1.ao.to_numpy()) / 2
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    ev = pd.DatetimeIndex(t.evening)
    ei = np.searchsorted(ins, pd.DatetimeIndex(t.entry_time).tz_convert("UTC").as_unit("ns").asi8)
    assert (ins[ei] == pd.DatetimeIndex(t.entry_time).as_unit("ns").asi8).all()
    xs = exit_index(m1, pd.DatetimeIndex(t.t_exit_sched_utc).tz_localize("UTC"))
    i18 = np.searchsorted(ins, C.ny_utc_ns(ev, "18:00"))
    i20 = exit_index(m1, pd.to_datetime(C.ny_utc_ns(ev, "20:00"), unit="ns", utc=True))
    out = {}
    for name, a, b in (("entry_bar_to_scheduled_exit_bar_18_15_to_20_15", ei, xs), ("first_bar_18_00_to_20_00", i18, i20),
                       ("first_bar_18_00_to_entry_bar_18_15", i18, ei)):
        r = (mid[b] - mid[a]) / mid[a] * 1e4
        out[name] = {"n": int(len(r)), "mean_bp": round(float(r.mean()), 3),
                     "t": round(float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))), 2),
                     "years_positive": f"{int((pd.Series(r).groupby(ev.year).mean() > 0).sum())}/{ev.year.nunique()}"}
    out["note"] = ("mid prices at bar opens on the 1,737 evenings of the main, no cost, no stop; information only, added "
                   "after the first numbers to compare like for like with the hour table of Addendum K")
    return out


def main():
    decl, sha = C.declared()
    run, nul, cor, hc, pre = J("run.json"), J("null.json"), J("correlation.json"), J("handcheck.json"), J("precheck.json")
    assert run["declared_sha256"] == sha and cor["declared_sha256"] == sha and hc["declared_sha256"] == sha
    trials = [json.loads(x) for x in open(os.path.join(C.OUT, "trials.jsonl"))]
    assert len(trials) == 7 and [t["params"]["name"] for t in trials] == [c["name"] for c in decl["configurations"]]
    L = {l["name"]: l for l in run["configs"]}
    m = L["main"]
    mi, ms, mg, me = m["is"], m["is_stress"], m["is_gross"], m["every_signal"]
    nb = {c["name"]: L[c["name"]]["is"]["pf"] for c in decl["configurations"][1:]}
    med = float(np.median(list(nb.values())))
    yp, yn = (int(x) for x in mi["years_pos"].split("/"))
    rho = cor["main"]["corr_with_sum_of_ten"]
    crit = {
        "n>=250": {"value": mi["n"], "threshold": ">= 250 trades", "pass": mi["n"] >= 250},
        "pf>=1.12": {"value": mi["pf"], "threshold": ">= 1.12", "pass": mi["pf"] >= 1.12},
        "t>=2.5": {"value": mi["t_stat"], "threshold": ">= 2.5", "pass": mi["t_stat"] >= 2.5},
        "years_pos>=60%": {"value": mi["years_pos"], "threshold": ">= 60 % of years (6 of 9)", "pass": yp >= 0.6 * yn},
        "stress_pf>=1.04": {"value": ms["pf"], "threshold": "PF >= 1.04 at costs x1.5", "pass": ms["pf"] >= 1.04},
        "neighbours_median_pf>=1.06": {"value": round(med, 4), "threshold": "median PF of the six neighbours >= 1.06",
                                       "neighbours": nb, "pass": med >= 1.06},
        "every_signal_exp>0": {"value": me["expectancy_R"], "threshold": "> 0 R", "pass": me["expectancy_R"] > 0,
                               "identical_to_main_run": me["identical_to_main_run"]},
        "max_hold<=5d": {"value": f"{mi['max_hold_min']} min", "threshold": "<= 5 trading days (192 h)",
                         "pass": mi["max_hold_h"] <= 192},
        "null>=97.5pct": {"value": nul["percentile"], "threshold": ">= 97.5th percentile of 200 random-time replays",
                          "rule_mean_R": nul["rule_mean_R"], "null_mean_R": nul["null_mean_R"], "null_p975_R": nul["null_p975_R"],
                          "pass": nul["percentile"] >= 97.5},
        "abs_weekly_corr_with_ten<=0.30": {"value": rho, "threshold": "|rho| <= 0.30 (weekly R, 2014-2021)",
                                           "pass": abs(rho) <= 0.30},
    }
    main_pass = bool(all(v["pass"] for v in crit.values()))
    lab = r2.is_criteria(m["r2_evaluate"], neighbor_median_pf=med)        # the lab's own function, same numbers
    agree = {k: lab[k] == crit[k2]["pass"] for k, k2 in (("n>=250", "n>=250"), ("pf>=1.12", "pf>=1.12"), ("t>=2.5", "t>=2.5"),
                                                           ("years_pos>=60%", "years_pos>=60%"), ("max_hold<=5d", "max_hold<=5d"),
                                                           ("stress_pf>=1.04", "stress_pf>=1.04"),
                                                           ("every_signal_exp>0", "every_signal_exp>0"),
                                                           ("neighbors_median_pf>=1.06", "neighbours_median_pf>=1.06"))}
    assert all(agree.values()), (lab, agree)
    gross, net = mg["bp_gross_per_trade"], mi["bp_net_per_trade"]
    prior = {
        "said_before_the_run": ("Addendum K: the lab's 2013-2021 hour table shows about +0.8 bp gross for the two hours after "
                                "the reopen (18:00 New York +0.23 bp, 19:00 New York +0.57 bp, all evenings), against about "
                                "+2.5 bp needed for t >= 2.5 after costs; the prior of a pass is low."),
        "measured_gross_bp_per_trade": gross, "measured_net_bp_per_trade": net,
        "measured_cost_bp_per_trade": round(gross - net, 3), "measured_t": mi["t_stat"],
        "gross_bp_needed_for_t_2.5_at_this_cost_and_spread": None,
    }
    # what gross edge would t = 2.5 have needed with the same trade-to-trade spread of results (information only)
    t1 = __import__("pandas").read_parquet(os.path.join(C.OUT, "trades_01_main.parquet"))
    sd_bp = float((t1.pnl / t1.entry * 1e4).std(ddof=1))
    need_net = 2.5 * sd_bp / np.sqrt(len(t1))
    prior["sd_net_bp_per_trade"] = round(sd_bp, 2)
    prior["net_bp_needed_for_t_2.5"] = round(float(need_net), 2)
    prior["gross_bp_needed_for_t_2.5_at_this_cost_and_spread"] = round(float(need_net + (gross - net)), 2)
    prior["mid_moves_same_evenings_information_only"] = mid_moves()
    neighbours = [{"label": c["name"], "n": L[c["name"]]["is"]["n"], "pf": L[c["name"]]["is"]["pf"],
                   "t": L[c["name"]]["is"]["t_stat"], "expectancy_R": L[c["name"]]["is"]["expectancy_R"],
                   "total_R": L[c["name"]]["is"]["total_R"], "years_pos": L[c["name"]]["is"]["years_pos"],
                   "bp_net_per_trade": L[c["name"]]["is"]["bp_net_per_trade"],
                   "bp_gross_per_trade": L[c["name"]]["is_gross"]["bp_gross_per_trade"],
                   "stress_pf": L[c["name"]]["is_stress"]["pf"]} for c in decl["configurations"][1:]]
    out = {
        "what": "Gold daily-reopen drift (PROTOCOL_V3 Addendum K, round 5): verdict on the main configuration, in sample "
                "2013-2021 only",
        "declared_sha256": sha, "declared_utc": decl["_written_utc"],
        "main_pass": main_pass,
        "verdict_text": ("PASS in sample: next step would be the independent re-implementation attack" if main_pass else
                         "FAIL in sample: nothing is attacked, nothing is kept, no look at 2022-2025 is declared"),
        "criteria": crit,
        "lab_is_criteria_agrees": agree,
        "main": {k: mi[k] for k in ("n", "pf", "t_stat", "expectancy_R", "total_R", "years_pos", "win_rate", "avg_win_R",
                                    "avg_loss_R", "max_dd_R", "bp_net_per_trade", "mean_risk_bp", "median_risk_bp",
                                    "mean_h1_range_usd", "n_stop_exits", "n_time_exits", "n_entry_delayed_over_5min",
                                    "n_exit_moved_before_gap", "max_hold_min", "by_year_R", "by_year", "by_weekday", "by_ny_dst")},
        "main_stress_x1.5": ms, "main_gross": mg, "main_every_signal": me,
        "main_first_entry": m["first_entry"], "main_last_exit": m["last_exit"],
        "neighbours": neighbours, "neighbours_median_pf": round(med, 4),
        "null_main": nul, "correlation_2014_2021": cor["main"], "correlation_n_weeks": cor["n_weeks"],
        "comparison_with_addendum_k_prior": prior,
        "trials_logged_this_round": len(trials),
        "handcheck": {k: hc[k] for k in ("n_checked", "n_core", "core_regimes", "any_stop_out_in_sample", "all_match", "max_abs_R_diff")},
        "sessions": {"candidate_evenings": pre["candidate_evenings"], "skipped_by_first_reason": pre["skipped_by_first_reason_all_years"],
                     "calendar_skips_per_year": pre["calendar_skips_per_year"],
                     "sessions_per_year": {y: v["sessions_main"] for y, v in pre["per_year"].items()},
                     "entries_delayed_over_5_min": pre["entry_delays_main"]["over_5_min"]},
        "in_sample_only": {"frames_cut_while_read": True, "val_access_log_unchanged": run["val_access_log_sha256_before"] ==
                           run["val_access_log_sha256_after"], "val_access_log_sha256": run["val_access_log_sha256_after"]},
        "changes_after_first_numbers": [
            "None to declared.json, to the rule or to the code that produced the judged numbers (declared.json sha256 "
            "unchanged and checked by every script).",
            "Added after the first numbers, information only and not judged: the pure mid-price moves on the main's evenings "
            "(comparison_with_addendum_k_prior.mid_moves_same_evenings_information_only), to compare like for like with "
            "Addendum K's hour-table figure."],
    }
    C.jdump(out, os.path.join(C.OUT, "results.json"))
    print(json.dumps({"main_pass": main_pass, "criteria": {k: (v["value"], v["pass"]) for k, v in crit.items()},
                      "neighbours_median_pf": round(med, 4), "prior": prior}, indent=1))


if __name__ == "__main__":
    main()
