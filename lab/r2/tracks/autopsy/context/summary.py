"""Assemble results/r2/autopsy/context/summary.json from the files written by repro / signals / anatomy / filters /
respec / causality (every table reported in the return of the lens)."""
import json
import os

import numpy as np
import pandas as pd

import common as C
import descr as D

J = lambda f: json.load(open(os.path.join(C.OUT, f)))


def profile(t):
    R = t.R.to_numpy()
    w, l = R[R > 0], R[R < 0]
    return {"n": int(len(R)), "exp": round(float(R.mean()), 4), "total": round(float(R.sum()), 1),
            "win": round(float((R > 0).mean()), 3), "avg_win": round(float(w.mean()), 3),
            "avg_loss": round(float(l.mean()), 3),
            "stop_exit_share": round(float(t.reason.isin(["stop", "trail", "gap"]).mean()), 3),
            "share_of_losses_below_-0.9R": round(float((R < -0.9).sum() / max(1, (R < 0).sum())), 3)}


def main():
    out = {"lens": "context: when do the signals lose (PROTOCOL_V3 Addendum H), in sample only",
           "data_rule": "price rows ts < 2022-01-01 and trades entry_time < 2022-01-01 (filters at read time)"}
    rep = J("baseline_repro.json")
    out["baseline_reproduction"] = {k: {q: v[q] for q in ("n_official", "n_mine", "R_official", "R_mine", "identical",
                                                           "n_differing", "sum_dR_differing", "only_mine", "only_official")}
                                    for k, v in rep["sleeves"].items()}
    out["baseline_reproduction_note"] = ("identical row by row except one trade each in donch4h_stop and orb_asia_2d_buf10, "
                                         "entered on 2021-12-31 and still open when the in-sample slice ends; these two "
                                         "trades are excluded from every statistic below (no in-sample result)")
    prof = {}
    for k in C.KEYS:
        prof[k] = {}
        for mode in ("fp", "stress"):
            ch = pd.read_parquet(os.path.join(C.OUT, "chains", f"{k}__{mode}.parquet"))
            prof[k][mode] = {"whole_in_sample": profile(ch),
                             "2018_2021": profile(ch[ch.entry_time >= pd.Timestamp("2018-01-01", tz="UTC")]),
                             "by_year_R": {int(y): round(float(g.R.sum()), 1) for y, g in ch.groupby(ch.entry_time.dt.year)},
                             "by_year_n": {int(y): int(len(g)) for y, g in ch.groupby(ch.entry_time.dt.year)}}
    out["baseline_profiles"] = prof
    out["signals_info"] = J("signals_info.json")
    # part 1
    out["part1_summary"] = J("anatomy_summary.json")
    sp = pd.read_csv(os.path.join(C.OUT, "separation.csv"))
    an = pd.read_csv(os.path.join(C.OUT, "anatomy.csv"), dtype={"year": str})
    sel = sp[(sp["mode"] == "fp") & (sp.population == "chain")]
    out["part1_separation_fp_trades"] = sel[["sleeve", "descriptor", "n_T1", "n_T3", "E_T1", "E_T2", "E_T3", "welch_t",
                                              "years_valid", "years_pos", "years_neg", "every_year_same_sign",
                                              "y2018_2021_same_sign"]].round(4).to_dict("records")
    sel = sp[(sp["mode"] == "fp") & (sp.population == "every")]
    out["part1_separation_fp_every_signal"] = sel[["sleeve", "descriptor", "n_T1", "n_T3", "E_T1", "E_T2", "E_T3",
                                                    "welch_t", "years_valid", "years_pos", "years_neg",
                                                    "every_year_same_sign"]].round(4).to_dict("records")
    key = sp[(sp["mode"] == "fp") & (sp.population == "chain") & (sp.every_year_same_sign | (sp.welch_t.abs() >= 2))]
    tabs = {}
    for r in key.itertuples():
        q = an[(an.sleeve == r.sleeve) & (an.descriptor == r.descriptor) & (an.population == "chain") & (an["mode"] == "fp")]
        t = {}
        for y, g in q.groupby("year"):
            t[y] = {f"T{int(x.group)}": {"n": int(x.n), "exp": round(float(x.exp), 3), "win": round(float(x.win), 3)}
                    for x in g.itertuples()}
        b = q[q.year == "all"][["group", "lo", "hi"]]
        tabs[f"{r.sleeve}|{r.descriptor}"] = {"bounds": {f"T{int(x.group)}": [round(x.lo, 4), round(x.hi, 4)] for x in b.itertuples()},
                                               "by_year": t}
    out["part1_tables_of_separating_descriptors_fp_trades"] = tabs
    # part 2
    v = J("part2_verdicts.json")
    raw = J("part2_raw.json")
    p2 = {}
    for k in C.KEYS:
        fp, st = raw[k]["fp"], raw[k]["stress"]
        d = {"oof_years": fp["years_oof"], "W": fp["W"], "applicable_filters": fp["applicable_filters"],
             "baseline_W_fp": None, "baseline_W_stress": None, "declared": {}}
        for vid, c in fp["variants"].items():
            if not (vid.endswith("_q0.333") or vid == "ridge_a1"):
                continue
            cs = st["variants"][vid]
            inf, infs = fp["variants"].get(vid + "_infold"), st["variants"].get(vid + "_infold")
            d["baseline_W_fp"], d["baseline_W_stress"] = c["base_W"], cs["base_W"]
            d["declared"][vid] = {"oof_fp": c["var_W"], "oof_stress": cs["var_W"],
                                  "infold_fp": inf["var_W"] if inf else None, "infold_stress": infs["var_W"] if infs else None,
                                  "skipped_signals_fp": c["n_skipped_signals"], "skipped_trades_fp": c["n_skipped_chain_trades"],
                                  "new_trades_fp": c["new_trades"],
                                  "by_year_fp": {y: [p["exp_b"], p["exp_v"], round(p["tot_b"], 1), round(p["tot_v"], 1)]
                                                 for y, p in c["by_year"].items()},
                                  "criteria": v["verdicts_declared"][k].get(vid)}
        p2[k] = d
    out["part2"] = p2
    out["part2_note"] = ("W = out-of-fold years inside 2018-2021; by_year_fp = [exp before, exp after, total before, total after]; "
                         "all 327 variants (declared + neighbours) are in trials.jsonl and part2_table.csv")
    rs = J("respec.json")
    out["respec_brk72_ethusd_riskbp"] = {"verdict": rs["verdict_riskbp_q0.333"],
                                        **{f"{m}_{vid}": {"base_W": rs["results"][m]["variants"][vid]["base_W"],
                                                          "var_W": rs["results"][m]["variants"][vid]["var_W"],
                                                          "by_year": rs["results"][m]["variants"][vid]["by_year"]}
                                           for m in ("fp", "stress") for vid in ("riskbp_q0.25", "riskbp_q0.333", "riskbp_q0.40",
                                                                                "riskbp_q0.333_infold")},
                                        "folds_fp": rs["results"]["fp"]["variants"]["riskbp_q0.333"]["info"]["folds"],
                                        "fit_all_in_sample_fp": rs["results"]["fp"]["variants"]["riskbp_q0.333_infold"]["info"]["fit"]}
    if os.path.exists(os.path.join(C.OUT, "causality.json")):
        out["causality"] = J("causality.json")
    if os.path.exists(os.path.join(C.OUT, "causality_control.json")):
        out["causality_negative_control"] = J("causality_control.json")
    # overview of part 2 (declared variants, FP, window W)
    t = pd.read_csv(os.path.join(C.OUT, "part2_table.csv"))
    d = t[t.declared & (t["mode"] == "fp")]
    act = d[(d.n_v != d.n_b) | ((d.exp_v - d.exp_b).abs() > 1e-9)]
    out["part2_overview"] = {
        "declared_variants": int(len(d)), "all_variants_with_neighbours": int((t["mode"] == "fp").sum()),
        "skipped_nothing_out_of_fold": int((d.skipped_signals == 0).sum()),
        "changed_window_W": int(len(act)), "exp_up": int((act.exp_v > act.exp_b).sum()),
        "exp_down": int((act.exp_v < act.exp_b).sum()),
        "exp_up_20pct_and_total_not_lower": int(((act.exp_v >= act.exp_b + 0.2 * act.exp_b.abs()) & (act.tot_v >= act.tot_b)).sum()),
        "sum_total_R_change_of_variants_that_acted": round(float((act.tot_v - act.tot_b).sum()), 1),
        "passed_a_to_e": v["candidates_before_causality"],
        "addendum": "riskbp re-specification of the brk72_24h_wd__ethusd sprR candidate: passes (a)-(e) and (f)"}
    # portfolio context (in sample, FP): what the candidate changes
    port = {}
    for a, b in ((2019, 2021), (2018, 2021)):
        n = tot = 0
        for k in C.KEYS:
            ch = pd.read_parquet(os.path.join(C.OUT, "chains", f"{k}__fp.parquet"))
            yy = ch.entry_time.dt.year
            cc = ch[(yy >= a) & (yy <= b)]
            n += len(cc)
            tot += float(cc.R.sum())
        port[f"{a}-{b}"] = {"trades": n, "total_R": round(tot, 1), "R_per_trade": round(tot / n, 4),
                            "trades_per_month": round(n / ((b - a + 1) * 12), 1)}
    c = rs["results"]["fp"]["variants"]["riskbp_q0.333"]
    dn = c["var_W"]["n"] - c["base_W"]["n"]
    dR = c["var_W"]["total"] - c["base_W"]["total"]
    p = port["2019-2021"]
    port["2019-2021_with_candidate"] = {"trades": p["trades"] + dn, "total_R": round(p["total_R"] + dR, 1),
                                        "R_per_trade": round((p["total_R"] + dR) / (p["trades"] + dn), 4)}
    out["portfolio_context_fp"] = port
    out["trials"] = sum(1 for _ in open(os.path.join(C.OUT, "trials.jsonl")))
    C.dump(out, os.path.join(C.OUT, "summary.json"))
    print("summary written; trials", out["trials"])


if __name__ == "__main__":
    main()
