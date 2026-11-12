"""Runs the 12 configurations declared in results/r2/round4/idxrs_1000/declared.json, IN SAMPLE ONLY, once.
Writes, under results/r2/round4/idxrs_1000/:
  trials.jsonl                 one line per configuration (12), losing ones included
  trades_<id>_<name>.parquet   the trades of configurations 1-11 (FP costs; 11 = costs x1.5)
  gross_main.parquet           the main's trades on mid prices without slippage (reported, not judged)
  signals_main.parquet         every session's ranking / threshold / hedge / sd_pi of the main
  configs.json                 full reports;  null.json  the 200 replays of configuration 12

    PYTHONDONTWRITEBYTECODE=1 NUMBA_CACHE_DIR=/tmp/... python3 run.py
"""
import datetime as dt
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

KEEP = ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "t_stat", "pf", "total_R",
        "max_dd_R", "years_pos", "by_year_R", "by_year_n", "weeks_pos_pct", "worst_week_R", "long_n", "long_R", "short_n",
        "short_R", "avg_hold_h", "max_hold_h", "exit_reasons", "net_bp_per_pair", "mid_bp_per_pair_same_exits",
        "cost_bp_per_pair", "gross_bp_per_pair", "gross_pf", "gross_expectancy_R", "money_expectancy_R", "money_pf",
        "sd_pi_bp_median", "h_median", "stop_share", "by_pair_type", "by_side_of_us100")


def null_test(P, t, n_seeds=200, seed=0, e=30, x=385, k=1.5):
    """Configuration 12 (declared.json R14): the main's pairs replayed at 10:00 on random in-sample sessions."""
    ix = {s: i for i, s in enumerate(C.SYMS)}
    S = t.S.map(ix).to_numpy(np.int64)
    W = t.W.map(ix).to_numpy(np.int64)
    h, sdpi = t.h.to_numpy(float), t.sd_pi.to_numpy(float)
    have = np.isfinite(P["bo"][:, :, e]) & np.isfinite(P["ao"][:, :, e])
    groups = {}
    for j, ab in enumerate(zip(S, W)):
        groups.setdefault(ab, []).append(j)
    elig = {ab: np.flatnonzero(have[ab[0]] & have[ab[1]]) for ab in groups}
    rng = np.random.default_rng(seed)
    means, stops = [], []
    for _ in range(n_seeds):
        dd = np.empty(len(t), np.int64)
        for ab, js in groups.items():
            dd[js] = elig[ab][rng.integers(0, len(elig[ab]), len(js))]
        res = C.sim_pairs(P, dd, S, W, h, sdpi, e, x, k)
        assert res["filled"].all()
        R = res["net"] / (k * sdpi)
        means.append(float(R.mean()))
        stops.append(float(res["stopped"].mean()))
    means = np.array(means)
    cand = float(t.R.mean())
    pct = float((means < cand).mean() * 100)
    return {"n_trades": int(len(t)), "n_seeds": n_seeds, "seed": seed, "rule_mean_R": round(cand, 5),
            "null_mean_R": round(float(means.mean()), 5), "null_sd_of_means": round(float(means.std(ddof=1)), 5),
            "null_p50_R": round(float(np.percentile(means, 50)), 5), "null_p95_R": round(float(np.percentile(means, 95)), 5),
            "null_p975_R": round(float(np.percentile(means, 97.5)), 5), "null_max_R": round(float(means.max()), 5),
            "null_stop_share_mean": round(float(np.mean(stops)), 3), "percentile": round(pct, 1), "pass": bool(pct >= 97.5),
            "eligible_sessions": {f"{C.SYMS[a]}>{C.SYMS[b]}": int(len(v)) for (a, b), v in elig.items()},
            "means": [round(float(v), 5) for v in means]}


