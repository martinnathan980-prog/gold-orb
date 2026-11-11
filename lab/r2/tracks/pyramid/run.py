"""Runner of track `pyramid` (draft Addendum F). IN SAMPLE ONLY.

    python3 lab/r2/tracks/pyramid/run.py      -> results/r2/pyramid/{checks,descriptive,portfolio,control,
                                                 small_accounts,summary}.json and results/r2/pyramid/run_log.jsonl

Every trades file is cut at entry_time < 2022-01-01 when it is read and the prices are loaded with
r2.load(sym, end="2022-01-01") (pyramid.build refuses anything else). Order of the work, logged:
self-checks and descriptive table (whole in-sample period, then common period), the reference and the 24 declared
configurations in the order of pyramid.CONFIGS, the zero-edge control (200 draws), the selection by the rule
declared in pyramid.py, the small-account readings.
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyramid as P  # noqa: E402
import study  # noqa: E402
import small as SM  # noqa: E402
import account as A  # noqa: E402  (r2/tracks/stake/account.py)

S = P.S


def extra_checks(out):
    """Checks that need the stake study: same reference, same account loop."""
    pw, aw, fr, a = out["_frames"]
    ck = {}
    ref = out["portfolio"]["reference"]
    with open(os.path.join(S.OUT, "trials.jsonl")) as fh:
        st = json.loads(fh.readline())["is"]["net_common"]["equal_stake"]          # trial 1 = the reference, in sample
    keys = ("total", "max_dd", "worst_week", "worst_day", "win_days_pct", "win_weeks_pct", "win_months_pct", "longest_red_weeks")
    ck["reference_vs_stake_study_in_sample"] = {k: [ref[k], st[k]] for k in keys}
    ck["reference_vs_stake_study_in_sample"]["n_trades"] = [ref["n_parents"], st["n_trades"]]
    ck["reference_equals_stake_study"] = bool(all(ref[k] == st[k] for k in keys) and ref["n_parents"] == st["n_trades"])
    # the parents of the frame are the stake study's frame, row for row
    d0 = S.subset("net", "common")
    par = fr[fr.is_add == 0].reset_index(drop=True)
    ck["parents_frame_identical_to_stake_frame"] = bool(len(d0) == len(par) and (d0.sleeve.to_numpy() == par.sleeve.to_numpy()).all()
                                                        and (d0.t_in.to_numpy() == par.t_in.to_numpy()).all() and (d0.R.to_numpy() == par.R.to_numpy()).all())
    # small-account loop: the reference equals the stake study's account loop
    same = {}
    for start in (1000.0, 5000.0, 12000.0):
        mine = out["small_accounts"][f"{start:.0f}"]["reference"]
        theirs = A.account({}, start, 1.0, d=A.frame(d=d0, price_level="today"), compound=False)
        same[f"{start:.0f}"] = {"final": [mine["final"], theirs["final"]], "taken": [mine["parents_taken"], theirs["n_taken"]],
                                "max_dd_pct": [mine["max_dd_pct"], theirs["max_dd_pct"]], "worst_week_pct": [mine["worst_week_pct"], theirs["worst_week_pct"]]}
    ck["small_account_reference_vs_stake_account_loop"] = same
    ck["small_account_reference_equals_stake_account_loop"] = bool(all(v["final"][0] == v["final"][1] and v["taken"][0] == v["taken"][1]
                                                                       and v["max_dd_pct"][0] == v["max_dd_pct"][1] for v in same.values()))
    # the account loop without constraints (huge account, no cap, period prices) equals the ideal accounting
    d = SM.frame(fr, price_level="is")
    free = {}
    for name in ("F1_k1_n1_f1_all", "F1_k2_n2_f0.5_all", "F2_k1_n2_all", "F2_k2_n1_trend"):
        cfg = dict(P.CONFIGS)[name]
        x = SM.account(d, cfg, 1e10, max_positions=10 ** 6, max_per_sym=10 ** 6, kill_dd=1e9)
        free[name] = {"account_total_pct": x["total_pct"], "ideal_total": out["portfolio"][name]["total"],
                      "account_addons": x["addons_taken"], "ideal_addons": out["portfolio"][name]["n_addons"],
                      "account_max_dd_pct": x["max_dd_pct"], "ideal_max_dd": round(out["portfolio"][name]["max_dd"], 1)}
    ck["account_loop_without_constraints_vs_ideal"] = free
    ck["account_loop_without_constraints_equals_ideal"] = bool(all(abs(v["account_total_pct"] - v["ideal_total"]) < 0.11 and v["account_addons"] == v["ideal_addons"]
                                                                   for v in free.values()))
    return ck


if __name__ == "__main__":
    t0 = time.time()
    P.log("run_start", script="run.py")
    out = study.look(None, P.COMMON_START, P.IS_END, "2022-01-01", last_year=2021, n_draws=200, t_min=2.5, log_runs=True)
    pub = study.public(out)
    pub["checks_totals"] = study.totals(out["checks"])
    pub["checks_stake_study"] = extra_checks(out)
    dump = lambda name, obj: json.dump(obj, open(os.path.join(P.OUT, name), "w"), indent=1)
    dump("checks.json", {"totals_whole_in_sample": pub["checks_totals"], "stake_study": pub["checks_stake_study"], "per_rule": pub["checks"],
                         "trend_scope": pub["trend_scope"], "f2_addons_per_rule_common": pub["f2_addons_per_rule"]})
    dump("descriptive.json", {"whole_in_sample_2013_2021": pub["descriptive_whole"], "common_2018_02_2021": pub["descriptive"]})
    dump("portfolio.json", {"window": pub["window"], "portfolio": pub["portfolio"], "criteria": pub["criteria"],
                            "finalist_by_the_declared_rule": pub["finalist_by_the_declared_rule"]})
    dump("control.json", {"meta": pub["control_meta"], "control": pub["control"]})
    dump("small_accounts.json", pub["small_accounts"])
    dump("summary.json", {"window": pub["window"], "finalist_by_the_declared_rule": pub["finalist_by_the_declared_rule"],
                          "passing": [n for n, _ in P.CONFIGS if pub["criteria"][n]["pass"]], "reference": pub["portfolio"]["reference"]})
    P.log("run_end", seconds=round(time.time() - t0), finalist=pub["finalist_by_the_declared_rule"])
    print(json.dumps(pub["checks_totals"], indent=1))
    print(json.dumps(pub["checks_stake_study"], indent=1))
    print(study.table(out))
    print("finalist:", pub["finalist_by_the_declared_rule"], f"[{time.time() - t0:.0f}s]")
