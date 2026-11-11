"""Track `pyramid`: one code path for the in-sample study (run.py), its dry run and the lead's single look (val.py).

look(build_start, win_start, end, price_end, ...):
    parents entered in [win_start, end) are the accounting window; the prices are cut at `price_end`;
    `build_start` < win_start only adds earlier parents to the descriptive table (run.py: whole in-sample period).
Returns a dict of plain JSON values: self-checks, descriptive tables, the reference and the 24 configurations,
the zero-edge control, the five criteria, the finalist by the declared rule, the small-account readings.
"""
import json

import numpy as np
import pandas as pd

import pyramid as P
import control as C
import small as SM


def _plain(x):
    return json.loads(json.dumps(x, default=str))


def look(build_start, win_start, end, price_end, last_year, n_draws=200, t_min=2.5, log_runs=False, small_starts=(1000.0, 5000.0, 12000.0)):
    ctl = C.Collector(win_start, end, n_draws)
    if log_runs:
        P.log("build_parents_and_addons", window=[str(build_start), str(end)], price_end=str(price_end), control_draws=n_draws)
    parents, addons, rep = P.build(build_start, end, price_end, hook=ctl.hook)
    out = {"window": [str(win_start.date()), str(end.date())], "price_end": str(price_end), "checks": rep}
    if build_start is None or build_start < win_start:
        if log_runs:
            P.log("descriptive_table", period="whole")
        out["descriptive_whole"] = P.describe(parents, addons)
        trend, table = P.trend_sleeves(parents)
        out["trend_scope"] = {"rule": P.TREND_RULE, "sleeves": trend, "table": table, "equals_frozen_TREND": trend == sorted(P.TREND)}
    pw = parents[parents.entry_time >= win_start].reset_index(drop=True)
    aw = addons[addons.pid.isin(pw.pid)].reset_index(drop=True)
    if log_runs:
        P.log("descriptive_table", period="window")
    out["descriptive"] = P.describe(pw, aw)
    res, fr, a = P.evaluate_all(pw, aw, last_year, log_runs)
    out["portfolio"] = res
    # where can F2 ever add: rows whose free-risk budget is > 0, per rule
    m = P.stakes(fr, dict(fam="F2", k=1.0, n=1, f=None, scope="all"), list(P.TREND))
    m2 = P.stakes(fr, dict(fam="F2", k=2.0, n=1, f=None, scope="all"), list(P.TREND))
    add = fr.is_add.to_numpy() == 1
    out["f2_addons_per_rule"] = {s: {"k1": int(((m > 0) & add & (fr.sleeve == s).to_numpy()).sum()), "k2": int(((m2 > 0) & add & (fr.sleeve == s).to_numpy()).sum()),
                                     "candidates_k1": int((add & (fr.level == 1.0) & (fr.sleeve == s)).sum())}
                                 for s in sorted(fr.sleeve.unique())}
    if log_runs:
        P.log("zero_edge_control", draws=n_draws, variants=list(C.VARIANTS))
    carr = ctl.results(last_year)
    out["control"] = {v: C.summary(arr, res["reference"]["total_exact"]) for v, arr in carr.items()}
    out["control_meta"] = {"draws": n_draws, "seed": C.SEED, "asked": ctl.asked, "skipped_because_the_rule_was_already_in_a_trade": ctl.skipped}
    crit = P.criteria(res, out["control"]["coin"] if n_draws else None, t_min)
    out["criteria"] = crit
    out["finalist_by_the_declared_rule"] = P.select(res, crit) or "NONE"
    if log_runs:
        P.log("selection", finalist=out["finalist_by_the_declared_rule"], passing=[n for n, _ in P.CONFIGS if crit[n]["pass"]])
        P.log("small_accounts", starts=list(small_starts))
    out["small_accounts"] = SM.readings(fr, small_starts)
    out["_frames"] = (pw, aw, fr, a)
    return out


