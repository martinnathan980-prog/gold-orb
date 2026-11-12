"""PROTOCOL_V3 Addendum J, round 4 lead synthesis, steps 1-4: writes lab/results/r2/round4/synthesis.json from
verification.json (my recomputation of the five main verdicts) and account.json (the ten's weekly Sharpe in sample).
IN SAMPLE ONLY: nothing here reads data; the two inputs were built from in-sample rows only.
"""
import datetime as dt
import hashlib
import json
import os

from common import HERE, LAB, dump

V = json.load(open(os.path.join(HERE, "verification.json")))
A = json.load(open(os.path.join(HERE, "account.json")))
IDEAS = os.path.join(LAB, "results", "r2", "round4_ideas.json")
SHA = hashlib.sha256(open(IDEAS, "rb").read()).hexdigest()
assert SHA == "c81387985baf8e43d64caa339c75daf4d3ff936a925ef28d97ff94755b5e225a"
RULES = ["idxrs_1000", "fx_weekend", "ger40_noise30_xetra", "fomc_cycle", "letf_close_pair"]
assert not any(V[r]["passes"] for r in RULES) and A["kept_rules"] == []
TRIALS = {r: sum(1 for _ in open(os.path.join(LAB, "results", "r2", "round4", r, "trials.jsonl"))) for r in RULES}

i, f, g, o, l_ = (V[r] for r in RULES)
ia = A["information_only_idxrs_1000_not_kept"]["server"]
ts, tw, te = A["ten_server"], A["ten_wsun"], A["ten_wsun_entries_2014_2021"]

