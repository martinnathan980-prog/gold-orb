"""PROTOCOL_V3, draft Addendum F: the lead's single look at 2022-2025 for the pyramiding finalist, and the same code
path in sample as a dry run.

    python3 r2/tracks/pyramid/val.py dry               # common in-sample period 2018-02..2021: must reproduce the
                                                       # designer's figures (results/r2/pyramid/*.json) exactly
    python3 r2/tracks/pyramid/val.py val [config]      # 2022-2025, ONCE, logged in results/val_access.log,
                                                       # writes results/r2/pyramid/val_look.json

`val` reads the finalist frozen in sample from results/r2/pyramid/summary.json. If it is NONE the script stops:
there is nothing to validate. The lead may name a configuration of pyramid.CONFIGS as a declared deviation
(it is written in the access log). Whatever is looked at, the 2022-2025 window is read once: the reference, the
24 configurations, the descriptive table, the zero-edge control and the small-account readings are all computed
and saved, the pass / fail is given for the frozen finalist only.

Pass criteria on 2022-2025 (Addendum F): the five in-sample criteria with t >= 2.0 instead of 2.5:
  (a) pooled add-on expectancy per unit of its own risk > 0, t clustered by day >= 2.0
  (b) profit at equal drawdown >= 1.15 x the reference's total of 2022-2025
  (c) worst week at equal drawdown <= 1.25 x the reference's
  (d) add-ons alone positive in at least 3 of the 4 years
  (e) zero-edge control (re-entered parents of 2022-2025, 200 draws): no gain in profit at equal drawdown
"""
import datetime as dt
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyramid as P  # noqa: E402
import study  # noqa: E402

WINDOW = {"dry": (P.COMMON_START, P.IS_END, "2022-01-01", 2021, 2.5),
          "val": (pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC"), None, 2025, 2.0)}


def _same(a, b, path=""):
    """First difference between two JSON values (None if identical)."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}/{k}: missing on one side"
            d = _same(a[k], b[k], f"{path}/{k}")
            if d:
                return d
        return None
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            d = _same(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else f"{path}: {a!r} != {b!r}"


def dry():
    start, end, price_end, last_year, t_min = WINDOW["dry"]
    out = study.look(start, start, end, price_end, last_year, n_draws=200, t_min=t_min)
    pub = study.public(out)
    load = lambda name: json.load(open(os.path.join(P.OUT, name)))
    saved_p, saved_c, saved_s, saved_d = load("portfolio.json"), load("control.json"), load("small_accounts.json"), load("descriptive.json")
    diffs = {
        "reference_and_24_configurations": _same(pub["portfolio"], saved_p["portfolio"]),
        "criteria": _same(pub["criteria"], saved_p["criteria"]),
        "finalist": _same(pub["finalist_by_the_declared_rule"], saved_p["finalist_by_the_declared_rule"]),
        "zero_edge_control": _same(pub["control"], saved_c["control"]),
        "small_accounts": _same(pub["small_accounts"], saved_s),
        "descriptive_table_common_period": _same(pub["descriptive"], saved_d["common_2018_02_2021"]),
    }
    print(study.table(out))
    print("finalist by the declared rule:", pub["finalist_by_the_declared_rule"])
    tot = study.totals(out["checks"])
    print("self-checks of this run:", json.dumps(tot))
    for k, v in diffs.items():
        print(f"dry run vs saved in-sample figures | {k:34s}: {'IDENTICAL' if v is None else 'DIFFERENT -> ' + v}")
    ok = all(v is None for v in diffs.values())
    print("DRY RUN REPRODUCES THE IN-SAMPLE FIGURES:", ok)
    json.dump({"time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "identical": ok, "differences": diffs,
               "self_checks": tot}, open(os.path.join(P.OUT, "dry_run_check.json"), "w"), indent=1)
    return ok


def val(forced=None):
    summ = json.load(open(os.path.join(P.OUT, "summary.json")))
    finalist = summ["finalist_by_the_declared_rule"]
    names = [n for n, _ in P.CONFIGS]
    if forced is not None:
        assert forced in names, f"unknown configuration {forced}"
    target = forced or finalist
    if target == "NONE":
        print("The in-sample finalist is NONE: nothing to validate. The 2022-2025 window was NOT read.")
        return None
    start, end, price_end, last_year, t_min = WINDOW["val"]
    label = f"pyramid:{target}:lead_single_look" + ("" if forced is None or forced == finalist else ":declared_deviation_from_finalist_" + finalist)
    with open(os.path.join(P.LAB, "results", "val_access.log"), "a") as f:
        f.write(json.dumps({"time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "track": "pyramid",
                            "label": label, "period": "val"}) + "\n")
    os.environ["PYRAMID_VAL_LOOK"] = "lead"            # the only place where pyramid.build accepts a window after 2021
    out = study.look(start, start, end, price_end, last_year, n_draws=200, t_min=t_min)
    pub = study.public(out)
    pub["looked_at"] = target
    pub["in_sample_finalist"] = finalist
    pub["checks_totals"] = study.totals(out["checks"])
    pub["val_criteria_of_the_finalist"] = pub["criteria"][target]
    pub["pass"] = bool(pub["criteria"][target]["pass"])
    try:                                               # the reference of 2022-2025 must be the stake study's
        sv = json.load(open(os.path.join(P.S.OUT, "val_look.json")))["profiles"]["reference"]["as_designed"]
        ref = pub["portfolio"]["reference"]
        pub["reference_vs_stake_study_val"] = {"total": [round(ref["total_exact"], 2), sv["total_pct"]], "max_dd": [ref["max_dd"], sv["max_dd_pct"]],
                                               "worst_week": [ref["worst_week"], sv["worst_week_pct"]]}
    except Exception as e:                             # never blocks the look
        pub["reference_vs_stake_study_val"] = f"not compared ({type(e).__name__})"
    json.dump(pub, open(os.path.join(P.OUT, "val_look.json"), "w"), indent=1)
    print(study.table(out))
    print("self-checks:", json.dumps(pub["checks_totals"]))
    print("reference vs stake study:", pub["reference_vs_stake_study_val"])
    x = pub["portfolio"][target]
    print(f"\nLOOKED AT: {target}\n  add-ons {x['n_addons']}, add-on expectancy {x['addon_mean_R']:+.4f} R (t {x['addon_t_by_day']}), add-ons by year {x['addons_by_year']}"
          f"\n  total {x['total']} against {pub['portfolio']['reference']['total']}; profit at equal drawdown {x['equal_dd']['profit']} = {x['equal_dd']['profit_vs_ref']} x the reference"
          f"\n  worst week at equal drawdown {x['equal_dd']['worst_week']} = {x['equal_dd']['worst_week_vs_ref']} x the reference's"
          f"\n  zero-edge control: {pub['control']['coin'][target]['ratio_equivalent_mean']} {pub['control']['coin'][target]['ratio_equivalent_ci95_of_mean']}"
          f"\n  criteria: {pub['val_criteria_of_the_finalist']}\n  PASS: {pub['pass']}")
    return pub


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "dry":
        sys.exit(0 if dry() else 1)
    elif mode == "val":
        val(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        sys.exit("usage: val.py dry | val.py val [configuration]")
