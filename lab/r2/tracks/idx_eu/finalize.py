"""Pre-validation dossier for the two finalists of track idx_eu (in-sample only).

Writes results/r2/idx_eu/finalists_preval.json (the decision, BEFORE any validation access) and
results/r2/idx_eu/candidates.json (all in-sample evidence).  Uses only cached trials (no new
configuration), in-sample trades, and -- for the account-constraint line only -- the STOP DISTANCES of
the orders dated 2024-2025 (no result of any 2022+ trade is computed or read).
"""
import datetime as dt
import json
import os

import numpy as np
import pandas as pd

from research import OUT, SYM, S, _load_cache, _key, cut, gl, r2

FINAL = {
    "late_mom_1600": {
        "syms": [SYM],
        "params": {"family": "mom", "times": ("16:00",), "k": 1.5, "stop_k": 0.5, "exit": "17:30"},
        "full_params": {"family": "mom", "times": ["16:00"], "anchor": "17:30", "lb": 20, "k": 1.5, "direction": 1,
                        "stop_k": 0.5, "exit": "17:30", "sides": "both", "tol_min": 5},
        "trial_tag": "S1_M1_mom1600_k1.5",
        "neighbors": ["S2_A02_k1.25", "S2_A03_k1.75", "S3_A18_T1545", "S3_A19_T1615", "S2_A05_T1530", "S2_A06_T1630",
                      "S2_A09_stop0.35", "S2_A10_stop0.75", "S2_A12_exit1725", "S2_A13_exit1735", "S2_A14_lb10",
                      "S2_A15_lb40", "S3_A20_anchor1725", "S3_A21_anchor1735"],
        "wider": ["S2_A01_k1.0", "S2_A04_k2.0", "S2_A07_T1700", "S2_A08_stop0.25", "S2_A11_stop1.0",
                  "S2_A16_grid1600-1700", "S2_A17_grid1500-1700"],
    },
    "close_run_1725": {
        "syms": [SYM],
        "params": {"family": "mom", "times": ("17:25",), "k": 0.5, "stop_k": 0.25, "exit": "17:30"},
        "full_params": {"family": "mom", "times": ["17:25"], "anchor": "17:30", "lb": 20, "k": 0.5, "direction": 1,
                        "stop_k": 0.25, "exit": "17:30", "sides": "both", "tol_min": 5},
        "trial_tag": "S4_C7_T1725_k0.5",
        "neighbors": ["S5_N01_T1723", "S5_N02_T1727", "S4_C5_T1720_k0.5", "S5_N03_k0.25", "S5_N04_k0.75",
                      "S5_N07_stop0.15", "S5_N08_stop0.35", "S5_N09_exit1729", "S5_N10_exit1731", "S5_N11_exit1735",
                      "S5_N12_lb10", "S5_N13_lb40", "S5_N14_anchor1725", "S5_N15_anchor1735"],
        "wider": ["S5_N05_k0", "S5_N06_k1.0", "S4_C2_T1715_k0.5", "S4_C3_T1715_k1.0"],
    },
}
SPLIT = pd.Timestamp("2018-01-01", tz="UTC")


def _tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 else float("nan")


def _bps(t):
    return float((t.pnl / t.entry).mean() * 1e4) if len(t) else float("nan")