results = [
    {"name": "IDXRS_1000: US index relative-strength pair, 10:00 to 15:55 New York",
     "in_sample": (
         "FAIL on one bar. Main (10:00 ranking and entry, Q75 over 60 sessions, stop 1.5 sd_pi, exit 15:55 New York), "
         f"in sample, FP costs: {i['main']['n']} pairs, entries 2014-03-07..2021-12-28. PF {i['main']['pf']:.3f}; "
         f"t {i['main']['t_trade']:.2f} against the 2.5 bar, the only failed bar (2.28 on weekly sums, "
         f"{i['money_version']['t_trade']:.2f} on the money version: every reading fails); "
         f"{i['main']['exp_R']:+.4f} R per pair, {i['main']['total_R']:+.1f} R; years {i['main']['years_pos']}; "
         f"PF {i['stress_x1.5']['pf']:.2f} at costs x1.5; neighbours' median PF {i['neighbours_median_pf']:.3f}; "
         f"every-signal = main; max hold {i['main']['max_hold_h']:.1f} h; null percentile {i['null']['percentile']:.1f} "
         f"(null p97.5 {i['null']['null_p975']:+.3f} R); weekly rho with ocm4 + noise30 "
         f"{i['correlation_wsun_2014_2021']['cluster_us100']:.3f} (bar 0.30); 2 of 3 pair types positive "
         "(us500/us30 -0.217 R on 8 pairs). Before costs t 3.10 (+6.1 bp per pair); FP costs of 1.6 bp per pair take it "
         f"under the bar; t 2.5 would need {i['t_gap']['mean_needed_for_t2.5_at_same_sd']:+.3f} R per pair at the same "
         "dispersion. 2020 gives +19.7 of the +43.7 R (without 2020: 442 pairs, t 1.29); the 10 best pairs give +30.5 R. "
         "My recomputation from the engineer's main, stress, neighbour, gross and null files gives the same figures."),
     "attack": ("None run: Addendum J attacks only in-sample passes, so there is no verdict. Its three neighbours with "
                "t >= 2.5 (Q67 2.78, Q80 2.72, 40-session windows 3.05) cannot stand in for it: the verdict is read on "
                "the main only, and picking a neighbour after seeing the table is selection."),
     "kept": False},
    {"name": "FX weekend overreaction fade (G10 basket)",
     "in_sample": (
         "FAIL on 9 of the 11 basket bars (only n and hold pass). Main (P75 of |z|, decision Sunday 20:00 New York, "
         "out Monday 16:00, stop 1 x ATR(20)), 8 pairs as one basket, in sample, FP costs: "
         f"{f['main']['n']} trades on {f['days']} Mondays, entries 2014-04-13..2021-12-26 (New York). Pooled PF "
         f"{f['main']['pf']:.3f}; t on Monday sums {f['t_daily_sums']:.2f}; {f['main']['exp_R']:+.4f} R per trade, "
         f"{f['main']['total_R']:+.1f} R; years {f['main']['years_pos']}; pairs positive 2/8; PF "
         f"{f['stress_x1.5']['pf']:.3f} at costs x1.5; neighbours' median PF {f['neighbours_median_pf']:.3f} (none "
         f"reaches 1.0); null percentile {f['null']['percentile']:.1f}. No gross edge: -0.19 bp per trade before costs "
         "(engineer's accounting); by Monday 16:00 the weekend move has come back +0.6 bp of a 29 bp mean move. "
         "My recomputation gives the same figures. The judge's MT5 Sunday-spread check is moot."),
     "attack": "None run: failed in sample (Addendum J attacks only passes); no verdict.",
     "kept": False},
    {"name": "ger40_noise30_xetra: the frozen us100 noise-area rule on the DAX's own cash clock",
     "in_sample": (
         "FAIL on 6 of 10 bars. Main (frozen noise30: lookback 14, band 1.0, checks 09:30-17:00 Berlin every 30 min, "
         f"exit 17:25), in sample, FP costs: {g['main']['n']:,} trades, entries 2014-01-03..2021-12-29. PF "
         f"{g['main']['pf']:.3f}; t {g['main']['t_trade']:.2f}; {g['main']['exp_R']:+.4f} R per trade "
         f"({g['main']['total_R']:+.1f} R; -0.3 bp per trade in money terms); years {g['main']['years_pos']}; PF "
         f"{g['stress_x1.5']['pf']:.3f} at costs x1.5; neighbours' median PF {g['neighbours_median_pf']:.3f}; null "
         f"percentile {g['null']['percentile']:.1f}. Passes n, every-signal, hold and the declared |weekly rho with the "
         f"ten| <= 0.30 ({g['correlation_wsun_2014_2021']['sum_of_ten']:+.3f}). Gross +0.66 bp per trade (t 1.40) against "
         "about 0.96 bp of cost. My recomputation gives the same figures."),
     "attack": "None run: failed in sample (Addendum J attacks only passes); no verdict. The judge's follow-ups "
               "(ger40_ocm4_xetra, UK100, AUS200) were conditional on a pass and are not triggered.",
     "kept": False},
    {"name": "FOMC-cycle even/odd weeks, long-short on US500",
     "in_sample": (
         "FAIL on 7 of the 9 section-4 bars and on the declared ger40 condition. Main (us500, long W0/W2/W4/W6, short "
         "W1/W3/W5, flat W-1, in and out at 15:55 New York, stop 3 x ATR(20)), in sample, FP costs: "
         f"{o['main']['n']} trades, entries 2013-06-17..2021-12-20. PF {o['main']['pf']:.3f}; t {o['main']['t_trade']:.2f}; "
         f"{o['main']['exp_R']:+.4f} R per trade, {o['main']['total_R']:+.1f} R; years {o['main']['years_pos']}; PF "
         f"{o['stress_x1.5']['pf']:.3f} at spread, slippage and swap x1.5; neighbours' median PF "
         f"{o['neighbours_median_pf']:.3f}; null percentile {o['null']['percentile']:.1f}; ger40 check "
         f"{o['ger40_mechanism']['exp_R']:+.4f} R ({o['ger40_mechanism']['n']} trades, PF {o['ger40_mechanism']['pf']:.3f}). "
         "Gross +0.15 bp per trade (t 0.61) against about 6 bp of cost, mostly the long-side swap; the even-minus-odd "
         "market move is -5 bp a week (t -0.24): the published effect is absent. My recomputation gives the same figures."),
     "attack": "None run: failed in sample (Addendum J attacks only passes); no verdict.",
     "kept": False},
    {"name": "LETF_CLOSE_PAIR: Nasdaq-100 against the Dow in the last half hour of big days",
     "in_sample": (
         "FAIL on 8 of 10 bars (only n and hold pass). Main (15:30 signal on big same-sign days, us100 against us30, "
         f"stop 1.5 sd_pi, exit 15:59 New York), in sample, FP costs: {l_['main']['n']} pairs, entries "
         f"2014-03-03..2021-12-27. PF {l_['main']['pf']:.3f}; t {l_['main']['t_trade']:.2f}; {l_['main']['exp_R']:+.4f} R "
         f"per pair, {l_['main']['total_R']:+.1f} R; years {l_['main']['years_pos']}; PF {l_['stress_x1.5']['pf']:.3f} at "
         f"costs x1.5; neighbours' median PF {l_['neighbours_median_pf']:.3f}; null percentile "
         f"{l_['null']['percentile']:.1f}; knife-edge exits PF {l_['neighbours']['trades_05_n_exit_1557']['pf']:.3f} "
         f"(15:57) and {l_['neighbours']['trades_06_n_exit_1605']['pf']:.3f} (16:05) against 1.06. Gross +0.24 bp per "
         "pair (t 0.49) against 1.7 bp of cost. My recomputation gives the same figures."),
     "attack": "None run: failed in sample (Addendum J attacks only passes); no verdict.",
     "kept": False},
]

