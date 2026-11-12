"""Runs the 11 configurations declared in results/r2/round4/letf_close_pair/declared.json, IN SAMPLE ONLY, once.
Writes, under results/r2/round4/letf_close_pair/:
  trials.jsonl                 one line per configuration (11), losing ones included
  trades_<id>_<name>.parquet   the trades of configurations 1-10 (FP costs; 10 = costs x1.5)
  gross_main.parquet           the main's trades on mid prices without slippage (reported, not judged)
  signals_main.parquet         every session's d, sd_d, condition, hedge, sd_pi of the main
  configs.json                 full reports;  null.json  the 200 replays of configuration 11

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
        "max_dd_R", "years_pos", "by_year_R", "by_year_n", "by_year_pf", "by_year_net_bp", "weeks_pos_pct",
        "worst_week_R", "long_n", "long_R", "short_n", "short_R", "avg_hold_h", "max_hold_h", "exit_reasons",
        "net_bp_per_pair", "mid_bp_per_pair_same_exits", "cost_bp_per_pair", "gross_n", "gross_bp_per_pair", "gross_pf",
        "gross_expectancy_R", "gross_t", "money_expectancy_R", "money_pf", "sd_pi_bp_median", "h_median", "stop_share",
        "by_direction", "first_entry", "last_entry")


def null_test(P, cal, t, n_seeds=200, seed=0, e=30, x=59, k=1.5):
    """Configuration 11 (declared.json R15): the main's pairs replayed at 15:30 on random sessions of the list."""
    L2 = C.LEG["us30"]
    rows_all = cal["srow"]
    have = (np.isfinite(P["bo"][0][rows_all, e]) & np.isfinite(P["ao"][0][rows_all, e])
            & np.isfinite(P["bo"][L2][rows_all, e]) & np.isfinite(P["ao"][L2][rows_all, e]))
    pool = rows_all[have]
    dirs, h, sdpi = t.dir.to_numpy(float), t.h.to_numpy(float), t.sd_pi.to_numpy(float)
    rng = np.random.default_rng(seed)
    means, stops = [], []
    for _ in range(n_seeds):
        rr = pool[rng.integers(0, len(pool), len(t))]
        res = C.sim_pairs(P, rr, L2, dirs, h, sdpi, e, x, k)
        assert res["filled"].all()
        R = res["net"] / (k * sdpi)
        means.append(float(R.mean()))
        stops.append(float(res["stopped"].mean()))
    means = np.array(means)
    cand = float(t.R.mean())
    pct = float((means < cand).mean() * 100)
    return {"n_trades": int(len(t)), "n_seeds": n_seeds, "seed": seed, "pool_sessions": int(len(pool)),
            "rule_mean_R": round(cand, 5), "null_mean_R": round(float(means.mean()), 5),
            "null_sd_of_means": round(float(means.std(ddof=1)), 5), "null_p50_R": round(float(np.percentile(means, 50)), 5),
            "null_p95_R": round(float(np.percentile(means, 95)), 5), "null_p975_R": round(float(np.percentile(means, 97.5)), 5),
            "null_max_R": round(float(means.max()), 5), "null_stop_share_mean": round(float(np.mean(stops)), 3),
            "percentile": round(pct, 1), "pass": bool(pct >= 97.5), "means": [round(float(v), 5) for v in means]}


