"""PROTOCOL_V3 addendum G, seventh clarification: a monthly check before the stop of the plan is armed.

    python3 r2/tracks/stake/control.py dry     # in sample, 50 paths: nothing is written
    python3 r2/tracks/stake/control.py val     # 2022-2025 (logged access): writes results/r2/stake/control.json

At each month end 1..11 the robot's gain (balance minus money paid in) is compared with an orange line (10th percentile
of the half-edge paths) and a red line (the q-th percentile, the same q every month, the largest q for which at most
5 % of the half-edge paths are ever below it). Rule tested: stop for good at the first month end below the red line.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import growth as G  # noqa: E402

LAST = 11                                        # months 1..LAST: before the twelfth payment arms the stop
FALSE_CUTS = 5.0                                 # % of half-edge paths the red line may cut
GRID = np.arange(0.1, 10.0001, 0.1)              # candidate percentiles for the red line
SCEN = [(1.0, "paper"), (G.NO_2024, "paper_without_2024"), (0.5, "half"), (0.25, "quarter"), (0.0, "covers_costs"), (-0.5, "worthless")]


def gains(x, months, n_paths, seed):
    G.PLANS = G.LADDER                           # the engine loops over the module's plan list
    res, fired, zero, paid_m, n_weeks = G.resampled(x, months=months, n_paths=n_paths, seed=seed)
    paid = G.resampled.paid_in
    return {s: {f: res[s][f] - paid[s][f] for f in res[s]} for s in res}


def red_line(g_half):
    """`g_half`: paths x months 1..LAST. Returns (q, line): the largest q of GRID with at most FALSE_CUTS % of paths ever below."""
    best = None
    for q in GRID:
        line = np.percentile(g_half, q, axis=0)
        if 100.0 * (g_half < line).any(axis=1).mean() <= FALSE_CUTS:
            best = (float(q), line)
    return best


def cut_month(g, line):
    """First month (1-based) below the line, 0 when never. `g`: paths x months 1..LAST."""
    below = g < line
    return np.where(below.any(axis=1), below.argmax(axis=1) + 1, 0)


def stats(v):
    return {"median": round(float(np.median(v)), 0), "p10": round(float(np.percentile(v, 10)), 0), "p90": round(float(np.percentile(v, 90)), 0)}


def main(period):
    d = G.load(period)
    x = G.arrays(d, "today")
    months, n = (36, G.N_PATHS) if period == "val" else (12, 50)
    g = gains(x, months, n, G.SEED)
    g2 = gains(x, months, n, G.SEED + 2)         # other draws: the false-cut rate is measured there
    out = {"protocol": "PROTOCOL_V3 addendum G, seventh clarification", "months_checked": LAST, "false_cuts_allowed_pct": FALSE_CUTS,
           "paths": n, "seed": G.SEED, "other_draws_seed": G.SEED + 2, "plans": {}}
    for s in G.LADDER:
        half = g[s][0.5][:, 1:LAST + 1]
        q, red = red_line(half)
        orange = np.percentile(half, 10, axis=0)
        row = {"q_pct": round(q, 1), "red_line_by_month": [round(float(v), 0) for v in red], "orange_line_by_month": [round(float(v), 0) for v in orange],
               "scenarios": {}}
        for f, name in SCEN:
            gm = g[s][f]
            cm = cut_month(gm[:, 1:LAST + 1], red)
            end = gm[:, -1]
            with_rule = np.where(cm > 0, gm[np.arange(len(gm)), cm], end)
            cut = cm > 0
            r = {"cut_pct": round(float(100 * cut.mean()), 1), "cut_before_month_9_pct": round(float(100 * ((cm > 0) & (cm < 9)).mean()), 1),
                 "median_month_of_the_cut": (float(np.median(cm[cut])) if cut.any() else None),
                 "gain_at_the_end_without_the_rule": stats(end), "gain_at_the_end_with_the_rule": stats(with_rule),
                 "cut_paths_gain_when_cut": (stats(with_rule[cut]) if cut.any() else None),
                 "cut_paths_gain_at_the_end_without_the_rule": (stats(end[cut]) if cut.any() else None)}
            g2m = g2[s][f]
            cm2 = cut_month(g2m[:, 1:LAST + 1], red)
            r["other_draws"] = {"cut_pct": round(float(100 * (cm2 > 0).mean()), 1), "cut_before_month_9_pct": round(float(100 * ((cm2 > 0) & (cm2 < 9)).mean()), 1),
                                "gain_at_the_end_without_the_rule": stats(g2m[:, -1]),
                                "gain_at_the_end_with_the_rule": stats(np.where(cm2 > 0, g2m[np.arange(len(g2m)), cm2], g2m[:, -1]))}
            row["scenarios"][name] = r
        w = row["scenarios"]["worthless"]
        saved = w["gain_at_the_end_with_the_rule"]["median"] - w["gain_at_the_end_without_the_rule"]["median"]
        row["offered"] = bool(w["cut_before_month_9_pct"] >= 50.0 and saved >= 500.0)
        row["median_loss_saved_when_worthless_eur"] = round(float(saved), 0)
        out["plans"][s] = row
        print(f"{s:5s} red line = percentile {q:4.1f} | red {row['red_line_by_month']} | orange {row['orange_line_by_month']}")
        for f, name in SCEN:
            r = row["scenarios"][name]
            print(f"      {name:18s} cut {r['cut_pct']:5.1f} % (before month 9: {r['cut_before_month_9_pct']:5.1f} %, median month {r['median_month_of_the_cut']}) | "
                  f"end without {r['gain_at_the_end_without_the_rule']['median']:>8,.0f} ({r['gain_at_the_end_without_the_rule']['p10']:>8,.0f}) "
                  f"with {r['gain_at_the_end_with_the_rule']['median']:>8,.0f} ({r['gain_at_the_end_with_the_rule']['p10']:>8,.0f}) | "
                  f"cut paths: at the cut {r['cut_paths_gain_when_cut']['median'] if r['cut_paths_gain_when_cut'] else None}, without the rule "
                  f"{r['cut_paths_gain_at_the_end_without_the_rule']['median'] if r['cut_paths_gain_at_the_end_without_the_rule'] else None} | other draws: cut {r['other_draws']['cut_pct']:5.1f} %")
        print(f"      offered: {row['offered']} (worthless robots cut before month 9: {w['cut_before_month_9_pct']} %, median loss saved {saved:,.0f} EUR)")
    if period == "val":
        json.dump(out, open(os.path.join(G.S.OUT, "control.json"), "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