account = (
    "No rule is kept, so the account with the kept rules is the ten alone. In sample 2014-2021, FP costs, 1 R per "
    "trade, plain sum of the official one-position chains, weekly R booked at the exit, all 418 calendar weeks counted "
    f"(my own code): weekly Sharpe {ts['sharpe']:.2f} on FP server weeks ({tw['sharpe']:.2f} on UTC Monday-Sunday weeks; "
    f"{te['sharpe']:.3f} in the engineers' variant counting only trades entered 2014-2021); {ts['trades_booked']:,} "
    f"trades, {ts['total_R']:+,.1f} R, {ts['mean_week_R']:+.2f} R a week (sd {ts['sd_week_R']:.2f}), "
    f"{ts['losing_weeks_pct']:.1f} % losing weeks, worst week {ts['worst_week_R']:.1f} R. With = without: "
    f"{ts['sharpe']:.2f} -> {ts['sharpe']:.2f}. Information only, deciding nothing: had IDXRS_1000's in-sample main "
    f"(failed, not kept) been added at 1 R per pair, the Sharpe would read {ia['ten_plus_idxrs_1R']:.3f} instead of "
    f"{ia['ten']:.3f} (+{100 * (ia['ratio_1R'] - 1):.1f} %; best-weighting bound +{100 * (ia['best_ratio'] - 1):.1f} %), "
    f"i.e. +{ia['mean_week_R_equal_swing']['ten_plus_idxrs'] - ia['mean_week_R_equal_swing']['ten']:.3f} R a week at "
    f"equal weekly swing; its own weekly Sharpe {ia['idxrs_weekly_sharpe']:.2f} against a break-even of "
    f"{ia['break_even_s=c*S']:.2f} (correlation {ia['corr_with_ten']:.2f} x {ia['ten']:.2f}).")

caveats = [
    "All five fail in sample. My recomputation from the engineers' trade, stress, neighbour, gross and null files "
    "(r2/tracks/round4/synthesis/verify_verdicts.py) gives every judged figure to rounding. None was attacked, because "
    "Addendum J attacks only in-sample passes. Nothing goes to 2022-2025, and no look is declared.",
    "IDXRS_1000 misses on one bar only, t 2.15 against 2.5 on 518 pairs. It would need +0.098 R per pair at the same "
    "dispersion instead of +0.084, about 16 % more. It is still a fail, and the protocol drops it. Its neighbours with "
    "t >= 2.5 cannot replace it: that would be selection after seeing the results.",
    "IDXRS_1000's in-sample profit is concentrated: 2020 gives +19.7 of +43.7 R (without 2020, t 1.29 on 442 pairs), "
    "and the 10 best of 518 pairs give +30.5 R. 445 of its 518 pairs are us100/us30. Its weekly correlation with "
    "ocm4 + noise30 is 0.234, so part of it is the us100 cluster again.",
    "Gross edges against costs, per trade, in sample: IDXRS_1000 +6.1 bp against 1.6 bp; ger40 Xetra +0.66 bp against "
    "about 0.96 bp; LETF +0.24 bp against 1.7 bp; FOMC +0.15 bp against about 6 bp (mostly swap); FX weekend -0.19 bp "
    "before costs. Only IDXRS_1000 has a gross edge worth the name.",
    "Costs are the lab's frozen FP model: today's spreads in bp with Dukascopy's intraday shape, modelled slippage, and "
    "swaps where charged. There are no broker fill statistics. A wider real cost could only deepen the fails.",
    "Information only: even at its in-sample face value, IDXRS_1000 would have raised the ten's weekly Sharpe by under "
    "1 % (2.51 -> 2.53). Breadth from this pool could not approach the user's x4.4 gap, as Addendum J said before the run.",
    f"Round 4 logged {sum(TRIALS.values())} configurations ({' + '.join(str(TRIALS[r]) for r in RULES)}), losing ones "
    "included, each declared in declared.json before its run (file times checked). My recomputations and the account "
    "measure simulate nothing and are not trials.",
    "In sample only. I read the engineers' in-sample trade files and the official trades of the ten, with "
    "entry_time < 2022-01-01 and exit_time < 2022-01-01 inside each read call. No price frame and no 2022+ row was read. "
    "The two exposures the engineers disclosed touch no verdict: LETF saw two DAX rules' 2022-2025 lines in an idx_eu "
    "report before its declaration, and FX printed the keys of recalc/summary.json.",
    "The engineers used slightly different conventions for weeks, year attribution and open details, each written in "
    "declared.json before the run. None changes a verdict: each of the other four rules fails at least six bars, and "
    "IDXRS_1000 fails its t under every reading (2.15 per pair, 2.28 on weekly sums, 2.14 on the money version).",
    "Data gaps, as the engineers reported them: sparse Q4 2013 index data (IDXRS_1000's first trade is 2014-03-07; LETF "
    "has 28 trades in 2014); sparse early-2013 us500 (FOMC lost 17 trades); LETF neighbour (6) is partly a data artifact "
    "(no us100/us30 quotes after 16:00 New York in 2016-2017).",
    "Files: I wrote only under lab/r2/tracks/round4/synthesis/ and lab/results/r2/round4/synthesis.json. I modified no "
    "existing file and ran no git command that changes anything. The validation_hi files git shows as modified belong to "
    "other jobs.",
]