def main():
    decl = json.load(open(os.path.join(C.OUT, "declared.json")))
    dc = json.load(open(os.path.join(C.OUT, "data_check.json")))
    drop6 = bool(dc["R19_drop_rule_of_6"]["config_6_dropped"])
    cfgs = decl["configurations"]
    trials_path = os.path.join(C.OUT, "trials.jsonl")
    assert not os.path.exists(trials_path), "trials.jsonl exists: the declared configurations are run once"
    t_start = time.time()
    cal = C.calendar()
    fr = C.load_frames(1.0)
    P1 = C.prepare(C.build_grid(fr, cal["tdays"]))
    del fr
    fr = C.load_frames(1.5)
    P15 = C.prepare(C.build_grid(fr, cal["tdays"]))
    del fr
    now = lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    reports, main_t = {}, None
    with open(trials_path, "a") as ftr:
        for c in cfgs:
            p = c["params"]
            if c["id"] == 11:
                continue
            if c["id"] == 6 and drop6:
                row = {"id": 6, "name": c["name"], "params": p, "dropped": True, "why": "R19 (data_check.json)",
                       "written_utc": now()}
                ftr.write(json.dumps(row) + "\n")
                continue
            cm = p["cost_mult"]
            P = P15 if cm != 1.0 else P1
            # signals on mid prices (R13: the widening keeps the mid, so the stress run sees the main's signals)
            sg = C.signals(P1, cal, **p)
            t, counts = C.run_config(P, sg, p, C.SLIP_M * cm, C.SLIP_S * cm, "net")
            tg, _ = C.run_config(P1, sg, p, mode="mid")
            rep = C.summarize(t, tg)
            if len(t):
                fbk = t.exit_fallback.to_numpy()
                counts["exit_fallback_by_year"] = {int(y): int(v) for y, v in
                                                   pd.Series(fbk).groupby(t.entry_time.dt.year.to_numpy()).sum().items()}
            if c["id"] == 1:
                main_t = t
                tg.to_parquet(os.path.join(C.OUT, "gross_main.parquet"))
                sig = pd.DataFrame({"date": cal["sessions"], "row": sg["rows"], "prev_was_early_close": cal["prev_half"],
                                    "d_us100": sg["d100"], "d_us30": sg["d2"], "sd_d": sg["sd_d"],
                                    "ret_us100": sg["ret"][0], "ret_us30": sg["ret"][1], "sd_us100": sg["sdA"],
                                    "sd_us30": sg["sdB"], "h": sg["h"], "dir": sg["dir"], "pi_mid": sg["pi"],
                                    "sd_pi": sg["sdpi"], "cond": sg["cond"], "take": sg["take"]})
                sig.to_parquet(os.path.join(C.OUT, "signals_main.parquet"))
            if c["id"] == 10:      # information: signals recomputed on the widened frames (mid equal to ~1e-12)
                s15 = C.signals(P15, cal, **p)
                counts["signals_differing_if_built_on_widened_frames"] = int((s15["take"] != sg["take"]).sum())
            t.to_parquet(os.path.join(C.OUT, f"trades_{c['id']:02d}_{c['name']}.parquet"))
            row = {"id": c["id"], "name": c["name"], "params": p, "counts": counts,
                   "is": {kk: rep.get(kk) for kk in KEEP},
                   "period": "IS sessions 2013-09-30..2021-12-31 (entries), frames ts < 2022-01-01",
                   "costs": f"FP frames, slippage market {0.2 * cm:.2f} bp / stop {0.5 * cm:.2f} bp per leg"
                            + (", spreads x1.5" if cm != 1.0 else ""),
                   "written_utc": now()}
            ftr.write(json.dumps(row, default=str) + "\n")
            ftr.flush()
            reports[c["name"]] = {"params": p, "counts": counts, "report": rep}
            print(f"[{c['id']:2d}] {c['name']:<14} n={rep.get('n')} PF={rep.get('pf')} t={rep.get('t_stat')} "
                  f"expR={rep.get('expectancy_R')} yrs+={rep.get('years_pos')} net={rep.get('net_bp_per_pair')}bp "
                  f"gross={rep.get('gross_bp_per_pair')}bp cost={rep.get('cost_bp_per_pair')}bp "
                  f"stops={rep.get('stop_share')} | {counts}", flush=True)
        c11 = [c for c in cfgs if c["id"] == 11][0]
        nul = null_test(P1, cal, main_t, c11["params"]["n_seeds"], c11["params"]["seed"])
        row = {"id": 11, "name": c11["name"], "params": c11["params"],
               "null": {kk: v for kk, v in nul.items() if kk != "means"}, "written_utc": now()}
        ftr.write(json.dumps(row, default=str) + "\n")
    C.jdump(nul, os.path.join(C.OUT, "null.json"))
    reports["null_200"] = {kk: v for kk, v in nul.items() if kk != "means"}
    C.jdump(reports, os.path.join(C.OUT, "configs.json"))
    print("[11] null:", {kk: v for kk, v in nul.items() if kk != "means"})
    print(f"done in {time.time() - t_start:.0f}s")


if __name__ == "__main__":
    main()