def dossier(name, f, cache_by_tag, nulls):
    p = f["params"]
    row = cache_by_tag[f["trial_tag"]]
    assert row["key"] == _key(SYM, p), "finalist params must equal the logged trial"
    ev = row["ev"]
    nb = {t: cache_by_tag[t]["ev"]["is"]["pf"] for t in f["neighbors"]}
    med = float(np.median(list(nb.values())))
    crit = r2.is_criteria(ev, neighbor_median_pf=med)
    nul = nulls.get(f["trial_tag"])
    # trade-level in-sample diagnostics (same configuration, IS only)
    m1 = r2.load(SYM)
    t_net = cut(r2.run(SYM, S.make_orders, p, "fp", m1=m1), "is")
    t_gross = cut(r2.run(SYM, S.make_orders, p, "gross", m1=m1), "is")
    h1g, h2g = t_gross[t_gross.entry_time < SPLIT], t_gross[t_gross.entry_time >= SPLIT]
    h1n, h2n = t_net[t_net.entry_time < SPLIT], t_net[t_net.entry_time >= SPLIT]
    lg, sh = t_net[t_net.side > 0], t_net[t_net.side < 0]
    R = t_net.R.to_numpy()
    srt = np.sort(R)
    # account constraint: stop distance of the orders dated 2024-2025 (orders only, no trade result)
    o = S.make_orders(m1, **p)
    et = m1.index[o["entry_i"].to_numpy()]
    m = (et >= pd.Timestamp("2024-01-01", tz="UTC")) & (et < pd.Timestamp("2026-01-01", tz="UTC"))
    sd = o["stop_dist"].to_numpy()[m]
    px = ((m1["bo"].to_numpy() + m1["ao"].to_numpy()) / 2)[o["entry_i"].to_numpy()[m]]
    spec = r2.SPEC[SYM]
    med_stop = float(np.median(sd))
    # "historical" cost model for information: raw Dukascopy bid/ask, in-sample only
    raw = gl.load_m1(SYM, end="2022-01-01")
    t_hist = cut(r2.run(SYM, S.make_orders, p, "fp", m1=raw), "is")
    rep_hist = gl.report(t_hist)
    t_net.assign(entry_berlin=t_net.entry_time.dt.tz_convert("Europe/Berlin").dt.strftime("%Y-%m-%d %H:%M")) \
        [["entry_berlin", "side", "entry", "exit", "stop", "reason", "pnl", "R", "hold_min", "z"]] \
        .to_csv(os.path.join(OUT, f"trades_is_{name}.csv"), index=False)
    cost_bps = ev["is_gross_bps_per_trade"] - ev["is_bps_per_trade"]
    return {
        "name": name, "syms": f["syms"], "params": f["full_params"], "trial_tag": f["trial_tag"],
        "is": ev["is"], "is_bps_per_trade": ev["is_bps_per_trade"], "is_gross_bps_per_trade": ev["is_gross_bps_per_trade"],
        "is_cost_bps_per_trade": round(cost_bps, 2),
        "gross_over_cost": round(ev["is_gross_bps_per_trade"] / cost_bps, 2),
        "is_stress": ev["is_stress"], "is_gross": ev["is_gross"], "is_every_signal": ev["is_every_signal"],
        "neighbors_pf": nb, "neighbor_median_pf": round(med, 3),
        "wider_variants_pf": {t: cache_by_tag[t]["ev"]["is"]["pf"] for t in f["wider"]},
        "is_criteria": crit, "null_test": nul,
        "long": {"n": int(len(lg)), "mean_R": round(float(lg.R.mean()), 4), "sum_R": round(float(lg.R.sum()), 1), "t": round(_tstat(lg.R), 2),
                 "bps": round(_bps(lg), 2)},
        "short": {"n": int(len(sh)), "mean_R": round(float(sh.R.mean()), 4), "sum_R": round(float(sh.R.sum()), 1), "t": round(_tstat(sh.R), 2),
                  "bps": round(_bps(sh), 2)},
        "halves": {"split": "2018-01-01",
                   "first": {"n": int(len(h1g)), "gross_bps": round(_bps(h1g), 2), "net_bps": round(_bps(h1n), 2),
                             "net_mean_R": round(float(h1n.R.mean()), 4), "net_t": round(_tstat(h1n.R), 2)},
                   "second": {"n": int(len(h2g)), "gross_bps": round(_bps(h2g), 2), "net_bps": round(_bps(h2n), 2),
                              "net_mean_R": round(float(h2n.R.mean()), 4), "net_t": round(_tstat(h2n.R), 2)}},
        "tail": {"sd_R": round(float(R.std(ddof=1)), 3), "max_R": round(float(srt[-1]), 2),
                 "top10_sum_R": round(float(srt[-10:].sum()), 1), "total_R": round(float(R.sum()), 1),
                 "mean_R_without_top10": round(float(srt[:-10].mean()), 4), "t_without_top10": round(_tstat(srt[:-10]), 2),
                 "median_R": round(float(np.median(R)), 3)},
        "exit_reasons": t_net.reason.value_counts().to_dict(),
        "stop_2024_25": {"n_orders": int(m.sum()), "median_stop_points": round(med_stop, 1),
                         "median_stop_bps": round(float(np.median(sd / px) * 1e4), 1),
                         "min_lot": spec["min_lot"], "min_lot_stop_money_eur": round(med_stop * spec["units_per_lot"] * spec["min_lot"], 2),
                         "median_price": round(float(np.median(px)), 0)},
        "historical_cost_model_is": {k: rep_hist[k] for k in ("n", "pf", "expectancy_R", "t_stat", "years_pos", "long_R", "short_R")}
        | {"bps_per_trade": round(_bps(t_hist), 2)},
    }


