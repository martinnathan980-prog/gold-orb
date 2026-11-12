"""Step 3: lab/results/r2/sizing/synthesis.json from the outputs of steps 0-2 (numbers read from out/, nothing
re-estimated by hand). IN SAMPLE ONLY.

    NUMBA_CACHE_DIR=/tmp/synthI_numba PYTHONDONTWRITEBYTECODE=1 python3 s3_summary.py
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import sy_common as C  # noqa: E402
import s1_variants as V  # noqa: E402

S0 = json.load(open(os.path.join(C.OUT, "s0_repro.json")))
S1 = json.load(open(os.path.join(C.OUT, "s1_variants.json")))
S2 = json.load(open(os.path.join(C.OUT, "s2_truncation.json")))
DECL = json.load(open(os.path.join(C.HERE, "declared.json")))
TRIALS = [json.loads(x) for x in open(C.TRIALS)]
KEYS_M = ["trades", "R_per_trade", "eur_per_100_risked", "sharpe", "total_R", "losing_weeks_pct", "worst_week",
          "longest_losing_weeks", "losing_trades_per_month", "max_fall_weekly_R"]


def table(vid, mode, against="vs_S00"):
    r = S1["variants"][vid][mode][against]
    out = {"scale_k": r["scale_k"], "years_up": r["years_up"],
           "pooled_2019_2021": {k: r["pooled"][k] for k in KEYS_M}}
    out["pooled_2019_2021"]["sharpe_ratio_vs_ref"] = r["pooled"]["sharpe_ratio_vs_ref"]
    out["by_year"] = {}
    for y, v in r["by_year"].items():
        d = {k: v["variant"][k] for k in KEYS_M}
        d["sharpe_ratio_vs_ref"] = v["variant"]["sharpe_ratio_vs_ref"]
        out["by_year"][y] = d
    return out


def ref_table(mode):
    r = S1["variants"]["S00_R0"][mode]["vs_S00"]
    out = {"pooled_2019_2021": {k: r["pooled_ref"][k] for k in KEYS_M}, "by_year": {}}
    for y, v in r["by_year"].items():
        out["by_year"][y] = {k: v["ref"][k] for k in KEYS_M}
    return out


def p0_window():
    """synthesis_B's P0 check: the ten chains, entries 2018-02-01..2021-12-31, FP and x1.5"""
    out = {}
    for mode in C.MODES:
        n, tot = 0, 0.0
        for k in C.KEYS:
            t = C.load_trades(f"ref__{k}__{mode}")
            w = t[t.entry_time >= pd.Timestamp("2018-02-01", tz="UTC")]
            n += len(w)
            tot += float(w.R.sum())
        out[mode] = {"trades": n, "total_R": round(tot, 2)}
    return out


def k1_fit_2022():
    out = {}
    for mode in C.MODES:
        s = pd.read_parquet(os.path.join(C.OUT, f"k1sig__brk72_24h_wd__ethusd__{mode}.parquet"),
                            filters=[("t_dec", "<", C.IS_END_NS)])
        use = (s.filled & ~s.refused & ~s.boundary & np.isfinite(s.label)).to_numpy()
        tr = use & (s.t_dec.to_numpy(np.int64) < C.train_cut_ns(2022))
        f = V.k1_fit(s.riskbp.to_numpy()[tr], s.label.to_numpy()[tr])
        out[mode] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()}
    return out


def fmt_ratio(vid, mode, against="vs_S00"):
    r = S1["variants"][vid][mode][against]
    by = r["by_year"]
    return (f"x{r['pooled']['sharpe_ratio_vs_ref']:.3f} (2019 x{by['2019']['variant']['sharpe_ratio_vs_ref']:.3f}, "
            f"2020 x{by['2020']['variant']['sharpe_ratio_vs_ref']:.3f}, 2021 x{by['2021']['variant']['sharpe_ratio_vs_ref']:.3f})")