def totals(rep):
    t = {"parents_replayed": sum(v["n_resimulated"] for v in rep.values()),
         "replay_vs_simulator_mismatches": sum(v["replay_vs_simulator_mismatches"] for v in rep.values()),
         "saved_vs_resimulated_mismatches": sum(v["saved_vs_resimulated_mismatches"] for v in rep.values()),
         "of_which_open_at_the_end_of_the_price_frame": sum(v["of_which_open_at_the_end_of_the_price_frame"] for v in rep.values()),
         "unexplained_mismatches": sum(v["unexplained_mismatches"] for v in rep.values()),
         "reach_vs_simulator_mfe_mismatches": sum(v["reach_vs_simulator_mfe_mismatches"] for v in rep.values()),
         "addons_checked": sum(v.get("prefix_test_addons_checked", 0) for v in rep.values()),
         "prefix_test_mismatches": sum(v.get("prefix_test_mismatches", 0) for v in rep.values()),
         "addon_resimulated_alone_fill_mismatches": sum(v.get("addon_resimulated_alone_fill_mismatches", 0) for v in rep.values()),
         "addon_resimulated_alone_exit_mismatches": sum(v.get("addon_resimulated_alone_exit_mismatches", 0) for v in rep.values()),
         "addon_resimulated_alone_max_abs_pnl_diff": max(v.get("addon_resimulated_alone_max_abs_pnl_diff", 0.0) for v in rep.values()),
         "addon_exit_equals_parent_exit_all": all(v.get("addon_exit_equals_parent_exit", True) for v in rep.values()),
         "addons_on_parents_open_at_the_end_of_the_frame": sum(v["addons_on_parents_open_at_the_end_of_the_frame"] for v in rep.values())}
    return t


def public(out):
    return _plain({k: v for k, v in out.items() if not k.startswith("_")})


def table(out, top=None):
    """Plain-text table of the reference and the configurations."""
    res, crit = out["portfolio"], out["criteria"]
    ref = res["reference"]
    lines = [f"{'reference':22s} adds {0:5d} total {ref['total']:7.1f} DD {ref['max_dd']:6.2f} worst wk {ref['worst_week']:7.2f} day {ref['worst_day']:6.2f}"
             f" win d/w/m {ref['win_days_pct']:4.1f}/{ref['win_weeks_pct']:4.1f}/{ref['win_months_pct']:4.1f} red {ref['longest_red_weeks']}"
             f" open avg {ref['avg_open_risk']:.2f} max {ref['max_open_risk']:.1f} years {ref['by_year']}"]
    for name, _ in P.CONFIGS:
        x = res[name]
        if x["n_addons"] == 0:
            lines.append(f"{name:22s} adds     0 (no add-on)")
            continue
        e, b, c = x["equal_dd"], x["reference_with_a_bigger_flat_stake_same_total"], crit[name]
        lines.append(
            f"{name:22s} adds {x['n_addons']:5d} total {x['total']:7.1f} DD {x['max_dd']:6.2f} worst wk {x['worst_week']:7.2f} day {x['worst_day']:6.2f}"
            f" win d/w/m {x['win_days_pct']:4.1f}/{x['win_weeks_pct']:4.1f}/{x['win_months_pct']:4.1f} red {x['longest_red_weeks']}"
            f" open avg {x['avg_open_risk']:.2f} max {x['max_open_risk']:.1f} | addR {x['addon_mean_R']:+.3f} t {x['addon_t_by_day']:5.2f}"
            f" add tot {x['addons_total']:7.1f} yrs {x['addons_by_year']} | eqDD x{e['scale']:.3f} profit {e['profit']:7.1f} ({e['profit_vs_ref']:.3f})"
            f" wk {e['worst_week']:7.2f} ({e['worst_week_vs_ref']:.2f}) | flat x{b['flat_stake']:.3f} DD {b['max_dd']:6.2f} wk {b['worst_week']:7.2f}"
            f" | {'PASS' if c['pass'] else 'no'} " + "".join("Y" if v else "n" for k, v in c.items() if isinstance(v, bool) and k != "pass"))
    return "\n".join(lines)