def main():
    decl = json.load(open(os.path.join(C.OUT, "declared.json")))
    cfgs = decl["configurations"]
    trials_path = os.path.join(C.OUT, "trials.jsonl")
    assert not os.path.exists(trials_path), "trials.jsonl exists: the declared configurations are run once"
    t_start = time.time()
    days = C.sessions()
    fr = C.load_frames(1.0)
    P1 = C.prepare(C.build_grid(fr, days))
    del fr
    fr = C.load_frames(1.5)
    P15 = C.prepare(C.build_grid(fr, days))
    del fr
    reports, main_t, main_sg = {}, None, None
    with open(trials_path, "a") as ftr:
        for c in cfgs:
            p = c["params"]
            if c["id"] == 12:
                continue
            cm = p["cost_mult"]
            P = P15 if cm != 1.0 else P1
            # signals on mid prices (R12: the widening keeps the mid, so the stress run sees the main's signals)
            sg = C.signals(P1, p["entry_min"], p["exit_min"], p["q"], p["win"], p["minv"])
            t, counts = C.run_config(P, sg, p["k"], C.SLIP_M * cm, C.SLIP_S * cm, "net")
            tg, _ = C.run_config(P1, sg, p["k"], mode="mid")
            rep = C.summarize(t, tg)
            if c["id"] == 1:
                main_t, main_sg = t, sg
                tg.to_parquet(os.path.join(C.OUT, "gross_main.parquet"))
                sig = pd.DataFrame({"date": days, "ranked": sg["ok"], "S": [C.SYMS[i] for i in sg["S"]],
                                    "W": [C.SYMS[i] for i in sg["W"]], "r_us100": sg["r"][:, 0], "r_us500": sg["r"][:, 1],
                                    "r_us30": sg["r"][:, 2], "D": sg["D"], "Q": sg["Q"], "h": sg["h"], "sd_pi": sg["sdpi"],
                                    "pi_mid": sg["pi"], "take": sg["take"]})
                sig.to_parquet(os.path.join(C.OUT, "signals_main.parquet"))
            if c["id"] == 11:      # information: signals recomputed on the widened frames (mid equal to ~1e-12)
                s15 = C.signals(P15, p["entry_min"], p["exit_min"], p["q"], p["win"], p["minv"])
                counts["signals_differing_if_built_on_widened_frames"] = int((s15["take"] != sg["take"]).sum())
            t.to_parquet(os.path.join(C.OUT, f"trades_{c['id']:02d}_{c['name']}.parquet"))
            row = {"id": c["id"], "name": c["name"], "params": p, "counts": counts,
                   "is": {kk: rep.get(kk) for kk in KEEP}, "period": "IS sessions 2013-09-30..2021-12-31 (entries)",
                   "written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
            ftr.write(json.dumps(row, default=str) + "\n")
            ftr.flush()
            reports[c["name"]] = {"params": p, "counts": counts, "report": rep}
            print(f"[{c['id']:2d}] {c['name']:<14} n={rep.get('n')} PF={rep.get('pf')} t={rep.get('t_stat')} "
                  f"expR={rep.get('expectancy_R')} yrs+={rep.get('years_pos')} net={rep.get('net_bp_per_pair')}bp "
                  f"gross={rep.get('gross_bp_per_pair')}bp cost={rep.get('cost_bp_per_pair')}bp stops={rep.get('stop_share')} "
                  f"| {counts}", flush=True)
        c12 = [c for c in cfgs if c["id"] == 12][0]
        nul = null_test(P1, main_t, c12["params"]["n_seeds"], c12["params"]["seed"])
        row = {"id": 12, "name": c12["name"], "params": c12["params"],
               "null": {kk: v for kk, v in nul.items() if kk != "means"},
               "written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        ftr.write(json.dumps(row, default=str) + "\n")
    C.jdump(nul, os.path.join(C.OUT, "null.json"))
    reports["null_200"] = {kk: v for kk, v in nul.items() if kk != "means"}
    C.jdump(reports, os.path.join(C.OUT, "configs.json"))
    print("[12] null:", {kk: v for kk, v in nul.items() if kk not in ("means", "eligible_sessions")})
    print(f"done in {time.time() - t_start:.0f}s")


if __name__ == "__main__":
    main()