def main():
    p0 = p0_window()
    k22 = k1_fit_2022()
    R0f, R0s = ref_table("fp"), ref_table("stress")
    rf, rs = R0f["pooled_2019_2021"], R0s["pooled_2019_2021"]
    v5 = S1["variants"]["S01_V05"]["fp"]["vs_S00"]
    v5s = S1["variants"]["S01_V05"]["stress"]["vs_S00"]
    k1 = S1["variants"]["S03_K1"]["fp"]["vs_S00"]
    kv = S1["variants"]["S04_K1_V05"]["fp"]["vs_S03_K1"]
    kvs = S1["variants"]["S04_K1_V05"]["stress"]["vs_S03_K1"]
    p2 = S1["variants"]["S05_P2"]["fp"]["vs_S00"]
    p2s = S1["variants"]["S05_P2"]["stress"]["vs_S00"]
    t1 = S2["T1"]
    t2 = S2["T2"]

    rule2 = {k: {"official_trades_closed_before_2022": v["n_official_closed_before_2022"],
                 "matched_identical": v["matched"], "rows_differing": v["rows_differing"],
                 "total_R_official_closed": v["totR_official_closed"], "total_R_mine_matched": v["totR_mine_matched"],
                 "official_rows_entered_before_2022_exit_not_before_2022_not_read":
                     v["official_rows_entered_before_2022_with_exit_not_before_2022"],
                 "my_trades_open_at_slice_end": v["only_mine"], "reproduced": v["reproduced"]}
             for k, v in S0["rule2"].items()}

    growth = {
        "kept_set": "Addendum I keeps nothing: the weekly Sharpe at equal swing is unchanged (x1.00), so is the growth.",
        "rule": ("At equal weekly swing the mean weekly gain moves in proportion to the weekly Sharpe. A compounding "
                 "account staked at a fixed fraction of its optimal (Kelly) stake grows at a rate proportional to the "
                 "square of the Sharpe. At a fixed fall over a long horizon (expected deepest fall about stake x "
                 "variance / mean), the stake can rise about in proportion to the Sharpe and the gain about with its "
                 "square; over a short horizon such as one month the falls come from the swing, so the stake cannot "
                 "rise and the gain rises only in proportion to the Sharpe. In these samples the deepest fall at equal "
                 "swing is noisy: K1+K2+K3 has a higher Sharpe and a deeper fall (24.1 R against 21.0 R)."),
        "information_only_in_sample": {
            "V05 (dropped)": {"sharpe_ratio": v5["pooled"]["sharpe_ratio_vs_ref"],
                              "growth_ratio_at_fixed_fraction_of_optimal": round(v5["pooled"]["sharpe_ratio_vs_ref"] ** 2, 3)},
            "V05 on top of K1 (dropped)": {"sharpe_ratio": kv["pooled"]["sharpe_ratio_vs_ref"],
                                           "growth_ratio_at_fixed_fraction_of_optimal": round(kv["pooled"]["sharpe_ratio_vs_ref"] ** 2, 3)},
            "K1 (Addendum H)": {"sharpe_ratio": k1["pooled"]["sharpe_ratio_vs_ref"],
                                "growth_ratio_at_fixed_fraction_of_optimal": round(k1["pooled"]["sharpe_ratio_vs_ref"] ** 2, 3)},
            "K1+K2+K3 (Addendum H, the look's content)": {"sharpe_ratio": p2["pooled"]["sharpe_ratio_vs_ref"],
                                                          "growth_ratio_at_fixed_fraction_of_optimal": round(p2["pooled"]["sharpe_ratio_vs_ref"] ** 2, 3)}},
        "demand": {"R_per_trade_needed_at_todays_noise": 0.35, "R_per_trade_2022_2025_task_figure": 0.08,
                   "sharpe_multiple_needed": round(0.35 / 0.08, 2), "growth_multiple_needed": round((0.35 / 0.08) ** 2, 1),
                   "remaining_after_this_addendum": round(0.35 / 0.08, 2)},
    }

    look = (
        "DECLARATION for the single look at 2022-2025 (PROTOCOL_V3 Addendum I, lead synthesis; written 2026-11-12 "
        "before any 2022+ row is read by this synthesis, which reads none). "
        "1. ADDENDUM I ADDS NO CHANGE. No conviction, clock or weight rule survived the criteria fixed in Addendum I "
        "and the attack, so none enters the look. FROZEN for Addendum I: every trade of every sleeve keeps a stake of "
        "1 base stake (1 R); nothing is fitted, so nothing is refitted on 1 January 2022, 2023, 2024 or 2025. V05 (the "
        "pooled crypto ridge, x1.095 in sample, below the x1.10 bar), IV00 and every other variant of the three lenses "
        "are excluded and may not be added to the look, before or after any 2022+ result. "
        "2. THE ONE LOOK covers exactly the kept changes of Addendum H, each as declared by its synthesis, at most one "
        "change per sleeve: K1, K2 and K3 as declared in results/r2/autopsy/synthesis_B.json (K1: brk72_24h_wd ethusd "
        f"skips a signal when 10,000 x stop_dist / P >= T(Y); T(2022) = {k22['fp']['q_hi']:.2f} bp, the 2/3 quantile of "
        f"the riskbp of the {k22['fp']['n_train']} in-sample signals decided before 2021-12-25, each taken alone with FP "
        f"costs, whose upper third averaged {k22['fp']['E_hi']:+.3f} R against {k22['fp']['E_lo']:+.3f} R for the lower "
        "third; refitted each 1 January Y on the signals decided before 1 January Y minus 7 days, the worse third skipped "
        "only if it lost; with costs x1.5 the same procedure on the x1.5 labels "
        f"(T(2022) = {k22['stress']['q_hi']:.2f} bp); K2 and K3: orb_asia_2d_buf10 unchanged on ethusd and btcusd), "
        "with synthesis_B's comparisons and criteria unchanged; plus the changes that synthesis_A keeps, if its "
        "declaration is complete before the look is run. "
        "3. READING ADDED BY ADDENDUM I, NOT A CRITERION (so that the gain per unit of swing is on file): on the plain "
        "sum of the one-position chains (3-spread refusal; trades open at 2025-12-31 23:59 dropped), FP server weeks "
        "booked at the exit, every week of 2022-2025 counted, the weekly Sharpe of (i) the ten unchanged and (ii) the "
        "portfolio with every kept change of Addendum H (new sleeves included), (ii) scaled so that its weekly standard "
        "deviation over 2022-2025 equals "
        "(i)'s; pooled and for each year 2022, 2023, 2024, 2025; FP costs and costs x1.5 (frames and orders rebuilt); "
        "with trades, R per trade, euros earned per 100 euros risked, total R, share of losing weeks, worst week, longest "
        "run of losing weeks and losing trades per month. "
        "4. EXPECTATIONS declared now, not targets: for Addendum I, none (no change). On this measure the in-sample H set "
        f"(K1+K2+K3 against the ten, 2019-2021, FP) gave {fmt_ratio('S05_P2', 'fp')}, mostly 2019; the verifiers' forward "
        "estimates are +0.03 to +0.06 R per trade for K1 (possibly zero), +0.15 to +0.25 for K2, +0.10 to +0.16 for K3 "
        "(zero plausible). "
        "5. CRITERIA: Addendum I has none, since nothing of it is in the look; each change of Addendum H is judged by the "
        "criteria of its own declaration. The 2026 holdout stays untouched. A failure is final: nothing is re-tuned, "
        "re-declared or looked at again.")

    summary_fr = "\n".join([
        "Réponse : non. Miser plus sur les trades « qui ont des chances » n'apporte pas assez ; rien n'est retenu.",
        "Testé sur 2019-2021 seulement, à risque hebdomadaire égal : mise selon le contexte, l'heure, le jour, ou par règle.",
        "Heure et jour : rien (de -7 % à 0 % de gain à risque égal). Mise par règle : +6 % au mieux, 2019 en baisse.",
        "Meilleure idée : 1,5 mise sur les cassures crypto bien notées, 0,5 ou 0 ailleurs : +9,5 % ; il fallait +10 %.",
        "Ce gain vient presque tout de 2021 (+34 %) ; 2019 : +0,6 % ; 2018 va dans l'autre sens (-6 %).",
        "Avec le filtre éther déjà retenu, elle n'ajoute que +6 %, et 2019 baisse.",
        "Sur 1 000 € aux prix actuels, les petites mises passent sous le lot minimum : -5 %.",
        "Le portefeuille reste celui d'avant : 2019-2021, 14 € gagnés pour 100 € risqués, 45 % de semaines perdantes, pire semaine -13 mises.",
        "Doubler en un mois avec des chutes sous 20 % demande 35 € pour 100 € risqués au lieu de 8 (2022-2025), soit 4,4 fois plus : on reste à 1.",
        "Seul levier qui bouge un peu : ajouter des règles, comme deux règles « Asie » sur crypto (essai précédent) : +12 %, surtout 2019, pire chute plus profonde.",
        "Tout vient des années qui ont servi à bâtir les règles : c'est optimiste.",
        "Suite : le seul test 2022-2025 déjà prévu, sans mise variable.",
    ])

    global IDEAS, CAVEATS, FILES
    p2p, p2y = p2["pooled"], p2["by_year"]
    IDEAS = [
        ("Stakes or skips by hour band or weekday (clock lens, 9 declared rules): x0.933 to x1.000 pooled weekly Sharpe at "
         "equal swing, 2019-2021, FP (x0.952 to x0.998 with costs x1.5), up in at most 1 of 3 years. Even stakes set with "
         "perfect hindsight of each year (x1.18 hour bands, x1.38 weekdays) stay below the median of the same bound on "
         "randomly shuffled labels (x1.22, x1.41): the clock carries no more structure than noise."),
        ("One stake per sleeve (weights lens, 15 variants): walk-forward mean/variance x0.938 to x0.985; inverse "
         "volatility x1.007 to x1.059 with 2019 down at every shrinkage (IV00: 2019 x0.859, 2020 x1.074, 2021 x1.297); "
         "switching a sleeve off while its trailing 12/24/36-month expectancy is not positive x0.959 to x0.990 (the "
         "24-month switch turned off 459 trades that made +56.4 R); rank weights D4-D7 x0.919 to x0.981. Even the best "
         "static weights chosen with hindsight of 2019-2021 give only +24.6 %."),
        ("Per-sleeve terciles of one descriptor with 0 / 0.5 / 1.5 stakes (conviction V01-V04, V23-V28): x0.942 to x1.047 "
         "FP; on the six non-crypto sleeves every per-sleeve rule lowered the R (230.5 R to 149-218 R, 2019-2021); the "
         "chosen descriptor drifts from year to year; V04's permutation null reaches it in 29.5 % of draws."),
        ("Bigger stakes when another sleeve holds the same side of the same market (V11-V15): x0.952 to x0.997 FP; its "
         "null reaches V11 in 59.5 % of draws. The +0.24 R vs +0.14 R seen by the cluster lens does not hold out of fold."),
        ("Combining the pooled ridge with per-sleeve rules (V16-V20): x1.018 to x1.061, worse than the ridge alone; a "
         "per-sleeve ridge for all ten (V10, 8 fitted parameters per sleeve): x1.007."),
        ("Cutting the trades 'with no chance' (V05's zero rule alone, verifier): x1.042; the 213 baseline crypto trades it "
         "removed made +5.5 R in total (+0.026 R each, my run: brk72 btc 30 trades +1.8 R, F1 eth 48 trades +13.2 R, "
         "brk72 eth 135 trades -9.5 R). What gains is the 1.5 stake on high scores, mostly in 2020-2021."),
        ("The best idea, the pooled crypto ridge V05: my re-simulation " + fmt_ratio("S01_V05", "fp") + " FP, "
         + fmt_ratio("S01_V05", "stress") + " with costs x1.5; strict training cut " + fmt_ratio("S02_V05_strict", "fp")
         + "; on top of K1 " + fmt_ratio("S04_K1_V05", "fp", "vs_S03_K1") + "; earlier 2018 fold x0.944 (verifier); on a "
         "1,000 EUR account at today's prices as the live program would run it x0.954 at 1 % risk, x0.993 at 2 % "
         "(verifier). Not kept."),
    ]
    CAVEATS = [
        ("In sample only, on the years that built the ten rules (F1's scorecard was fitted on candidates up to "
         "2021-12-27): every figure here, walk-forward included, is optimistic. The measure that counts is the "
         "validation look, then the demo account."),
        ("The kept set (none) was declared before any run of this synthesis (declared.json, 15:03 UTC). My runs reproduce "
         "the lens and verifier figures to the fourth decimal (V05 x1.0951, strict x1.1002, on K1 x1.0558, K1 x1.0359, "
         "reference 3,985 trades +556.16 R Sharpe 2.7466) and do not change it."),
        ("Account: plain sum of the one-position chains, 1 R x stake, no 6-position / 2-per-market caps, no compounding, "
         "no minimum lot. On the user's 1,000 EUR account many 0.5 stakes and BTC stakes fall under 0.01 lot (Addendum E); "
         "the verifier's live-like run of V05 there gives x0.954 at 1 % risk."),
        ("The H set measured here (K1+K2+K3, " + fmt_ratio("S05_P2", "fp") + f" FP, k {p2['scale_k']}) covers synthesis_B's "
         "changes only. Its gain sits in 2019; at equal swing its deepest weekly fall is "
         f"{p2p['max_fall_weekly_R']} R against {rf['max_fall_weekly_R']} R and its worst week {p2p['worst_week']} R "
         f"against {rf['worst_week']} R; K2 and K3 were chosen by the breadth lens on 2013-2021, so 2019-2021 is not out of "
         "sample for their selection; their edge per trade halved from 2018-2019 to 2020-2021; ethusd would carry three "
         "sleeves for two slots. synthesis_A (declared 15:12 UTC, in progress) may add other H changes to the look "
         "(ocm4 T1, F1 ethusd H2, brk72 btcusd S0.75r, donch4h_stop S0.75r, orb_asia_2d_buf10 S0.75r); they are not in "
         "these figures."),
        ("Rule 3's 7-day purge: in their 2019 fits V05 as declared uses two outcomes known exactly at the purge instant and "
         "K1 one outcome known a few hours after it (truncation test T1b); both fits are identical on frames cut at "
         "1 January of the year they are used in (T1a), so neither sees the year it is applied to."),
        ("The FP frames' spread uses a day-median shape that is not causal; it affects fills and labels, not the "
         "descriptors of the stakes (riskbp replaces sprR)."),
        ("The two gold trades entered on 2021-12-31 whose official exit is in 2022 were counted but not read, and are "
         "excluded everywhere. Weeks are FP server weeks booked at the exit and belong to the year of their Thursday; "
         "the 3,985 reference trades include a few entered in late December 2018 (the clock and weights lenses count "
         "3,981 by entry)."),
        ("Selection: the three lenses tried 30 + 15 + 15 variants and the verifier 77 lines; this synthesis ran 6 "
         "re-measurements x 2 cost modes (12 trial lines) and chose no parameter."),
        ("Repository: only lab/r2/tracks/sizing/synthesis/ and lab/results/r2/sizing/synthesis.json were written; no git "
         "command that changes anything; the last line of results/val_access.log (13:50:26 UTC, track stake) predates "
         "this synthesis, whose code never calls a validation cut. synthesis_A's declaration (in sample, no result) was "
         "read; nothing in validation_hi was opened. The brain maps were read with every sentence mentioning 2022-2026 "
         "or validation masked."),
    ]
    FILES = [os.path.join(C.HERE, f) for f in ("declared.json", "trials.jsonl", "sy_common.py", "s0_repro.py",
                                                "s1_variants.py", "s2_truncation.py", "s3_summary.py")] + \
        [os.path.join(C.OUT, f) for f in ("s0_repro.json", "s1_variants.json", "s2_truncation.json")] + \
        [C.OUT + "/ (chains: ref__*, var__*, k1sig__*)", C.RESULT]

    out = {
        "what": ("PROTOCOL_V3 Addendum I, lead analyst synthesis of the lenses conviction, clock and weights and of the attack "
                 "on V05. IN SAMPLE ONLY: price frames read with the parquet row filter ts < 2022-01-01; official trades "
                 "read with entry_time < 2022-01-01 and exit_time < 2022-01-01 in the read; context-lens tables read with "
                 "t_dec < 2022-01-01; nothing dated 2022 or later was read, simulated or looked at. No validation look."),
        "account_convention": DECL["account"] + " " + DECL["weeks"] + " " + DECL["equal_swing"],
        "first_check_rule2": {
            "all_ten_reproduced": S0["all_ten_reproduced"],
            "official_rows_entered_and_closed_before_2022": S0["official_closed_total"],
            "per_sleeve": rule2,
            "note": ("8 sleeves identical row by row over all their in-sample rows; donch4h_stop and orb_asia_2d_buf10 "
                     "identical on every official row closed before 2022 (494 and 1,038); each has one more official row, "
                     "entered 2021-12-31 and closed in 2022, which was counted but not read; in my run that trade is "
                     "still open at the slice end and is dropped from every statistic. The earlier syntheses quote "
                     "84.235 and 230.065 R including those two rows (-0.066 and -1.080 R): 84.301 - 0.066 and 231.145 - "
                     "1.080, consistent."),
            "chains_equal_context_lens_chains_fp_and_x1_5": all(v[m]["equals_context_chain"] for k, v in S0["chains"].items()
                                                                if not k.startswith("new_") for m in C.MODES),
            "refused_3_spreads": {k: {m: v[m]["refused_3spreads"] for m in C.MODES} for k, v in S0["chains"].items()},
            "P0_window_2018_02_2021_12": p0,
            "P0_matches_synthesis_B": bool(p0["fp"]["trades"] == 5205 and abs(p0["fp"]["total_R"] - 788.59) < 0.01),
        },
        "kept_changes_addendum_I": [],
        "decision": DECL["kept_set_decision"],
        "dropped": [
            {"change": "V05, pooled crypto ridge (conviction lens; verdict weakened)",
             "why": ("fails criterion (a) as declared: my re-simulation " + fmt_ratio("S01_V05", "fp") +
                     f" FP, k {v5['scale_k']}, {v5['pooled']['trades']} trades, +{v5['pooled']['total_R']} R at equal swing "
                     f"against {rf['trades']} trades +{rf['total_R']} R; with costs x1.5 " + fmt_ratio("S01_V05", "stress") +
                     ". The strict reading of rule 3 gives " + fmt_ratio("S02_V05_strict", "fp") +
                     ": a post hoc reading passing by 0.0002 thanks to two trades whose time exits fall on the 2018-12-25 "
                     "00:00 UTC cutoff (truncation test T1b: the declared fit uses 673 training trades, 671 on a frame cut "
                     "at the training cut). On top of K1 (Addendum H, same sleeve, same lead descriptor riskbp) it adds only "
                     + fmt_ratio("S04_K1_V05", "fp", "vs_S03_K1") + " FP and " + fmt_ratio("S04_K1_V05", "stress", "vs_S03_K1") +
                     " with costs x1.5: fails (a) and (b) as an addition. The verifier adds: 2018 fold x0.944, 2018-2021 "
                     "x1.043; 72 % of 2021's gain in 5 weeks; the zero rule removed trades that made +5.5 R; Friday close "
                     "x1.084 with 2019 down; capped account x1.097 with 2019 down; 1,000 EUR account at today's prices "
                     "x0.954 (1 % risk) and x0.993 (2 %). Recommendation of the verifier: do not carry. Noted after this "
                     "synthesis's declaration (15:03 UTC), not used for the decision: three of its four sleeves already "
                     "carry an Addendum H change (K1 on brk72 ethusd; synthesis_A, declared 15:12 UTC and in progress, "
                     "proposes S0.75r on brk72 btcusd and H2 on F1 ethusd), and at most one change per sleeve may go "
                     "forward.")},
            {"change": "the other conviction families (per-sleeve terciles, gated terciles, pooled single descriptor, "
                       "per-sleeve ridge, agreement, combinations)",
             "why": "no candidate: x0.942 to x1.061 pooled FP (lens figures), their nulls overlap them"},
            {"change": "clock lens (hour bands and weekdays)", "why": "no candidate: x0.933 to x1.000 pooled FP"},
            {"change": "weights lens (mean-variance, inverse volatility, trailing switches, rank weights)",
             "why": "no candidate: best IV00 x1.059 with 2019 down (x0.859); the others x0.919 to x0.990"},
        ],
        "results_plain_sum_157_weeks_2019_2021": {
            "S00_reference_equals_account_with_kept_changes_of_I": {"fp": R0f, "stress": R0s},
            "S01_V05_information": {"fp": table("S01_V05", "fp"), "stress": table("S01_V05", "stress")},
            "S02_V05_strict_information": {"fp": table("S02_V05_strict", "fp"), "stress": table("S02_V05_strict", "stress")},
            "S03_K1_addendum_H": {"fp": table("S03_K1", "fp"), "stress": table("S03_K1", "stress")},
            "S04_K1_plus_V05_information": {"fp_vs_S00": table("S04_K1_V05", "fp"), "fp_vs_S03_K1": table("S04_K1_V05", "fp", "vs_S03_K1"),
                                            "stress_vs_S00": table("S04_K1_V05", "stress"),
                                            "stress_vs_S03_K1": table("S04_K1_V05", "stress", "vs_S03_K1")},
            "S05_P2_K1_K2_K3_addendum_H": {"fp": table("S05_P2", "fp"), "stress": table("S05_P2", "stress")},
            "V05_fits": {y: {"coef": f["coef"], "b_lo": round(f["b_lo"], 4), "b_hi": round(f["b_hi"], 4),
                             "zero_on": [k for k, z in f["zero_on"].items() if z], "n_train": f["n_train"]}
                         for y, f in S1["fits"]["fp"]["S01_V05"].items()},
            "V05_trade_changes_fp": S1["variants"]["S01_V05"]["fp"]["trade_changes"],
            "V05_per_crypto_sleeve_fp_unscaled": {k: v for k, v in S1["variants"]["S01_V05"]["fp"]["per_sleeve_oof"].items()
                                                  if k in C.CRYPTO_BRK},
            "K1_folds_fp": S1["k1_folds"]["fp"],
            "K1_fit_for_2022": k22,
        },
        "truncation": {"T1_fits_on_physically_cut_frames": t1, "T2_decisions": {k: t2[k] for k in (
            "decisions", "value_mismatch", "stop_mismatch", "stake_mismatch", "k1_mismatch", "max_abs_diff",
            "negative_control_identical", "pass", "per_sleeve")},
            "reading": ("Every fit is identical when rebuilt from frames cut at 1 January of the year it is used in, and "
                        f"the {t2['decisions']} decisions recomputed on frames cut at the decision give 0 mismatches "
                        f"(descriptors, stop distance, stake, K1 skip); a price read 2 minutes after the decision differs "
                        f"on the cut frame in {t2['decisions'] - t2['negative_control_identical']} of {t2['decisions']}. "
                        "On frames cut at the 7-day purge point, 2019 differs for V05 as declared (673 vs 671 training "
                        "trades: two time exits exactly at 2018-12-25 00:00 UTC; 30 stakes of 2019 change) and for K1 "
                        "(586 vs 585 training signals: one signal decided within the last day before the purge point, its "
                        "outcome known a few hours after it; threshold 505.85 vs 505.61 bp); V05 strict is identical. "
                        "Neither uses anything from the year it is applied to.")},
        "account_before": {"fp": R0f, "stress": R0s},
        "account_after": "identical to account_before: Addendum I keeps no change",
        "growth_meaning": growth,
        "proposed_validation_look": look,
        "summary_for_the_user_fr": summary_fr,
        "ideas_that_do_not_work": IDEAS,
        "caveats": CAVEATS,
        "files": FILES,
        "trials": {"this_synthesis_lines": len(TRIALS), "file": C.TRIALS,
                   "declared_before_runs": os.path.join(C.HERE, "declared.json"),
                   "plus": "1 truncation test (T1: 6 fit rebuilds; T2: 78 decisions)",
                   "lens_trials": {"conviction": "30 variants and controls + reference V00", "clock": 15, "weights": 15},
                   "verifier_V05": "77 lines"},
    }
    C.dump(out, C.RESULT)
    print("written", C.RESULT)
    print(json.dumps({"p0": p0, "k22": k22}, indent=1))


if __name__ == "__main__":
    main()
