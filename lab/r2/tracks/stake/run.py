"""Runner of track `stake` (Addendum E). IN SAMPLE ONLY (every trades file is cut at entry < 2022-01-01 on reading).

    python3 lab/r2/tracks/stake/run.py            -> results/r2/stake/trials.jsonl (every configuration, four views)
                                                     and a table on stdout
    python3 lab/r2/tracks/stake/run.py final      -> + self-checks, selection, frozen profiles at their frozen base
                                                     stake, zero-edge controls, crypto diagnostics, account realism:
                                                     results/r2/stake/summary.json
The trades without costs come from gross_is.py (run it once before).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stake as S  # noqa: E402

VIEWS = ("gross_common", "net_common", "gross_whole", "net_whole")
YEARS = {"common": 3.915, "whole": 9.0}          # 2018-02-01..2021-12-31 ; 2012-12-31..2021-12-31


def line(r, view="gross_common"):
    e, s = r["is"][view]["equal_stake"], r["is"][view]["scaled"]
    return (f"{r['trial']:2d} {r['name'][:38]:38s} wk {e['win_weeks_pct']:5.1f} dy {e['win_days_pct']:5.1f} mo {e['win_months_pct']:5.1f}"
            f" | tot {e['total']:7.1f} g/r day {e['avg_green_day']:+5.2f}/{e['avg_red_day']:+6.2f} wD {e['worst_day']:6.1f}"
            f" wW {e['worst_week']:6.1f} DD {e['max_dd']:5.1f} stake {e['avg_stake']:4.2f} skip {e['skipped_pct']:4.1f}% red {e['longest_red_weeks']}"
            f" || x{s['scale']:4.2f} tot {s['total']:6.1f} ({s['total_vs_ref']:4.2f}) wD {s['worst_day']:6.1f} DD {s['max_dd']:5.1f}"
            f" ({s['dd_vs_ref']:4.2f}) {'ok' if s['eligible'] else 'NO'}")


def select(rows, view="gross_common", min_total_share=None):
    """Addendum E: eligible (scaled max drawdown <= reference's), highest winning weeks, tie: highest scaled total."""
    el = [r for r in rows if r["is"][view]["scaled"]["eligible"] and r["trial"] != 1]
    if min_total_share is not None:
        el = [r for r in el if r["is"][view]["scaled"]["total"] >= min_total_share * rows[0]["is"][view]["equal_stake"]["total"]]
    el.sort(key=lambda r: (-r["is"][view]["equal_stake"]["win_weeks_pct"], -r["is"][view]["scaled"]["total"]))
    return el


def selfcheck():
    """No peeking, accounting identities, account loop == engine on an unconstrained account."""
    import account as A
    out = {}
    a = S.arrays("net", "common")
    cfg = S.FROZEN["strong"]["config"]
    m = S.run(a, cfg)
    rng = np.random.default_rng(1)
    ok = True
    for i in rng.integers(100, len(m) - 1, 200):
        R2 = a["R"].copy()
        later = a["t_out"] >= a["t_in"][i]               # everything not closed strictly before the entry of i
        R2[later] = rng.normal(0, 3, later.sum())
        ok &= bool(np.array_equal(S.run(a, cfg, R2)[:i + 1], m[:i + 1]))
    out["stake_of_a_trade_unchanged_when_all_results_not_closed_before_its_entry_are_replaced"] = ok
    st = S.stats(a, S.run(a, {}))
    out["reference_total_equals_sum_of_R"] = bool(abs(st["total"] - a["R"].sum()) < 0.06)
    out["reference_net_common_matches_addendum_E"] = [st["win_days_pct"], st["win_weeks_pct"], st["win_months_pct"]]
    for name in ("reference", "strong"):
        c = {} if name == "reference" else cfg
        r = A.account(c, 1e9, 1.0, compound=False, max_positions=10 ** 6, max_per_sym=10 ** 6)
        e = S.stats(a, S.run(a, c))
        out[f"account_loop_equals_engine_without_constraints_{name}"] = {
            "account": [r["win_weeks_pct"], r["win_days_pct"], r["worst_week_pct"], r["max_dd_pct"]],
            "engine": [e["win_weeks_pct"], e["win_days_pct"], round(e["worst_week"], 1), round(e["max_dd"], 1)]}
    return out


def profile_report(cfg, scale):
    """One rule at a fixed base stake (`scale` x the reference's 1 %): amounts in % of the account, no compounding."""
    out = {}
    for kind in S.KINDS:
        for period in S.PERIODS:
            a = S.arrays(kind, period)
            m = S.run(a, cfg)
            st = S.stats(a, m)
            for k in S.AMOUNTS:
                st[k] = round(float(st[k] * scale), 3)
            st["per_year"] = round(float(st["total"] / YEARS[period]), 1)
            took = m > 0
            wk = np.bincount(a["wk_out"][took], weights=(m * a["R"])[took] * scale, minlength=a["nwk"])
            wn = np.bincount(a["wk_out"][took], minlength=a["nwk"])
            yr = pd.DatetimeIndex(a["week_monday"] + pd.Timedelta(days=3)).year.to_numpy()   # year of the week's Thursday
            by = {}
            for y in np.unique(yr[wn > 0]):
                k = (yr == y) & (wn > 0)
                by["2022-01 (exits of trades entered in Dec 2021)" if y == 2022 else str(int(y))] = {"weeks": int(k.sum()), "win_weeks_pct": round(float(100 * (wk[k] > 0).mean()), 1),
                                   "total": round(float(wk[k].sum()), 1), "worst_week": round(float(wk[k].min()), 2)}
            st["by_year"] = by
            w = wk[wn > 0]
            st["weeks_distribution"] = {"p05": round(float(np.percentile(w, 5)), 2), "p25": round(float(np.percentile(w, 25)), 2),
                                        "median": round(float(np.median(w)), 2), "p75": round(float(np.percentile(w, 75)), 2),
                                        "p95": round(float(np.percentile(w, 95)), 2)}
            st["stake_range_pct_of_account"] = [round(float(m[took].min() * scale), 3), round(float(m.max() * scale), 3)]
            out[f"{kind}_{period}"] = st
    return out


def crypto_diagnostics(rows):
    a = S.arrays("net", "common")
    df = pd.DataFrame({"s": a["sleeve"], "d": a["dy_out"], "w": a["wk_out"], "f": a["fam"], "R": a["R"]})
    tab = df.pivot_table(index="d", columns="s", values="R", aggfunc="sum").fillna(0)
    c = tab.corr()
    fam = df.pivot_table(index="w", columns="f", values="R", aggfunc="sum").fillna(0)
    fam.columns = list(S.FAM_NAMES)
    out = {"daily_R_correlation": {
        "F1 btc / F1 eth": round(float(c.loc["F1_brk_ridge_filter_btcusd", "F1_brk_ridge_filter_ethusd"]), 2),
        "brk72 btc / brk72 eth": round(float(c.loc["brk72_24h_wd_btcusd", "brk72_24h_wd_ethusd"]), 2),
        "noise30 / ocm4 (us100)": round(float(c.loc["noise30_us100", "ocm4_us100"]), 2),
        "mean of the other pairs": round(float((c.values.sum() - 10 - 2 * (c.loc["F1_brk_ridge_filter_btcusd", "F1_brk_ridge_filter_ethusd"]
                                                + c.loc["brk72_24h_wd_btcusd", "brk72_24h_wd_ethusd"] + c.loc["noise30_us100", "ocm4_us100"])) / 84), 3)},
        "weekly_R_by_family": {"sd": fam.std().round(2).to_dict(), "mean": fam.mean().round(2).to_dict(),
                               "sd_of_the_ten_rules_together": round(float(fam.sum(axis=1).std()), 2),
                               "share_of_weekly_variance_from_crypto_pct": round(float(100 * fam["crypto"].var() / fam.sum(axis=1).var()), 0)}}
    comp = {}
    for t in (6, 22, 23, 24):
        r = rows[t - 1]
        m = S.run(a, r["config"])
        st = S.stats(a, m)
        took = m > 0
        wk = np.bincount(a["wk_out"][took], weights=(m * a["R"])[took], minlength=a["nwk"])
        ww = int(np.argmin(wk))
        k = took & (a["wk_out"] == ww)
        z = S.zero_edge(r["config"], "net", "common", 1000)
        zb = S.zero_edge(r["config"], "net", "common", 1000, block=True)
        comp[r["name"]] = {"win_weeks_pct": st["win_weeks_pct"], "worst_week": st["worst_week"], "worst_day": st["worst_day"],
                           "max_open_stake": st["max_open_stake"], "scale": r["is"]["net_common"]["scaled"]["scale"],
                           "total_kept_after_scaling": r["is"]["net_common"]["scaled"]["total_vs_ref"],
                           "worst_week_part_from_crypto": round(float((m * a["R"])[k & (a["fam"] == 2)].sum()), 2),
                           "zero_edge_win_weeks_pct": z["win_weeks_pct"]["mean"],
                           "zero_edge_worst_week_median_independent_signs": z["worst_week"]["median"],
                           "zero_edge_worst_week_median_one_sign_per_family_and_day": zb["worst_week"]["median"]}
    out["catch_up_cap3_by_family_net_common"] = comp
    return out


def account_realism():
    import account as A
    prof = {"reference": ({}, 1.0)}
    for k, v in list(S.FROZEN.items()) + list(S.INFO_ONLY.items()):
        prof[k] = (v["config"], v["base_scale"])
    keep = ("start", "base_pct", "price_level", "compound", "taken_pct", "skipped", "final", "killed_at", "per_year_pct",
            "win_days_pct", "win_weeks_pct", "win_months_pct", "avg_green_day_pct", "avg_red_day_pct", "avg_green_week_pct",
            "avg_red_week_pct", "worst_day_pct", "worst_week_pct", "max_dd_pct", "longest_red_weeks", "avg_real_risk_eur",
            "avg_mult_taken")
    runs = []
    for name, (cfg, sc) in prof.items():
        # (a) the account kept at its size: what the minimum lots do at each size, at 2018-2021 and at today's prices
        for lvl in ("is", "today"):
            for st in (1000, 2000, 3000, 5000, 10000, 20000, 50000):
                for kind in ("net", "gross"):
                    if kind == "gross" and st not in (1000, 20000):
                        continue
                    r = A.account(cfg, float(st), sc, kind=kind, price_level=lvl, compound=False)
                    runs.append({"profile": name, "kind": kind, **{k: r.get(k) for k in keep}})
        # (b) other base stakes on 1,000 EUR at today's prices (reference at 1 / 2 / 3 %: the profile at scale x that)
        for mult in (2.0, 3.0):
            r = A.account(cfg, 1000.0, sc * mult, price_level="today", compound=False)
            runs.append({"profile": name, "kind": "net", **{k: r.get(k) for k in keep}})
        # (c) the lab's usual reading: 1,000 EUR, compounding, 2018-2021 prices and today's
        for lvl in ("is", "today"):
            r = A.account(cfg, 1000.0, sc, price_level=lvl, compound=True)
            runs.append({"profile": name, "kind": "net", **{k: r.get(k) for k in keep}})
    return runs


if __name__ == "__main__":
    rows = S.log_trials()
    for view in VIEWS:
        print("==", view)
        for r in rows:
            print(line(r, view))
    print("trials:", len(rows))
    if len(sys.argv) < 2 or sys.argv[1] != "final":
        sys.exit(0)

    summ = {"track": "stake (PROTOCOL_V3 Addendum E)", "data": "in sample only: entries before 2022-01-01",
            "clock": "FP server time = New York + 7 h; day = server day; week = Monday..Sunday; booking at the exit time",
            "units": "R = % of the account at a 1 % base stake, no compounding (ideal account); account runs in % of the account",
            "trials_logged": len(rows), "trial_budget": 40}
    summ["selfcheck"] = selfcheck()
    # ---- selection (gross, common period), literal
    strong, soft = select(rows)[0], select(rows, min_total_share=2 / 3)[0]
    assert strong["trial"] == S.FROZEN["strong"]["trial"] and soft["trial"] == S.FROZEN["soft"]["trial"]
    top = lambda L: [{"trial": r["trial"], "name": r["name"], "win_weeks_pct": r["is"]["gross_common"]["equal_stake"]["win_weeks_pct"],
                      "scaled_total_vs_ref": r["is"]["gross_common"]["scaled"]["total_vs_ref"]} for r in L[:5]]
    summ["selection"] = {
        "rule": "scale each configuration to the reference's worst week; eligible if scaled max drawdown <= reference's; "
                "highest share of winning weeks; tie: highest scaled total. View: gross, common period 2018-02..2021-12.",
        "eligible_in_gross_common": sum(r["is"]["gross_common"]["scaled"]["eligible"] for r in rows[1:]),
        "strong_ranking_top5": top(select(rows)),
        "soft_rule": "same rule among the configurations that keep >= 2/3 of the reference's total after scaling",
        "soft_ranking_top5": top(select(rows, min_total_share=2 / 3)),
        "same_winner_in_the_other_views": {v: {"strong": select(rows, v)[0]["trial"], "soft": select(rows, v, 2 / 3)[0]["trial"]} for v in VIEWS},
        "scales_of_the_frozen_profiles_per_view": {k: {v: rows[f["trial"] - 1]["is"][v]["scaled"]["scale"] for v in VIEWS}
                                                   for k, f in S.FROZEN.items()},
    }
    # ---- frontier (equal stake and after scaling)
    fr = []
    for r in rows:
        g, n = r["is"]["gross_common"], r["is"]["net_common"]
        fr.append({"trial": r["trial"], "name": r["name"],
                   "gross": {"win_weeks_pct": g["equal_stake"]["win_weeks_pct"], "win_days_pct": g["equal_stake"]["win_days_pct"],
                             "worst_week_x_ref": round(1 / g["scaled"]["scale"], 2), "scaled_total_vs_ref": g["scaled"]["total_vs_ref"],
                             "scaled_dd_vs_ref": g["scaled"]["dd_vs_ref"]},
                   "net": {"win_weeks_pct": n["equal_stake"]["win_weeks_pct"], "win_days_pct": n["equal_stake"]["win_days_pct"],
                           "worst_week_x_ref": round(1 / n["scaled"]["scale"], 2), "scaled_total_vs_ref": n["scaled"]["total_vs_ref"],
                           "scaled_dd_vs_ref": n["scaled"]["dd_vs_ref"]}})
    nd = [f for f in fr if f["gross"]["scaled_dd_vs_ref"] <= 1.0 and not any(
        (o["gross"]["win_weeks_pct"] >= f["gross"]["win_weeks_pct"] and o["gross"]["scaled_total_vs_ref"] >= f["gross"]["scaled_total_vs_ref"]
         and (o["gross"]["win_weeks_pct"] > f["gross"]["win_weeks_pct"] or o["gross"]["scaled_total_vs_ref"] > f["gross"]["scaled_total_vs_ref"])
         and o["gross"]["scaled_dd_vs_ref"] <= 1.0) for o in fr)]
    nd.sort(key=lambda f: f["gross"]["win_weeks_pct"])
    summ["frontier_winning_weeks_vs_profit_kept_after_scaling"] = nd
    for f in nd:                                   # the same frontier when there is no edge at all
        z = S.zero_edge(rows[f["trial"] - 1]["config"], "net", "common", 1000)
        f["zero_edge"] = {"win_weeks_pct": z["win_weeks_pct"]["mean"], "worst_week_median": z["worst_week"]["median"],
                          "win_days_pct": z["win_days_pct"]["mean"]}
    best_days = sorted(rows, key=lambda r: -r["is"]["gross_common"]["equal_stake"]["win_days_pct"])[:3]
    summ["best_share_of_winning_days_by_stake_rules"] = [
        {"trial": r["trial"], "name": r["name"], "gross": r["is"]["gross_common"]["equal_stake"]["win_days_pct"],
         "net": r["is"]["net_common"]["equal_stake"]["win_days_pct"], "eligible": r["is"]["gross_common"]["scaled"]["eligible"],
         "avg_green_day_vs_red_gross": [r["is"]["gross_common"]["equal_stake"]["avg_green_day"], r["is"]["gross_common"]["equal_stake"]["avg_red_day"]],
         "scaled_total_vs_ref_gross": r["is"]["gross_common"]["scaled"]["total_vs_ref"]} for r in best_days]
    # ---- the profiles at their frozen base stake, and their zero-edge controls
    prof = {"reference": {"trial": 1, "config": {}, "base_scale": 1.0}, **S.FROZEN, **S.INFO_ONLY}
    summ["profiles"] = {}
    for name, f in prof.items():
        sc = f["base_scale"]
        d = {"trial": f["trial"], "frozen": name in S.FROZEN, "config": f["config"], "base_stake_pct_when_reference_is_1pct": sc,
             "at_frozen_base_stake": profile_report(f["config"], sc), "zero_edge": {}}
        for period in S.PERIODS:
            for label, kw in (("random_sign_per_trade", {}), ("one_sign_per_family_and_day", {"block": True}),
                              ("shuffle_within_rule", {"shuffle": True})):
                z = S.zero_edge(f["config"], "net", period, 1000, base_pct=(1.0, sc, 2 * sc, 3 * sc), **kw)
                for k in ("worst_week", "worst_day", "total", "max_dd"):      # amounts at the frozen base stake
                    z[k + "_at_frozen_base"] = {q: round(v * sc, 2) for q, v in z[k].items()}
                d["zero_edge"][f"{label}_{period}"] = z
        summ["profiles"][name] = d
        zc = d["zero_edge"]["random_sign_per_trade_common"]
        print(name, "| IS net common:", {k: d["at_frozen_base_stake"]["net_common"][k] for k in
                                         ("win_weeks_pct", "win_days_pct", "win_months_pct", "per_year", "avg_green_day", "avg_red_day",
                                          "worst_day", "worst_week", "max_dd", "longest_red_weeks")},
              "| zero edge:", zc["win_weeks_pct"], zc["worst_week_at_frozen_base"], zc["p_lose_half_pct"])
    summ["crypto_correlation"] = crypto_diagnostics(rows)
    summ["account_realism"] = {
        "loop": "r2/tracks/stake/account.py (variant of goldlab.portfolio.run_account with a stake that follows the week)",
        "price_levels": "is = 2018-2021 prices; today = same trades, stop distances rescaled to fp_costs.json spread_ref_price",
        "runs": account_realism()}
    summ["disclosure"] = ("While listing the lab's files I printed the head of results/r2/round3_summary.json, which contains the "
                          "reference's aggregate 2022-2025 figures (ten rules at equal stake). No stake rule was involved and nothing "
                          "in this track was chosen with it. No 2022+ trade or price was read by the code of this track.")
    json.dump(summ, open(os.path.join(S.OUT, "summary.json"), "w"), indent=1)
    print("selfcheck:", json.dumps(summ["selfcheck"]))
    print("selection:", json.dumps(summ["selection"], indent=1))
    print("frontier:")
    for f in nd:
        print(f"  {f['trial']:2d} {f['name'][:42]:42s} gross wk {f['gross']['win_weeks_pct']:5.1f} keep {f['gross']['scaled_total_vs_ref']:4.2f} wW x{f['gross']['worst_week_x_ref']:4.2f}"
              f" | net wk {f['net']['win_weeks_pct']:5.1f} keep {f['net']['scaled_total_vs_ref']:4.2f} | zero edge wk {f['zero_edge']['win_weeks_pct']:5.1f} wW {f['zero_edge']['worst_week_median']:6.1f}")
    print(json.dumps(summ["best_share_of_winning_days_by_stake_rules"]))
    print(json.dumps(summ["crypto_correlation"], indent=1))
