"""Lens `weights`, PART 2: evaluate the 15 variants declared in results/r2/sizing/weights/declared.json (declared
before this script ran). IN SAMPLE ONLY (the reference chains of s0_repro.py).

For each variant, universe (U10 judges; U8_noF1 reported beside; U5_gold_us100 information only) and cost mode
(fp; stress = the whole procedure re-run on the x1.5 chains):
  stakes from stakes.py (yearly fits on the expanding history, or trailing state rules);
  out-of-fold book = trades entered in 2019-2021; weekly R booked at the server exit week over every week of
  2019-2021 (157); the variant scaled to the reference's pooled weekly standard deviation (equal weekly swing);
  weekly Sharpe pooled and by year, totals and the user's measures at equal swing, a paired block bootstrap.
Writes one line per variant to results/r2/sizing/weights/trials.jsonl (plus one 'reference' line) and
results/r2/sizing/weights/part2_raw.json (every table), part2_table.csv.
Criteria (a), (b), (c), (d), (f) are computed here; (e) comes from the truncation tests (s3, s4).
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402
import stakes as S  # noqa: E402

U5 = ["ocm4__us100", "noise30__us100", "donch4h_stop__xauusd", "orb_asia_2d_buf10__xauusd", "GOLD_FRI_PM__xauusd"]
UNIV = {"U10": C.UNIVERSES["U10"], "U8_noF1": C.UNIVERSES["U8_noF1"], "U5_gold_us100": U5}
REF = {"id": "REF", "family": "REF"}
BOOT_N, BOOT_BLOCK, BOOT_SEED = 2000, 4, 7


def weekly(b, st, years):
    sel = np.isin(b.year_in.to_numpy(), list(years))
    s = pd.Series(st[sel] * b.R.to_numpy()[sel]).groupby(b.wk_out.to_numpy()[sel]).sum()
    return s.reindex(C.weeks_of_years(years), fill_value=0.0)


def weekly_2018(b, st):
    sel = (b.year_in.to_numpy() == 2018) & (b.t_in.to_numpy() >= C.COMMON_START.value)
    s = pd.Series(st[sel] * b.R.to_numpy()[sel]).groupby(b.wk_out.to_numpy()[sel]).sum()
    ws = C.weeks_of_years((2018,))
    thu = pd.DatetimeIndex((ws * 7).astype("datetime64[D]"))
    ws = ws[thu >= pd.Timestamp("2018-02-01")]
    return s.reindex(ws, fill_value=0.0)


def wsum(x):
    x = np.asarray(x, float)
    return {"weeks": int(len(x)), "sharpe": round(C.sharpe(x), 4), "total": round(float(x.sum()), 2),
            "mean": round(float(x.mean()), 4), "sd": round(float(x.std(ddof=1)), 4),
            "losing_weeks_pct": round(float(100 * (x < 0).mean()), 1), "worst_week": round(float(x.min()), 3),
            "longest_losing_run": C.longest_run(x < 0), "max_dd": round(C.max_dd(x), 2)}


def bootstrap(W0, W1):
    """paired circular block bootstrap of the pooled Sharpe ratio variant / reference (information only)"""
    a, b = np.asarray(W0, float), np.asarray(W1, float)
    n = len(a)
    rng = np.random.default_rng(BOOT_SEED)
    nb = int(np.ceil(n / BOOT_BLOCK))
    r = np.empty(BOOT_N)
    for i in range(BOOT_N):
        st = rng.integers(0, n, nb)
        idx = ((st[:, None] + np.arange(BOOT_BLOCK)[None, :]) % n).ravel()[:n]
        s0, s1 = C.sharpe(a[idx]), C.sharpe(b[idx])
        r[i] = s1 / s0 if s0 > 0 else np.nan
    r = r[np.isfinite(r)]
    return {"draws": int(len(r)), "p_ratio_gt_1": round(float((r > 1).mean()), 3),
            "p_ratio_ge_1.10": round(float((r >= 1.10).mean()), 3),
            "q05": round(float(np.quantile(r, 0.05)), 3), "q50": round(float(np.quantile(r, 0.5)), 3),
            "q95": round(float(np.quantile(r, 0.95)), 3)}


def evaluate(b, st, st0, keys):
    """variant stakes st vs reference stakes st0 on book b (one universe, one mode)"""
    W0, W1 = weekly(b, st0, C.OOF), weekly(b, st, C.OOF)
    sd0, sd1 = float(W0.std(ddof=1)), float(W1.std(ddof=1))
    k = sd0 / sd1 if sd1 > 0 else np.nan
    W1s = W1 * k
    wy = C.week_year(W0.index.to_numpy())
    oof = np.isin(b.year_in.to_numpy(), list(C.OOF))
    R = b.R.to_numpy()
    res = {"k_equal_swing": round(k, 4),
           "pooled": {"ref": wsum(W0), "var_equal_swing": wsum(W1s),
                      "sharpe_ratio": round(C.sharpe(W1) / C.sharpe(W0), 4)},
           "by_year": {}, "bootstrap": bootstrap(W0, W1)}
    up = 0
    for y in C.OOF:
        m = wy == y
        s0, s1 = C.sharpe(W0.to_numpy()[m]), C.sharpe(W1.to_numpy()[m])
        up += int(s1 > s0)
        res["by_year"][y] = {"ref": wsum(W0.to_numpy()[m]), "var_equal_swing": wsum(W1s.to_numpy()[m]),
                             "sharpe_ratio": round(s1 / s0, 4) if s0 > 0 else None, "up": bool(s1 > s0)}
    res["years_up"] = up
    taken = oof & (st > 0)
    res["trades"] = {"oof_trades": int(oof.sum()), "taken": int(taken.sum()),
                     "losing_trades_per_month_ref": round(float((oof & (R < 0)).sum()) / 36, 2),
                     "losing_trades_per_month_var": round(float((taken & (R < 0)).sum()) / 36, 2)}
    so = st[oof]
    res["stakes"] = {"raw_min": round(float(so.min()), 4), "raw_max": round(float(so.max()), 4),
                     "raw_mean": round(float(so.mean()), 4), "scaled_min": round(float(so.min() * k), 4),
                     "scaled_max": round(float(so.max() * k), 4), "scaled_mean": round(float(so.mean() * k), 4),
                     "share_zero": round(float((so == 0).mean()), 4),
                     "mean_by_sleeve_year": {C.SHORT[kk]: {int(y): round(float(st[(b.k.to_numpy() == kk) & (b.year_in.to_numpy() == y)].mean()), 3)
                                                          for y in C.OOF if ((b.k.to_numpy() == kk) & (b.year_in.to_numpy() == y)).any()}
                                             for kk in keys}}
    # early year 2018 (U10 / U8: entries from 2018-02-01), information only
    if any(x.startswith(("brk72", "nq_btc")) for x in keys):
        E0, E1 = weekly_2018(b, st0), weekly_2018(b, st)
        res["early_2018_info"] = {"sharpe_ref": round(C.sharpe(E0), 4), "sharpe_var": round(C.sharpe(E1), 4),
                                  "up": bool(C.sharpe(E1) > C.sharpe(E0))}
    return res


def evaluate_u5(b, st, st0):
    """information only: years 2015-2021 of the five gold / us100 sleeves (scale-free Sharpe by year)"""
    out = {}
    for y in range(2015, 2022):
        W0, W1 = weekly(b, st0, (y,)), weekly(b, st, (y,))
        out[y] = {"sharpe_ref": round(C.sharpe(W0), 4), "sharpe_var": round(C.sharpe(W1), 4),
                  "up": bool(C.sharpe(W1) > C.sharpe(W0))}
    W0, W1 = weekly(b, st0, (2015, 2016, 2017, 2018)), weekly(b, st, (2015, 2016, 2017, 2018))
    out["pooled_2015_2018"] = {"sharpe_ref": round(C.sharpe(W0), 4), "sharpe_var": round(C.sharpe(W1), 4),
                               "ratio": round(C.sharpe(W1) / C.sharpe(W0), 4)}
    W0, W1 = weekly(b, st0, C.OOF), weekly(b, st, C.OOF)
    out["pooled_2019_2021"] = {"sharpe_ref": round(C.sharpe(W0), 4), "sharpe_var": round(C.sharpe(W1), 4),
                               "ratio": round(C.sharpe(W1) / C.sharpe(W0), 4)}
    out["years_up_2015_2018"] = int(sum(out[y]["up"] for y in range(2015, 2019)))
    return out


def folds_table(folds):
    if not folds:
        return None
    return {int(Y): {C.SHORT[k]: round(w, 4) for k, w in f["weights"].items()} for Y, f in folds.items() if Y >= 2016}


def estimates_table(folds):
    if not folds:
        return None
    return {int(Y): {C.SHORT[k]: {"mu_week": round(e[0], 4), "sd_week": round(e[1], 4), "weeks": e[2], "trades": e[3]}
                     for k, e in f["estimates"].items()} for Y, f in folds.items() if Y >= 2018}


def check_f(v, st_all):
    """(f): raw stakes in [0, 2], F1 <= 1, fitted parameters per sleeve <= 3"""
    ok = True
    for (u, mode), (b, st) in st_all.items():
        ok &= bool((st >= 0).all() and (st <= 2.0 + 1e-12).all())
        f1 = np.isin(b.k.to_numpy(), C.F1_KEYS)
        ok &= bool((st[f1] <= 1.0 + 1e-12).all())
    return bool(ok and v.get("fitted_per_sleeve", 0) <= 3)


def main():
    decl = json.load(open(C.DECLARED))
    variants = decl["variants"]
    assert len(variants) <= decl["budget"]["allowed"]
    if os.path.exists(C.TRIALS):
        raise SystemExit("trials.jsonl exists: every variant is evaluated once; remove only by hand if a crash left it partial")
    books = {}
    for mode in C.MODES:
        full = S.book_frame(C.load_book(mode))
        for u, keys in UNIV.items():
            books[(u, mode)] = full[full.k.isin(keys)].reset_index(drop=True)
    ref_st = {um: np.ones(len(b)) for um, b in books.items()}
    raw = {"reference": {}, "variants": {}}
    for (u, mode), b in books.items():
        if u == "U5_gold_us100":
            continue
        W0 = weekly(b, ref_st[(u, mode)], C.OOF)
        raw["reference"][f"{u}|{mode}"] = {"pooled": wsum(W0), "by_year": {y: wsum(W0.to_numpy()[C.week_year(W0.index.to_numpy()) == y]) for y in C.OOF},
                                           "oof_trades": int(np.isin(b.year_in.to_numpy(), list(C.OOF)).sum()),
                                           "losing_trades_per_month": round(float((np.isin(b.year_in.to_numpy(), list(C.OOF)) & (b.R.to_numpy() < 0)).sum()) / 36, 2)}
    C.append_trial({"kind": "reference", "id": "REF", "rule": "equal stakes, 1 R per trade", "results": raw["reference"]})
    rows = []
    for v in variants:
        rec = {"id": v["id"], "family": v["family"], "params": {x: v.get(x) for x in ("lambda", "window_days") if x in v},
               "rule": v["rule"]}
        st_all = {}
        for (u, mode), b in books.items():
            st, folds = S.stakes(b, UNIV[u], v, return_folds=True)
            st_all[(u, mode)] = (b, st)
            if u == "U5_gold_us100":
                rec[f"{u}|{mode}"] = evaluate_u5(b, st, ref_st[(u, mode)])
                continue
            ev = evaluate(b, st, ref_st[(u, mode)], UNIV[u])
            if folds:
                ev["fold_weights"] = folds_table(folds)
                ev["fold_estimates"] = estimates_table(folds)
            rec[f"{u}|{mode}"] = ev
        crit = {}
        for u in ("U10", "U8_noF1"):
            fp, ss = rec[f"{u}|fp"], rec[f"{u}|stress"]
            crit[u] = {"a_sharpe_up_10pct": bool(fp["pooled"]["sharpe_ratio"] >= 1.10),
                       "b_up_2_of_3_years": bool(fp["years_up"] >= 2),
                       "c_holds_costs_x1.5": bool(ss["pooled"]["sharpe_ratio"] >= 1.10 and ss["years_up"] >= 2),
                       "f_stakes_and_parameters": None}
        crit["f"] = check_f(v, {um: x for um, x in st_all.items() if um[0] != "U5_gold_us100"})
        for u in ("U10", "U8_noF1"):
            crit[u]["f_stakes_and_parameters"] = crit["f"]
        rec["criteria_partial"] = crit
        raw["variants"][v["id"]] = rec
        fp, ss = rec["U10|fp"], rec["U10|stress"]
        f8 = rec["U8_noF1|fp"]
        rows.append({"id": v["id"], "family": v["family"], "lambda": v.get("lambda"), "window_days": v.get("window_days"),
                     "U10_fp_sharpe_ref": fp["pooled"]["ref"]["sharpe"], "U10_fp_sharpe_var": round(fp["pooled"]["ref"]["sharpe"] * fp["pooled"]["sharpe_ratio"], 4),
                     "U10_fp_ratio": fp["pooled"]["sharpe_ratio"],
                     "U10_fp_2019": fp["by_year"][2019]["sharpe_ratio"], "U10_fp_2020": fp["by_year"][2020]["sharpe_ratio"],
                     "U10_fp_2021": fp["by_year"][2021]["sharpe_ratio"], "U10_fp_years_up": fp["years_up"],
                     "U10_fp_k": fp["k_equal_swing"], "U10_fp_total_ref": fp["pooled"]["ref"]["total"],
                     "U10_fp_total_var": fp["pooled"]["var_equal_swing"]["total"],
                     "U10_stress_ratio": ss["pooled"]["sharpe_ratio"], "U10_stress_years_up": ss["years_up"],
                     "U8_fp_ratio": f8["pooled"]["sharpe_ratio"], "U8_fp_years_up": f8["years_up"],
                     "U8_stress_ratio": rec["U8_noF1|stress"]["pooled"]["sharpe_ratio"],
                     "U10_boot_p_gt1": fp["bootstrap"]["p_ratio_gt_1"],
                     "U5_ratio_2015_2018": rec["U5_gold_us100|fp"]["pooled_2015_2018"]["ratio"],
                     "U5_years_up_2015_2018": rec["U5_gold_us100|fp"]["years_up_2015_2018"],
                     "U10_2018_up": fp.get("early_2018_info", {}).get("up")})
        print(f"{v['id']:5s} U10 fp ratio {fp['pooled']['sharpe_ratio']:.3f} years {[fp['by_year'][y]['sharpe_ratio'] for y in C.OOF]} "
              f"k {fp['k_equal_swing']:.3f} | stress {ss['pooled']['sharpe_ratio']:.3f} up {ss['years_up']} | "
              f"U8 fp {f8['pooled']['sharpe_ratio']:.3f} up {f8['years_up']} | boot P>1 {fp['bootstrap']['p_ratio_gt_1']}", flush=True)
        C.append_trial({"kind": "variant", **{x: rec[x] for x in ("id", "family", "params", "rule")},
                        "results": {um: {kk: vv for kk, vv in rec[um].items() if kk not in ("fold_estimates",)}
                                    for um in rec if "|" in um},
                        "criteria_partial": crit})
    # (d) neighbours (U10 fp): every declared neighbour above the reference
    for v in variants:
        rec = raw["variants"][v["id"]]
        nb = v.get("neighbours", [])
        for u in ("U10", "U8_noF1"):
            vals = {n: raw["variants"][n][f"{u}|fp"]["pooled"]["sharpe_ratio"] for n in nb}
            rec["criteria_partial"][u]["d_neighbours_improve"] = bool(len(nb) > 0 and all(x > 1.0 for x in vals.values()))
            rec["criteria_partial"][u]["d_neighbour_ratios"] = vals
    C.jdump(raw, os.path.join(C.OUT, "part2_raw.json"))
    pd.DataFrame(rows).to_csv(os.path.join(C.OUT, "part2_table.csv"), index=False)


if __name__ == "__main__":
    main()
