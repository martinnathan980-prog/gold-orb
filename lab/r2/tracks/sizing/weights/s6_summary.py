"""Lens `weights`: summary.json with every table reported, the verdict on criteria (a)-(f), findings, the ideas that do
not work and the caveats. IN SAMPLE ONLY. Reads only this lens's own result files.
Output: results/r2/sizing/weights/summary.json
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402

import common as C  # noqa: E402


def load(name):
    return json.load(open(os.path.join(C.OUT, name)))


# written after every number below was printed by s0-s5 (files of this directory); in sample only
TEXT = {
    "findings": [
        "Reference (ten sleeves, equal stakes 1 R, plain sum, FP, trades entered 2019-2021, 157 server weeks): weekly Sharpe 2.745 (2019 2.395, 2020 3.714, 2021 2.037), 3,981 trades, +555.8 R, weekly sd 9.30 R, 44.6 % losing weeks, worst week -12.54 R, longest run of losing weeks 7, deepest fall of the weekly cumulative R 21.0 R, 60.7 losing trades per month. Costs x1.5: Sharpe 2.490, +499.7 R (3,983 trades). Without the two F1 sleeves: Sharpe 2.597, +384.1 R (3,166 trades).",
        "Per sleeve, 2019-2021, FP (weekly Sharpe annualised; R per trade; trades): nq_btc_follow 2.11, +0.088, 720; F1 btcusd 1.98, +0.274, 422; brk72 btcusd 1.67, +0.249, 420; F1 ethusd 1.38, +0.143, 393; noise30 1.37, +0.073, 609; brk72 ethusd 1.20, +0.124, 395; donch4h_stop 1.07, +0.191, 158; ocm4 0.83, +0.106, 377; orb_asia gold 0.79, +0.155, 348; GOLD_FRI_PM -0.37, -0.012, 139 (-1.6 R in three years).",
        "The sleeves' results move a lot from year to year: brk72 and F1 on btcusd and ethusd earned +0.09 to +0.56 R per trade in each year 2018-2020 and +0.01 to +0.08 in 2021; nq_btc_follow -0.04 and -0.03 in 2018-2019, then +0.13 in 2020 and 2021; orb_asia gold -0.17 (2018), +0.16 (2019), +0.35 (2020), -0.02 (2021); GOLD_FRI_PM +0.07 to +0.09 in 2013-2016, -0.04 to +0.02 in 2017-2021 (FP).",
        "The weekly swing of a sleeve differs fifteen-fold at the same 1 R stake: weekly sd 2019-2021 from 0.20 R (GOLD_FRI_PM, sd 0.22 R per trade: its trades rarely travel to the stop) to 3.15 R (orb_asia gold, sd 2.15 R per trade).",
        "Correlations of weekly R (FP, 157 weeks 2019-2021): mean over the 45 pairs 0.109; donch4h~orb gold 0.61, brk72 eth~F1 eth 0.55, F1 btc~F1 eth 0.44, brk72 btc~F1 btc 0.40, brk72 btc~brk72 eth 0.39; nq_btc_follow -0.10 to -0.02 with the crypto breakouts; covariances make 50 % of the portfolio's weekly variance. The four crypto breakout sleeves' mean pairwise correlation: 0.63 (2018 from February), 0.52, 0.45, 0.15 (2019-2021).",
        "A sleeve's past does not tell its next year: across the ten sleeves, the rank correlation between the expanding past weekly Sharpe (weeks closed before 25 December) and the next year's weekly Sharpe is +0.56 (2019), +0.10 (2020), -0.21 (2021); between past mean / variance of weekly R and the next year's weekly Sharpe +0.08, -0.22, -0.48 (FP).",
        "Ceiling of the lens (hindsight, description only): the best static stakes in [0, 2] (F1 <= 1) chosen WITH the 2019-2021 weeks themselves raise the pooled weekly Sharpe from 2.747 to 3.423 (+24.6 %; without F1 +25.4 %); chosen year by year with hindsight +19 %, +35 %, +124 %. They put 0 on orb_asia gold and GOLD_FRI_PM and the most on nq_btc_follow and donch4h_stop. No weighting fitted on earlier years can beat that ceiling on these weeks, so one stake per sleeve cannot bring the four- to five-fold rise in gain per unit of swing that doubling a small account in a month with falls under 20 % needs (about 0.35 R per trade instead of 0.08, results/r2/stake/x2/x2.json).",
        "PART 2 verdict (15 declared variants, all causal by both truncation tests): no candidate. Best: IV00 +5.9 % pooled (2019 -14 %, 2020 +7 %, 2021 +30 %), +4.5 % with costs x1.5, +7.0 % without F1. All 4 MV, 3 Z and 4 D variants lower the weekly Sharpe at equal swing (ratios 0.919 to 0.990, FP)."],
    "ideas_that_do_not_work": [
        {"idea": "MV00-MV75: stake proportional to the walk-forward mean / variance of each sleeve's weekly R (expanding window, refitted every 1 January on weeks closed before 25 December), shrunk toward equal stakes by 0, 0.25, 0.5, 0.75, clipped to [0.25, 2], F1 <= 1",
         "numbers": "Pooled 2019-2021 weekly Sharpe at equal swing, FP: x0.938 / 0.953 / 0.969 / 0.985 (2.745 -> 2.575 / 2.616 / 2.660 / 2.705); down in 2019 and 2020 at every shrinkage (0.93-0.99); costs x1.5 x0.916-0.978, 0 of 3 years up; without F1 x0.964-0.991. Total R at equal swing +521.4 / +529.6 / +538.6 / +547.7 against +555.8. Why: GOLD_FRI_PM's weekly R barely moves (sd 0.25 R in fold 2019), so its mean / variance is 4.5 times the average of the ten (0.788 vs 0.176) and it sits at the cap 2 in every fold while it lost; after its 2018 loss (-9.5 R) nq_btc_follow gets the floor 0.25 (MV00) to 0.43-0.57 (MV50) in 2019-2020, just before +31.2 R (2020) and +38.3 R (2021); the crypto breakouts are favoured going into 2021, when they fell to +0.01-0.08 R per trade."},
        {"idea": "IV00-IV75: inverse volatility, stake proportional to 1 / sd of each sleeve's weekly R (same walk-forward), shrunk by 0, 0.25, 0.5, 0.75, clipped [0.25, 2], F1 <= 1",
         "numbers": "Pooled ratio FP x1.059 / 1.039 / 1.022 / 1.007; by year IV00 0.859 / 1.074 / 1.297 (2019 down at every shrinkage, 0.86-0.97); costs x1.5 x1.045 / 1.030 / 1.016 / 1.004; without F1 x1.070 / 1.045 / 1.024 / 1.008. Fails (a) at every shrinkage (+10 % needed), hence (c). Block bootstrap of the pooled ratio for IV00: 5-95 % range 0.99-1.14, P(ratio >= 1.10) 0.18, and it is the best of 15 tries. At equal swing IV00 needs k = 1.99, effective stakes 0.66 to 3.99 times the base (GOLD_FRI_PM). For the user, IV00 vs reference at equal weekly swing (FP, 2019-2021): losing trades per month 60.7 -> 60.7, losing weeks 44.6 % -> 45.9 %, worst week -12.54 -> -12.43 R, longest losing run 7 -> 7 weeks, deepest fall 21.0 -> 22.1 R, total +555.8 -> +588.8 R. The gain is mostly nq_btc_follow (mean contribution 0.40 -> 0.78 R per week) and donch4h_stop (0.19 -> 0.38) getting more weight, orb_asia gold (0.34 -> 0.23), F1 btcusd (0.74 -> 0.50) and brk72 btcusd (0.67 -> 0.57) less. Information only: 2018 (from February) 3.24 -> 3.62; gold + us100 sub-portfolio 2015-2018 x1.04-1.20 but 2019-2021 x0.98-1.00."},
        {"idea": "Z12 / Z24 / Z36: a sleeve set to 0 (followed on paper) while the mean R of its trades closed in the trailing 12 / 24 / 36 months is not positive (at least 20 trades)",
         "numbers": "Pooled ratio FP x0.964 / 0.959 / 0.990, years up 0 / 0 / 1; costs x1.5 x0.957 / 0.997 / 0.972; without F1 x0.969 / 0.932 / 0.987. Z24 switched off 459 trades of 2019-2021 that made +56.4 R: orb_asia gold 123 trades +40.5 R (2019-2020), nq_btc_follow 268 trades +14.7 R (2019-2020), GOLD_FRI_PM 68 trades +1.1 R. It cuts losing trades per month from 60.7 to 54.1 and losing weeks from 44.6 % to 42.0 % but the worst week grows to -13.38 R and the total at equal swing falls to +533.1 R. The switch turns sleeves off just before they recover."},
        {"idea": "D4 / D5 / D6 / D7 (cluster lens weights redone at equal weekly swing on the plain sum): stake 0.5 + rank / (n - 1) by the trailing 91 / 182 / 365-day or expanding paper mean R per trade, F1 <= 1",
         "numbers": "Pooled ratio FP x0.972 / 0.981 / 0.934 / 0.919, years up 1 / 1 / 0 / 0; 2021 x1.019 / 1.073 / 0.820 / 0.724 (the longer the memory, the more stake on the 2018-2020 crypto winners); costs x1.5 x0.969 / 0.998 / 0.943 / 0.924; without F1 x0.940 / 0.950 / 0.906 / 0.902. The cluster lens's +4 to +13 % were expectancy per stake on the capped account: these weights load the crypto breakouts, whose high expectancy comes with high, correlated weekly swings, so per unit of swing they lose. D5 shortens the longest losing run (7 -> 5 weeks) and the deepest fall (21.0 -> 18.3 R) but earns +545.5 R against +555.8."}],
    "caveats": [
        "In sample only: entries and exits before 2022-01-01, frames cut while read; nothing 2022+ read, simulated or looked at. The ten rules were chosen on data that include 2019-2021, so these out-of-fold years are out of fold for the weights only: every figure is optimistic. The validation look, then the demo account, is the measure that counts.",
        "Three out-of-fold years (157 weeks) judge; 15 variants were tried, so the best ratio is biased upward (IV00's 5-95 % bootstrap range 0.99-1.14 includes no gain).",
        "The MV normalisation (divide by the mean of the ten ratios) was fixed in the declaration before any description statistic; it is carried by GOLD_FRI_PM. A median or capped normalisation was not tried: choosing it after seeing 2019-2021 would be post hoc, and the hindsight ceiling (+24.6 %) bounds every static weighting anyway.",
        "Equal weekly swing scales all stakes by k (IV00 k = 1.99): raw stakes respect [0, 2] (F1 <= 1) but the effective stakes reach 4 times the base on GOLD_FRI_PM; on a small account stakes below the broker's minimum lot are skipped (Addendum E).",
        "Account: plain sum of the ten one-position chains (synthesis_B's P0), no 6-position / 2-per-market caps, no compounding; the cluster lens's D4-D7 figures were on the capped account and by expectancy per stake, hence differ.",
        "Z and D are state rules evaluated at each decision on trades closed strictly before it (no fitted parameter, no yearly refit), as the cluster lens defined D4-D7; MV and IV are refitted every 1 January on weeks closed before 25 December (7-day purge).",
        "The F1 sleeves' in-sample results are inflated (scorecard fitted on these years): U8 without them is reported and gives the same verdict.",
        "Costs x1.5: the whole procedure (chains rebuilt on the widened quotes, weights refitted on them, its own reference and scale). The FP frames' spread uses a day-median shape that is not causal; it affects fills, not stakes.",
        "Per-year Sharpe uses the server weeks whose Thursday is in the year and the trades entered 2019-2021; the PART 1 reference table also counts trades entered in late 2018 that close in the first 2019 week (2019: 2.400 instead of 2.395).",
        "Exposure note: while skimming lab/results/live/brain_maps_2026-11-11.json (as the task asked), a printed preview showed a few 2022-2025 aggregate lines (per-sleeve trades per year, win rate, holding time and exit-reason shares, and a summary of an earlier validation look). No number from them was used; the variant grid is the task's own (MV shrinkage 0.25 / 0.5 / 0.75, inverse volatility, 24-month switch, D4-D7) plus its natural neighbours (shrinkage 0, 12- and 36-month windows), declared before any 2019-2021 statistic was computed."]}


def user_measures(ev, ref):
    """for the user, at equal weekly swing, pooled 2019-2021"""
    p, r = ev["pooled"], ev["pooled"]["ref"]
    v = p["var_equal_swing"]
    return {"losing_trades_per_month": {"before": ev["trades"]["losing_trades_per_month_ref"], "after": ev["trades"]["losing_trades_per_month_var"]},
            "losing_weeks_pct": {"before": r["losing_weeks_pct"], "after": v["losing_weeks_pct"]},
            "worst_week_R": {"before": r["worst_week"], "after": v["worst_week"]},
            "longest_losing_run_weeks": {"before": r["longest_losing_run"], "after": v["longest_losing_run"]},
            "max_drawdown_weekly_R": {"before": r["max_dd"], "after": v["max_dd"]},
            "total_R": {"before": r["total"], "after": v["total"]},
            "weekly_sd_R": {"before": r["sd"], "after": v["sd"]}}


def main():
    decl = load("declared.json")
    repro = load("repro.json")
    p1 = load("part1.json")
    p2 = load("part2_raw.json")
    diag = load("diagnostics.json")
    t1 = load("truncation_T1.json")
    t2 = load("truncation_T2.json")
    trials = [json.loads(x) for x in open(C.TRIALS)]
    n_var = sum(1 for t in trials if t.get("kind") == "variant")

    # ---------------------------------------------------------------- verdicts
    verdict, table = {}, []
    for v in decl["variants"]:
        rec = p2["variants"][v["id"]]
        cp = rec["criteria_partial"]
        e = bool(t1["variants"][v["id"]]["U10"]["pass"] and t1["variants"][v["id"]]["U8_noF1"]["pass"] and t2["pass"])
        out = {}
        for u in ("U10", "U8_noF1"):
            c = dict(cp[u])
            c["e_causal_truncation"] = e
            c["candidate"] = bool(c["a_sharpe_up_10pct"] and c["b_up_2_of_3_years"] and c["c_holds_costs_x1.5"]
                                  and c["d_neighbours_improve"] and e and c["f_stakes_and_parameters"])
            out[u] = c
        out["candidate"] = out["U10"]["candidate"]
        out["flag_rests_on_F1"] = bool(out["U10"]["candidate"] and not out["U8_noF1"]["candidate"])
        verdict[v["id"]] = out
        fp, ss, f8, s8 = rec["U10|fp"], rec["U10|stress"], rec["U8_noF1|fp"], rec["U8_noF1|stress"]
        table.append({
            "id": v["id"], "family": v["family"], "lambda": v.get("lambda"), "window_days": v.get("window_days"),
            "U10_fp": {"sharpe_ref": fp["pooled"]["ref"]["sharpe"], "sharpe_var": round(fp["pooled"]["ref"]["sharpe"] * fp["pooled"]["sharpe_ratio"], 3),
                       "ratio": fp["pooled"]["sharpe_ratio"], "ratio_by_year": {y: fp["by_year"][str(y)]["sharpe_ratio"] for y in C.OOF},
                       "years_up": fp["years_up"], "k_equal_swing": fp["k_equal_swing"],
                       "total_R_ref": fp["pooled"]["ref"]["total"], "total_R_var_equal_swing": fp["pooled"]["var_equal_swing"]["total"],
                       "total_R_by_year_ref": {y: fp["by_year"][str(y)]["ref"]["total"] for y in C.OOF},
                       "total_R_by_year_var": {y: fp["by_year"][str(y)]["var_equal_swing"]["total"] for y in C.OOF},
                       "bootstrap": fp["bootstrap"], "stakes": {x: fp["stakes"][x] for x in ("raw_min", "raw_max", "raw_mean", "scaled_min", "scaled_max", "share_zero")},
                       "early_2018_info": fp.get("early_2018_info")},
            "U10_stress": {"ratio": ss["pooled"]["sharpe_ratio"], "ratio_by_year": {y: ss["by_year"][str(y)]["sharpe_ratio"] for y in C.OOF},
                           "years_up": ss["years_up"], "sharpe_ref": ss["pooled"]["ref"]["sharpe"], "k_equal_swing": ss["k_equal_swing"],
                           "total_R_ref": ss["pooled"]["ref"]["total"], "total_R_var_equal_swing": ss["pooled"]["var_equal_swing"]["total"]},
            "U8_noF1_fp": {"ratio": f8["pooled"]["sharpe_ratio"], "ratio_by_year": {y: f8["by_year"][str(y)]["sharpe_ratio"] for y in C.OOF},
                           "years_up": f8["years_up"], "sharpe_ref": f8["pooled"]["ref"]["sharpe"]},
            "U8_noF1_stress": {"ratio": s8["pooled"]["sharpe_ratio"], "years_up": s8["years_up"]},
            "U5_gold_us100_info": rec["U5_gold_us100|fp"],
            "for_the_user_U10_fp_equal_swing": user_measures(fp, None),
            "criteria": verdict[v["id"]]})
    candidates = [v for v, x in verdict.items() if x["candidate"]]

    # ---------------------------------------------------------------- part 1 tables
    by_year = pd.read_csv(os.path.join(C.OUT, "part1_by_year.csv"))
    part1 = {"by_sleeve_year_table": by_year.to_dict(orient="records")}
    for mode in C.MODES:
        part1[mode] = {k: p1[mode][k] for k in ("by_sleeve", "corr", "corr_by_year", "persistence", "reference_portfolio", "hindsight_bound")}

    ref = p2["reference"]
    best = max(table, key=lambda r: r["U10_fp"]["ratio"])
    summ = {
        "lens": "weights (PROTOCOL_V3 Addendum I): one stake per sleeve",
        "data": "in sample only: price frames read with the row filter ts < 2022-01-01; official trades read with entry_time < 2022-01-01 (and exit_time < 2022-01-01 for every R read); nothing dated 2022 or later read, simulated or looked at",
        "account": decl["account"],
        "units": "R = multiples of the base stake (the money risked on one trade at stake 1); no compounding",
        "clock": decl["clock"],
        "baseline_reproduced": {
            "all_ten": repro["all_ten_reproduced"],
            "per_sleeve": {k: {"official_entered_before_2022": repro[k]["n_official_entered_before_2022"],
                               "official_closed_in_2022_not_read": repro[k]["n_official_entered_before_2022_closed_in_2022"],
                               "official_closed_before_2022": repro[k]["n_official_closed_before_2022"],
                               "official_total_R_closed_before_2022": repro[k]["totR_official_closed_before_2022"],
                               "mine_matched": repro[k]["matched_on_entry_and_side"],
                               "mine_total_R_matched": repro[k]["totR_mine_on_matched"],
                               "matched_rows_differing": repro[k]["matched_rows_differing"],
                               "refused_3_spreads_fp_stress": [repro[k]["chains"]["fp"]["refused_3spreads"], repro[k]["chains"]["stress"]["refused_3spreads"]]}
                           for k in C.KEYS},
            "P0_fp_2018_02_2021_12": {"n": repro["P0_fp"]["n"], "total_R": repro["P0_fp"]["total_R"], "matches_synthesis_B": repro["P0_matches_synthesis_B"]},
            "P0_stress_2018_02_2021_12": {"n": repro["P0_stress"]["n"], "total_R": repro["P0_stress"]["total_R"]}},
        "declared": {"file": C.DECLARED, "declared_at": decl["declared_at"], "budget": decl["budget"]},
        "trials": {"variants_logged": n_var, "budget": decl["budget"]["allowed"], "file": C.TRIALS,
                   "other_lines": [t.get("kind") for t in trials if t.get("kind") != "variant"]},
        "reference_2019_2021": ref,
        "part1": part1,
        "part2_table": table,
        "candidates": candidates,
        "best_variant_by_pooled_ratio": {"id": best["id"], "U10_fp_ratio": best["U10_fp"]["ratio"]},
        "diagnostics": diag,
        "truncation": {"T1_trade_level": {"all_pass": t1["all_variants_pass"], "control_caught": t1["control_caught"],
                                          "per_variant": t1["variants"], "leaky_control": t1["leaky_control"]},
                       "T2_price_frames": t2},
    }
    summ["verdict"] = ("No candidate. None of the 15 declared variants raises the pooled 2019-2021 weekly Sharpe of the ten "
                       "sleeves by 10 % at equal weekly swing (FP); the best, IV00 (inverse volatility, no shrinkage), gives "
                       "+5.9 % (2.745 -> 2.908), down in 2019 (-14 %), +4.5 % with costs x1.5, +7.0 % without the F1 sleeves. "
                       "Every MV, Z and D variant lowers it.")
    summ["findings"] = TEXT["findings"]
    summ["ideas_that_do_not_work"] = TEXT["ideas_that_do_not_work"]
    summ["caveats"] = TEXT["caveats"]
    C.jdump(summ, os.path.join(C.OUT, "summary.json"))
    print("candidates:", candidates, "| best", best["id"], best["U10_fp"]["ratio"], "| T1", t1["all_variants_pass"], "T2", t2["pass"],
          "| variants logged", n_var)


if __name__ == "__main__":
    main()
