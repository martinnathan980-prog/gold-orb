"""PROTOCOL_V3 addendum G, ninth clarification (2026-11-13): the gain for the risk, between 3 % and 10 %.
D2's shape scaled by its starting risk X (X % per trade below 3,000 EUR, X/2 % below 10,000, X/5 % below 20,000,
X/10 % above, read on the larger of the balance and the money paid in, no plan stop): plans S3, S5, S6, S7, S8, S10.
S10 is D2 itself, run again as a check that the engine reproduces its stored cells exactly.

    python3 r2/tracks/stake/scaled_summary.py PATHS.npz

Reads only result files, never the trades:
  * results/r2/stake/growth_scaled.json  written by `growth.py val results/r2/stake/growth_scaled.json` (the whole engine,
                                         new plans included);
  * results/r2/stake/growth.json         the stored run (F3S and D2 for reference, and the D2 check);
  * PATHS.npz                            the month-end balances of all 2,000 paths, written by the engine itself with
                                         `growth.py dump PATHS.npz 2000` (same draws, path k is the same path).
Writes results/r2/stake/scaled_summary.json with, for each plan and case, exactly the measures the declaration lists.
Nothing is chosen here: the user picks the X.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "..", "results", "r2", "stake"))
SCALED = ("S3", "S5", "S6", "S7", "S8", "S10")
REFERENCE = ("F3S", "D2")
CASES = {"paper": "1.0", "without_2024": "1.0_no2024", "half": "0.5", "quarter": "0.25", "covers_costs": "0.0",
         "worthless": "-0.5"}
TARGET = 10000.0
BY_MONTHS = (4, 6, 9)
SAID_WITH_IT = ("The validation years 2022-2025, so optimistic. The broker's margin on crypto is not modelled (it may "
                "refuse some trades at the larger stakes). No plan stop and no disaster guard in these plans. Nothing is "
                "chosen here: the user picks the X.")


def leaves(obj, path=()):
    """Every leaf of a JSON tree, with its path."""
    if isinstance(obj, dict):
        for k in obj:
            yield from leaves(obj[k], path + (str(k),))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leaves(v, path + (str(i),))
    else:
        yield path, obj


def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def same(a, b):
    if is_number(a) and is_number(b):
        return a == b or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))
    return type(a) is type(b) and a == b


def compare(new, old):
    """Compare two JSON trees leaf by leaf: (numbers compared, other leaves compared, differences)."""
    a, b = dict(leaves(new)), dict(leaves(old))
    diffs = []
    for p in sorted(set(a) | set(b)):
        if p not in a or p not in b:
            diffs.append({"where": "/".join(p), "new": a.get(p, "<missing>"), "stored": b.get(p, "<missing>")})
        elif not same(a[p], b[p]):
            diffs.append({"where": "/".join(p), "new": a[p], "stored": b[p]})
    n_num = sum(1 for p in a if p in b and is_number(a[p]) and is_number(b[p]))
    return n_num, len(set(a) & set(b)) - n_num, diffs


def check_paths(npz, plan, case_key, cell):
    """The per-path balances must be those the engine summarised: percentile curves, mean curve, the first 40 sample
    paths and the gains after 1, 2 and 3 years, recomputed from the paths, equal to the stored figures exactly."""
    m = npz[f"{plan}_{case_key}"]
    paid = npz[f"paid_{plan}_{case_key}"]
    bad = []
    pc = np.percentile(m, (10, 25, 50, 75, 90), axis=0)
    for i, q in enumerate((10, 25, 50, 75, 90)):
        if [round(float(v), 0) for v in pc[i]] != cell["percentiles_by_month"][str(q)]:
            bad.append(f"percentile {q}")
    if [round(float(v), 0) for v in m.mean(axis=0)] != cell["mean_by_month"]:
        bad.append("mean")
    k = len(cell["sample_paths"]["balance"])
    if [[round(float(z), 0) for z in m[j]] for j in range(k)] != cell["sample_paths"]["balance"]:
        bad.append("sample paths")
    gains = m - paid
    for h in (12, 24, 36):
        got = (round(float(np.median(gains[:, h])), 0), round(float(np.percentile(gains[:, h], 10)), 0))
        if got != (cell[f"at_{h}_months"]["gain_median"], cell[f"at_{h}_months"]["gain_p10"]):
            bad.append(f"gain at {h} months")
    return m.shape, bad


def months_to_target(m):
    """From the month-end balances of every path (column 0 = the start, column h = the end of month h): the first month
    at or above TARGET on each path, then the median month and the shares of paths by the given months."""
    hit = m >= TARGET
    first = np.where(hit.any(axis=1), hit.argmax(axis=1), np.inf)       # inf = not reached within the 36 months
    share = lambda h: float(np.mean(first <= h))
    months = range(1, m.shape[1])
    median = next((h for h in months if share(h) >= 0.5), None)          # the first month by which half the paths got there
    reached = first[np.isfinite(first)]
    engine_rule = int(np.median(np.where(np.isfinite(first), first, 10 ** 6))) if len(reached) >= 0.5 * len(first) else None
    out = {"median_month": median, **{f"by_month_{h}_pct": round(100 * share(h), 1) for h in BY_MONTHS}}
    return out, engine_rule


def measures(cell, m):
    a12, a36, fl = cell["at_12_months"], cell["at_36_months"], cell["falls"]
    to_target, engine_rule = months_to_target(m)
    return {
        "months_to_10000_eur": to_target,
        "gain_after_1_year_eur": {"median": a12["gain_median"], "p10": a12["gain_p10"]},
        "gain_after_3_years_eur": {"median": a36["gain_median"], "p10": a36["gain_p10"]},
        "first_year_fall": {"typical_pct": fl["fall_first_52_weeks_pct"]["median"], "p90_pct": fl["fall_first_52_weeks_pct"]["p90"],
                            "typical_eur": fl["fall_first_52_weeks_eur"]["median"], "p90_eur": fl["fall_first_52_weeks_eur"]["p90"]},
        "fall_of_50_pct_or_more_pct": cell["shares_of_paths_pct"]["fall_of_50_pct_or_more"],
        "reaches_zero_pct": cell["balance_reaches_zero_pct"],
    }, engine_rule


def main(paths_file):
    new = json.load(open(os.path.join(OUT, "growth_scaled.json")))
    old = json.load(open(os.path.join(OUT, "growth.json")))
    npz = np.load(paths_file)

    # 1. S10 against the stored D2 cells of growth.json: every number of every case
    d2 = {"numbers_compared": 0, "other_leaves_compared": 0, "differences": [], "by_case": {}}
    for name, key in CASES.items():
        n_num, n_other, diffs = compare(new["resampled"]["S10"][key], old["resampled"]["D2"][key])
        d2["by_case"][name] = {"numbers_compared": n_num, "differences": len(diffs)}
        d2["numbers_compared"] += n_num
        d2["other_leaves_compared"] += n_other
        d2["differences"] += [dict(case=name, **x) for x in diffs]
    n_num, _, diffs = compare(new["real_order"]["schedules"]["S10"], old["real_order"]["schedules"]["D2"])
    d2["real_order_2022_2025"] = {"numbers_compared": n_num, "differences": diffs}
    d2["identical"] = not d2["differences"] and not diffs

    # 2. the whole stored file: growth_scaled.json with the six added plans taken out must equal growth.json leaf by leaf
    trimmed = json.load(open(os.path.join(OUT, "growth_scaled.json")))
    for plan in SCALED:
        for table in (trimmed["schedules"], trimmed["resampled"], trimmed["real_order"]["schedules"]):
            table.pop(plan)
    trimmed["keyed_on_max_of_balance_and_paid"] = [p for p in trimmed["keyed_on_max_of_balance_and_paid"] if p not in SCALED]
    n_num, n_other, diffs = compare(trimmed, old)
    rest = {"plans": len(old["resampled"]), "numbers_compared": n_num, "other_leaves_compared": n_other, "differences": diffs}

    # 3. the per-path file is the summarised run: checked against growth_scaled.json (new plans) and growth.json (F3S, D2)
    path_check = {"cells": 0, "paths_per_cell": None, "failures": []}
    for plan in SCALED + REFERENCE:
        src = new if plan in SCALED else old
        for name, key in CASES.items():
            shape, bad = check_paths(npz, plan, key, src["resampled"][plan][key])
            path_check["cells"] += 1
            path_check["paths_per_cell"] = shape[0]
            path_check["failures"] += [f"{plan} {name}: {b}" for b in bad]
    same_paths = all(np.array_equal(npz[f"S10_{k}"], npz[f"D2_{k}"]) for k in CASES.values())

    # 4. the measures of the declaration
    summary, rule_notes = {}, []
    for plan in SCALED + REFERENCE:
        src = new if plan in SCALED else old
        summary[plan] = {}
        for name, key in CASES.items():
            summary[plan][name], engine_rule = measures(src["resampled"][plan][key], npz[f"{plan}_{key}"])
            if engine_rule != summary[plan][name]["months_to_10000_eur"]["median_month"]:
                rule_notes.append(f"{plan} {name}: engine's int(median) rule gives {engine_rule}")

    plans = {}
    for plan in SCALED + REFERENCE:
        src = new if plan in SCALED else old
        base = src["stopped"][plan]["plan"] if plan in src["stopped"] else plan        # F3S is built on F3
        assert base in src["keyed_on_max_of_balance_and_paid"]
        thr, pct = src["schedules"][base]["thresholds_eur"], src["schedules"][base]["risk_pct"]
        plans[plan] = {"thresholds_eur": thr, "risk_pct": pct, "read_on": "the larger of the balance and the money paid in",
                       "stop": None, "source": "growth_scaled.json" if plan in SCALED else "growth.json"}
        if plan in SCALED:
            plans[plan]["x_pct"] = pct[0]
    plans["F3S"]["stop"] = {"at_fall_of_reference": old["stopped"]["F3S"]["stop_at_fall_of_reference"],
                            "armed_once_paid_in_eur": old["stopped"]["F3S"]["armed_once_paid_in"]}
    out = {
        "protocol": "PROTOCOL_V3 addendum G, ninth clarification (2026-11-13), declared before the run",
        "made_by": ["python3 r2/tracks/stake/growth.py val results/r2/stake/growth_scaled.json  (the whole engine: no "
                    "option runs only some plans; one logged read of 2022-2025)",
                    "python3 r2/tracks/stake/growth.py dump PATHS.npz 2000  (the month-end balances of all 2,000 paths, "
                    "same draws; one logged read of 2022-2025; the file is not kept in the repository)",
                    "python3 r2/tracks/stake/scaled_summary.py PATHS.npz  (this file: reads only the result files)"],
        "period": new["period"], "paths": new["paths"], "months": new["months"], "seed": new["seed"],
        "money": "1,000 EUR at the start and 1,000 EUR a month (36,000 EUR paid in after 3 years)",
        "cases": {name: f"edge key {key} in growth_scaled.json / growth.json" for name, key in CASES.items()},
        "plans": plans,
        "definitions": {
            "months_to_10000_eur": "from the month-end balances of each of the 2,000 paths (per-path data, not percentile "
                                   "curves): the first month whose end balance is at or above 10,000 EUR; median_month = the "
                                   "first month by which at least half the paths got there (null = fewer than half within 36 "
                                   "months); by_month_h_pct = share of paths that got there at the end of month h or earlier",
            "gain_after_1_year_eur / gain_after_3_years_eur": "balance minus the money paid in at the end of month 12 / 36, per "
                                                              "path; median and p10 (one path in ten does worse)",
            "first_year_fall": "the deepest fall within the first 52 weeks, payments set aside (share of the money paid in + "
                               "best gain so far, and in EUR): typical = median, p90 = one path in ten falls more",
            "fall_of_50_pct_or_more_pct": "share of paths whose deepest fall over the 3 years, payments set aside, is 50 % or more",
            "reaches_zero_pct": "share of paths whose balance reaches zero at least once",
        },
        "summary": summary,
        "check_S10_equals_stored_D2": d2,
        "check_rest_of_growth_json_reproduced": rest,
        "check_per_path_file": {**path_check, "S10_and_D2_paths_identical": bool(same_paths), "median_rule_notes": rule_notes},
        "said_with_it": SAID_WITH_IT,
    }
    json.dump(out, open(os.path.join(OUT, "scaled_summary.json"), "w"), indent=1)

    print(f"S10 vs stored D2: {d2['numbers_compared']} numbers in {len(CASES)} cases, {len(d2['differences'])} differences; "
          f"real order {d2['real_order_2022_2025']['numbers_compared']} numbers, {len(d2['real_order_2022_2025']['differences'])} differences")
    print(f"rest of growth.json: {rest['plans']} plans, {rest['numbers_compared']} numbers, {len(rest['differences'])} differences")
    print(f"per-path file: {path_check['cells']} cells x {path_check['paths_per_cell']} paths, failures {path_check['failures']}, "
          f"S10 = D2 path by path: {same_paths}, median rule notes {rule_notes}")
    head = (f"{'plan':5s} {'X':>3s} | {'10k med':>7s} {'by4':>5s} {'by6':>5s} {'by9':>5s} | {'1y med':>8s} {'1y p10':>8s} | "
            f"{'3y med':>8s} {'3y p10':>8s} | {'fall1y %':>8s} {'p90':>5s} {'EUR':>6s} {'p90':>6s} | {'>=50%':>5s} {'zero':>5s}")
    for name in CASES:
        print(f"\n{name}\n{head}")
        for plan in SCALED + REFERENCE:
            r = summary[plan][name]
            t, g1, g3, f1 = r["months_to_10000_eur"], r["gain_after_1_year_eur"], r["gain_after_3_years_eur"], r["first_year_fall"]
            x = f"{plans[plan]['x_pct']:g}" if plan in SCALED else "ref"
            med = "-" if t["median_month"] is None else str(t["median_month"])
            print(f"{plan:5s} {x:>3s} | {med:>7s} {t['by_month_4_pct']:5.1f} {t['by_month_6_pct']:5.1f} {t['by_month_9_pct']:5.1f} | "
                  f"{g1['median']:8,.0f} {g1['p10']:8,.0f} | {g3['median']:8,.0f} {g3['p10']:8,.0f} | {f1['typical_pct']:8.1f} "
                  f"{f1['p90_pct']:5.1f} {f1['typical_eur']:6,.0f} {f1['p90_eur']:6,.0f} | {r['fall_of_50_pct_or_more_pct']:5.1f} "
                  f"{r['reaches_zero_pct']:5.1f}")


if __name__ == "__main__":
    main(sys.argv[1])
