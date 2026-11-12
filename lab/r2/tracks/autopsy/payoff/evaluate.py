"""Evaluation of the payoff variants against the declared candidate criteria, plus risk measures.  IN SAMPLE ONLY.

Reads trials.jsonl, reference_<name>__<sym>.parquet/json and trades_<name>__<sym>.parquet (all written by run.py);
no price frame is needed.  Writes evaluation.json and variants_table.csv in results/r2/autopsy/payoff/.

Extra measures (common window, per cost mode), computed from the trade lists:
  sd_R            standard deviation of R per trade
  sharpe_trade    exp_R / sd_R: does not depend on the position size, so a stop change that only re-scales the
                  bet leaves it unchanged; the 'x2b' diagnostic of Addendum G (edge x f at unchanged noise) is a
                  statement about this ratio
  bps_trade       mean net pnl in basis points of the entry price (constant notional, no sizing)
  cost_tol_bp     extra cost per trade (bp of price) that would erase the variant's lead in expectancy over the
                  reference: (exp_v - exp_ref) / (mean(1e-4 x entry / risk)_v - same_ref); inf when the variant is not
                  more cost-sensitive than the reference
  max_dd_R, longest_losing_run, months_pos (share of exit months with a positive sum), worst_month_R
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

TRIALS = os.path.join(C.OUT, "trials.jsonl")
SHAPE_BE1 = {  # results/r2/shape/trials.jsonl, variant BE1, whole in-sample period, FP costs (quoted, not re-run)
    "noise30:us100": {"exp_R": 0.0867, "total_R": 142.4, "avg_loss_R": -0.402, "base_exp_R": 0.0818, "base_total_R": 134.4},
    "ocm4:us100": {"exp_R": 0.1464, "total_R": 146.3, "avg_loss_R": -0.652, "base_exp_R": 0.137, "base_total_R": 136.9},
    "brk72_24h_wd:btcusd": {"exp_R": 0.2588, "total_R": 169.2, "avg_loss_R": -0.624, "base_exp_R": 0.268, "base_total_R": 172.9},
    "F1_brk_ridge_filter:btcusd": {"exp_R": 0.3396, "total_R": 216.7, "avg_loss_R": None, "base_exp_R": 0.3588, "base_total_R": 226.4},
    "orb_asia_2d_buf10:xauusd": {"exp_R": 0.141, "total_R": 161.3, "avg_loss_R": None, "base_exp_R": 0.2196, "base_total_R": 228.0},
}


def risk_measures(t):
    t = C.window(t, "common")
    R = t["R"].to_numpy(float)
    if len(R) < 3:
        return {}
    sd = float(R.std(ddof=1))
    neg = R < 0
    run = best = 0
    for x in neg:
        run = run + 1 if x else 0
        best = max(best, run)
    mo = t.groupby(t.exit_time.dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period("M"))["R"].sum()
    cum = np.cumsum(R)
    dd = float((np.maximum.accumulate(np.r_[0.0, cum]) - np.r_[0.0, cum]).max())
    return {"n": int(len(R)), "exp_R": float(R.mean()), "sd_R": sd, "sharpe_trade": float(R.mean() / sd),
            "t_stat": float(R.mean() / sd * math.sqrt(len(R))), "bps_trade": float((t["pnl"] / t["entry"]).mean() * 1e4),
            "R_per_bp": float((1e-4 * t["entry"] / t["risk"]).mean()), "max_dd_R": dd, "longest_losing_run": int(best),
            "months_pos": float((mo > 0).mean()), "worst_month_R": float(mo.min()), "total_R": float(R.sum())}


def cost_tol(v, r):
    dv = v["exp_R"] - r["exp_R"]
    dc = v["R_per_bp"] - r["R_per_bp"]
    if dv <= 0:
        return 0.0
    return float(dv / dc) if dc > 1e-12 else float("inf")


def neighbours(spec, ids):
    f, i = spec["family"], spec["id"]
    if f == "S":
        if spec["k"] == 1.5:
            return []
        suf = {True: "r", False: "n"}.get(spec.get("reentry"), "")
        grid = [0.25, 0.5, 0.75]
        j = grid.index(spec["k"])
        return [f"S{grid[x]}{suf}" for x in (j - 1, j + 1) if 0 <= x < 3]
    if f == "T":
        return [f"T{m}" for m in (spec["m"] - 1, spec["m"] + 1) if 1 <= m <= 3]
    if f == "H":
        return ["H2" if spec["j"] == 1 else "H1"]
    if f == "B":
        return ["B1.5" if spec["b"] == 1.0 else "B1.0"]
    return []


def criteria(key, spec, line, ref, lines_by_id, ref_stress):
    v, r = line["fp"]["common"], ref["fp"]["common"]
    vs, rs = line["stress"]["common"], ref["stress"]["common"]
    out = {}
    if not v.get("n") or not r.get("n"):
        return {"candidate": False, "why": "no trades"}
    e_ok = (r["exp_R"] > 0 and v["exp_R"] >= 1.2 * r["exp_R"]) or (r["exp_R"] <= 0 and v["exp_R"] > r["exp_R"]
                                                                 and v["exp_R"] >= r["exp_R"] + 0.2 * abs(r["exp_R"]))
    l_ok = (abs(v["avg_loss_R"]) <= 0.8 * abs(r["avg_loss_R"])) and v["exp_R"] >= r["exp_R"]
    route = "E" if e_ok else ("L" if l_ok else None)
    out["a"] = route is not None
    out["route"] = route
    out["exp_gain_pct"] = round(100 * (v["exp_R"] / r["exp_R"] - 1), 1) if r["exp_R"] > 0 else None
    out["avg_loss_change_pct"] = round(100 * (abs(v["avg_loss_R"]) / abs(r["avg_loss_R"]) - 1), 1)
    out["b"] = v["total_R"] >= r["total_R"]
    yv, yr = line["fp"]["by_year"], ref["fp"]["by_year"]
    yrs = [str(y) for y in C.YEARS]
    if route == "L":
        better = [str(y) in yv and str(y) in yr and abs(yv[str(y)]["avg_loss_R"]) < abs(yr[str(y)]["avg_loss_R"])
                  for y in C.YEARS]
    else:
        better = [str(y) in yv and str(y) in yr and yv[str(y)]["exp_R"] > yr[str(y)]["exp_R"] for y in C.YEARS]
    out["years_better"] = f"{sum(better)}/4"
    out["c"] = sum(better) >= 3
    if route == "L":
        d_a = (abs(vs["avg_loss_R"]) <= 0.8 * abs(rs["avg_loss_R"])) and vs["exp_R"] >= rs["exp_R"]
    else:
        d_a = (rs["exp_R"] > 0 and vs["exp_R"] >= 1.2 * rs["exp_R"]) or (rs["exp_R"] <= 0 and vs["exp_R"] >= rs["exp_R"]
                                                                     + 0.2 * abs(rs["exp_R"]) and vs["exp_R"] > rs["exp_R"])
    out["d"] = bool(d_a and vs["total_R"] >= rs["total_R"])
    nb = neighbours(spec, lines_by_id)
    nb_ok = []
    for x in nb:
        if x in lines_by_id:
            c = lines_by_id[x]["fp"]["common"]
            if route == "L":
                nb_ok.append(abs(c["avg_loss_R"]) < abs(r["avg_loss_R"]) and c["exp_R"] >= r["exp_R"])
            else:
                nb_ok.append(c["exp_R"] > r["exp_R"] and c["total_R"] >= r["total_R"])
        elif x == "B1.0" and key in SHAPE_BE1:
            s = SHAPE_BE1[key]
            if route == "L":
                nb_ok.append(s["avg_loss_R"] is not None and s["exp_R"] >= s["base_exp_R"])
            else:
                nb_ok.append(s["exp_R"] > s["base_exp_R"] and s["total_R"] >= s["base_total_R"])
        else:
            nb_ok.append(False)
    out["neighbours"] = nb
    out["neighbours_improve"] = nb_ok
    out["e"] = bool(nb) and all(nb_ok)
    out["candidate_a_to_e"] = bool(out["a"] and out["b"] and out["c"] and out["d"] and out["e"])
    return out


def main():
    lines = [json.loads(x) for x in open(TRIALS)]
    by_sleeve = {}
    for d in lines:
        by_sleeve.setdefault(d["sleeve"], []).append(d)
    ev = {"n_variants_logged": len(lines), "sleeves": {}}
    rows = []
    for key, ls in by_sleeve.items():
        name, sym = key.split(":")
        ref = json.load(open(os.path.join(C.OUT, f"reference_{name}__{sym}.json")))
        rt = pd.read_parquet(os.path.join(C.OUT, f"reference_{name}__{sym}.parquet"))
        tr = pd.read_parquet(os.path.join(C.OUT, f"trades_{name}__{sym}.parquet"))
        rm = {m: risk_measures(rt[rt["mode"] == m]) for m in ("fp", "stress")}
        ids = {d["variant"]["id"]: d for d in ls}
        sl = {"reference": {"fp": ref["fp"]["common"], "stress": ref["stress"]["common"], "risk": rm,
                            "by_year": ref["fp"]["by_year"], "early": ref["fp"]["early"]}, "variants": {}}
        rows.append({"sleeve": key, "variant": "reference", **{f"fp_{k}": v for k, v in ref["fp"]["common"].items()
                                                                if k != "reasons"},
                     "fp_sharpe_trade": rm["fp"].get("sharpe_trade"), "stress_exp_R": ref["stress"]["common"].get("exp_R"),
                     "stress_total_R": ref["stress"]["common"].get("total_R"),
                     "stress_sharpe_trade": rm["stress"].get("sharpe_trade"), "fp_bps_trade": rm["fp"].get("bps_trade")})
        for vid, d in ids.items():
            vm = {m: risk_measures(tr[(tr["variant"] == vid) & (tr["mode"] == m)]) for m in ("fp", "stress")}
            for m in ("fp", "stress"):
                if vm[m]:
                    vm[m]["cost_tol_bp"] = cost_tol(vm[m], rm[m])
                    vm[m]["sharpe_ratio_vs_ref"] = vm[m]["sharpe_trade"] / rm[m]["sharpe_trade"] if rm[m]["sharpe_trade"] else None
            cr = criteria(key, d["variant"], d, ref, ids, None)
            sl["variants"][vid] = {"spec": d["variant"], "fp": d["fp"]["common"], "stress": d["stress"]["common"],
                                   "early": d["fp"]["early"], "by_year": d["fp"]["by_year"], "risk": vm,
                                   "criteria": cr, "refused_orders_fp": d["fp"]["refused_orders"],
                                   "refused_share_fp": d["fp"]["refused_share_of_orders"],
                                   "refused_orders_stress": d["stress"]["refused_orders"],
                                   "refused_share_stress": d["stress"]["refused_share_of_orders"],
                                   "diag_no_refusal_fp": d.get("diag_no_refusal_fp"),
                                   "witness_fp": d.get("witness_fp"), "witness_stress": d.get("witness_stress"),
                                   "censored_fp": d["fp"]["censored"],
                                   "extended_trades_fp": d["fp"].get("extended_trades")}
            c = d["fp"]["common"]
            rows.append({"sleeve": key, "variant": vid, **{f"fp_{k}": v for k, v in c.items() if k != "reasons"},
                         "fp_sharpe_trade": vm["fp"].get("sharpe_trade"), "stress_exp_R": d["stress"]["common"].get("exp_R"),
                         "stress_total_R": d["stress"]["common"].get("total_R"),
                         "stress_sharpe_trade": vm["stress"].get("sharpe_trade"), "fp_bps_trade": vm["fp"].get("bps_trade"),
                         "cost_tol_bp_fp": vm["fp"].get("cost_tol_bp"), "early_exp_R": d["fp"]["early"].get("exp_R"),
                         "early_n": d["fp"]["early"].get("n"),
                         "refused_fp": d["fp"]["refused_orders"], "refused_stress": d["stress"]["refused_orders"],
                         "years_better": cr.get("years_better"), "route": cr.get("route"),
                         **{f"crit_{k}": cr.get(k) for k in "abcde"}, "candidate_a_to_e": cr.get("candidate_a_to_e")})
        ev["sleeves"][key] = sl
    json.dump(ev, open(os.path.join(C.OUT, "evaluation.json"), "w"), indent=1, default=str)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(C.OUT, "variants_table.csv"), index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    cols = ["sleeve", "variant", "fp_n", "fp_exp_R", "fp_total_R", "fp_win_rate", "fp_avg_loss_R", "fp_max_dd_R",
            "fp_sharpe_trade", "stress_exp_R", "stress_sharpe_trade", "fp_bps_trade", "early_exp_R", "years_better",
            "candidate_a_to_e"]
    print(df[cols].round(4).to_string(index=False))


if __name__ == "__main__":
    main()