summary_fr = "\n".join([
    "Aucune des 5 nouvelles règles ne passe sur 2014-2021 : rien n'est gardé, aucun test sur 2022-2025.",
    "La plus proche, la paire d'indices US de 10h à 15h55 (New York) : 518 paires, +0,08 R par paire.",
    "Elle échoue sur la solidité statistique : t = 2,15 pour 2,5 exigé (3,1 avant frais).",
    "Et 45 % de son gain vient de la seule année 2020. Elle est abandonnée, comme prévu par le protocole.",
    "Les 4 autres ne gagnent rien de mesurable après frais (facteur de profit 0,75 à 1,03 ; 355 à 2 012 trades) :",
    "week-end des devises, DAX à l'heure de Francfort, cycle de la Fed, fin de séance Nasdaq contre Dow.",
    "Votre robot reste les dix règles actuelles : Sharpe hebdomadaire 2,5 sur 2014-2021, inchangé.",
    "Même gardée, la meilleure aurait ajouté moins de 1 % à ce Sharpe.",
    "Annoncé avant le test : 83 % de chances que rien ne passe ; l'écart ×4,4 avec votre demande ne viendra pas de là.",
    "Tout est mesuré sur les années de recherche ; rien après 2021 n'a été lu.",
])
assert len(summary_fr.splitlines()) <= 10

out = {
    "addendum": "PROTOCOL_V3 Addendum J (round 4), lead analyst synthesis",
    "written_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    "in_sample_only": ("Inputs: the five engineers' in-sample result files and the ten's official trades read with "
                       "entry_time AND exit_time < 2022-01-01 inside the read call. No price frame, no 2022+ row."),
    "judge_file": {"path": "results/r2/round4_ideas.json", "sha256": SHA},
    "decision": {"kept": [], "why": ("Step 1 keeps a rule only if it passed in sample AND its attack verdict is "
                                     "confirmed or weakened with an edge still positive. No rule passed in sample "
                                     "(engineers' verdicts, recomputed by me); none was attacked."),
                 "validation_look": "none: nothing is kept, so no look at 2022-2025 is declared for round 4"},
    "results": results,
    "lead_recomputation": {r: {"passes": V[r]["passes"], "failed_bars": V[r]["failed_bars"], "main": V[r]["main"],
                               "stress_x1.5": V[r]["stress_x1.5"], "neighbours_median_pf": V[r]["neighbours_median_pf"],
                               "null": V[r]["null"], "correlation_wsun_2014_2021": V[r]["correlation_wsun_2014_2021"]}
                           for r in RULES},
    "account_effect_in_sample": account,
    "account_numbers": A,
    "proposed_validation_look": "",
    "trials_round4": {**TRIALS, "total": sum(TRIALS.values())},
    "open_questions_settled_in_sample": {
        "index relative value at 10:00 (IDXRS_1000)": "a gross edge of about 6 bp per pair (t 3.1) that FP costs bring under the t bar (2.15); fails as declared",
        "FX weekend fade": "no gross edge (-0.19 bp per trade); the weekend move does not come back",
        "DAX on its own cash clock (noise30)": "no edge worth the cost (+0.66 bp gross, about 0.96 bp cost)",
        "FOMC-cycle even/odd weeks": "the effect is absent (-5 bp a week even minus odd, t -0.24)",
        "LETF close pair": "no edge (+0.24 bp gross, 1.7 bp cost); loses in 7 of 8 years"},
    "caveats": caveats,
    "summary_for_the_user_fr": summary_fr,
    "files": ["lab/r2/tracks/round4/synthesis/common.py", "lab/r2/tracks/round4/synthesis/verify_verdicts.py",
              "lab/r2/tracks/round4/synthesis/account.py", "lab/r2/tracks/round4/synthesis/build_synthesis.py",
              "lab/r2/tracks/round4/synthesis/verification.json", "lab/r2/tracks/round4/synthesis/account.json",
              "lab/results/r2/round4/synthesis.json"],
}
dump(out, os.path.join(LAB, "results", "r2", "round4", "synthesis.json"))
print(json.dumps({k: out[k] for k in ("decision", "trials_round4")}, indent=1, ensure_ascii=False))
print(account)
print(summary_fr)
for r in results:
    print("-", r["name"], "|", r["in_sample"][:160])