def main():
    cache = _load_cache()
    by_tag = {r["tag"]: r for r in cache.values()}
    nulls = {}
    for line in open(os.path.join(OUT, "null_tests.jsonl")):
        r = json.loads(line)
        nulls[r["name"]] = {k: r[k] for k in ("n", "mode", "rule_mean_R", "null_mean_R", "null_p95_R", "null_max_R", "percentile", "pass")}
    out = {"track": "idx_eu", "n_trials_logged": len(cache), "finalists": {}}
    for name, f in FINAL.items():
        d = dossier(name, f, by_tag, nulls)
        out["finalists"][name] = d
        i = d["is"]
        print(f"\n== {name}: n={i['n']} /yr={i['trades_per_year']} PF={i['pf']} t={i['t_stat']} expR={i['expectancy_R']} yrs={i['years_pos']} dd={i['max_dd_R']}")
        print("   criteria:", d["is_criteria"])
        print("   neighbors median PF:", d["neighbor_median_pf"], "| null:", d["null_test"])
        print("   long:", d["long"], "| short:", d["short"])
        print("   halves:", d["halves"])
        print("   tail:", d["tail"], "| exits:", d["exit_reasons"])
        print("   stop 2024-25:", d["stop_2024_25"])
        print("   gross/cost:", d["is_gross_bps_per_trade"], "/", d["is_cost_bps_per_trade"], "=", d["gross_over_cost"], "| historical-cost IS:", d["historical_cost_model_is"])
        print("   by year R:", i.get("by_year_R"))
    json.dump(out, open(os.path.join(OUT, "candidates.json"), "w"), indent=1, default=str)
    pre = os.path.join(OUT, "finalists_preval.json")
    if not os.path.exists(pre):
        json.dump({"decided_utc": dt.datetime.utcnow().isoformat(timespec="seconds"), "track": "idx_eu",
                   "n_trials_at_decision": len(cache), "validation_accessed_before_decision": False,
                   "finalists": {n: {"syms": d["syms"], "params": d["params"], "trial_tag": d["trial_tag"],
                                     "is": {k: d["is"][k] for k in ("n", "trades_per_year", "pf", "t_stat", "expectancy_R", "years_pos", "max_dd_R", "long_R", "short_R")},
                                     "is_criteria": d["is_criteria"], "neighbor_median_pf": d["neighbor_median_pf"],
                                     "null_percentile": d["null_test"]["percentile"]} for n, d in out["finalists"].items()},
                   "not_selected": "morning gap momentum (S3_B09 / S2_B03) passes the IS thresholds but is long-skewed and "
                                   "fat-tail dependent; kept out, validation data untouched for it."},
                  open(pre, "w"), indent=1, default=str)
        print("\nwrote", pre)
    else:
        print("\n", pre, "already exists (not rewritten)")


if __name__ == "__main__":
    main()
