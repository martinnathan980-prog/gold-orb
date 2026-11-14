"""Attack run: my own implementation of Addendum K's seven configurations, in sample only (2013-2021).

For each configuration: FP costs and costs x1.5 (spread x1.5 around the mid, slippage x1.5; the swap is zero because
no 17:00 New York rollover is crossed, asserted); for the main also the gross run (mid quotes, no cost). Then the
every-signal check, my own random-time null (two duration conventions), my own weekly correlation with the sum of
the ten, the PROTOCOL_V2 section 4 criteria and sensitivities to the open readings (same configurations, other
readings; none is a new configuration and none could be selected).
Every evaluated run is logged in results/r2/round5/gold_reopen/attack/attack_trials.jsonl (the engineer's
trials.jsonl is not touched).
Outputs: results/r2/round5/gold_reopen/attack/ (attack_results.json, trades_*.parquet, sessions_main.parquet,
null_means_*.npy).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acommon as A  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

TRIALS = os.path.join(A.OUT, "attack_trials.jsonl")


def log(label, cfg, scen, reading, m, note=""):
    with open(TRIALS, "a") as f:
        f.write(json.dumps({"label": label, "config": cfg, "costs": scen, "holiday_reading": reading, "note": note,
                            "n": m["n"], "pf": m["pf"], "t": m["t"], "expectancy_R": m["expectancy_R"],
                            "total_R": m["total_R"], "years_pos": m["years_pos"]}, default=str) + "\n")


def save(t, name):
    keep = ["evening", "entry_time", "exit_time", "entry", "stop", "exit", "reason", "risk", "pnl", "R", "swap",
            "hold_min", "entry_delay_min", "exit_delay_min", "mean_h1_range", "stop_dist", "last_h1_start",
            "t_entry_target", "t_exit_target", "entry_i", "exit_i", "exit_i_sched"]
    t[keep].to_parquet(os.path.join(A.OUT, f"trades_{name}.parquet"))


def criteria(m, ms, nb_pfs, every_exp, null_pct, rho):
    yp, yn = (int(x) for x in m["years_pos"].split("/"))
    med = float(np.median(nb_pfs))
    return {
        "n>=250": {"value": m["n"], "pass": m["n"] >= 250},
        "pf>=1.12": {"value": m["pf"], "pass": m["pf"] >= 1.12},
        "t>=2.5": {"value": m["t"], "pass": m["t"] >= 2.5},
        "years_pos>=60%": {"value": m["years_pos"], "pass": yp >= 0.6 * yn},
        "stress_pf>=1.04": {"value": ms["pf"], "pass": ms["pf"] >= 1.04},
        "neighbours_median_pf>=1.06": {"value": round(med, 4), "pass": med >= 1.06},
        "every_signal_exp>0": {"value": every_exp, "pass": every_exp > 0},
        "max_hold<=5_trading_days": {"value_min": m["max_hold_min"], "pass": m["max_hold_min"] <= 5 * 24 * 60},
        "null>=97.5pct": {"value": null_pct, "pass": null_pct >= 97.5},
        "abs_weekly_corr_with_ten<=0.30": {"value": rho, "pass": abs(rho) <= 0.30},
    }


def main():
    assert not os.path.exists(TRIALS), "attack_trials.jsonl exists: the attack run is done once"
    df = A.load_is()
    cache = {}
    cache["fp"] = A.Frame(df, 1.0)
    h1 = A.H1(cache["fp"])
    cal = A.gold_calendar()
    res = {"what": "attack (independent re-implementation) of PROTOCOL_V3 Addendum K, in sample 2013-2021",
           "frame": {"rows": int(len(df)), "first": str(df.index[0]), "last": str(df.index[-1])},
           "configs": {}}
    trades = {}
    for cfg in A.CONFIGS:
        row = {}
        for scen in ("fp", "x1.5"):
            t, S = A.run_config(df, cfg, cal, scen, fr_cache=cache, h1=h1)
            assert (t.last_h1_start + pd.Timedelta(hours=1) <= t.entry_time).all(), "an H1 bar not completed at the entry"
            m = A.metrics(t)
            row[scen] = m
            log(cfg["name"], cfg, scen, "union", m)
            trades[(cfg["name"], scen)] = t
            if scen == "fp":
                save(t, f"{cfg['id']:02d}_{cfg['name']}")
                if cfg["id"] == 1:
                    S.to_parquet(os.path.join(A.OUT, "sessions_main.parquet"))
                    row["sessions_by_status"] = {k: int(v) for k, v in S.status.value_counts().items()}
        if cfg["id"] == 1:
            save(trades[("main", "x1.5")], "01_main_costs_x1.5")
            tg, _ = A.run_config(df, cfg, cal, "gross", fr_cache=cache, h1=h1)
            save(tg, "01_main_gross")
            mg = A.metrics(tg)
            log("main", cfg, "gross", "union", mg)
            row["gross"] = mg
            row["gross_bp_mean"] = round(float((tg.pnl / tg.entry).mean() * 1e4), 3)
        res["configs"][cfg["name"]] = row
        print(cfg["name"], {s: (row[s]["n"], row[s]["pf"], row[s]["t"], row[s]["expectancy_R"]) for s in ("fp", "x1.5")}, flush=True)
    t1 = trades[("main", "fp")]
    # every signal: one order per session; no trade may overlap the next
    res["every_signal"] = {"overlapping_trades": A.overlaps(t1), "n": int(len(t1)),
                           "expectancy_R": res["configs"]["main"]["fp"]["expectancy_R"],
                           "note": "one order per session, sessions about a day apart, holds at most about 2.5 h: no order "
                                   "is ever skipped by 'one position at a time', so every signal = the main, trade for trade"}
    assert res["every_signal"]["overlapping_trades"] == 0
    # null (FP costs), two duration conventions
    fr = cache["fp"]
    nl_c, means_c = A.null_random_time(fr, t1, 200, 20261114, "clock", 120)
    nl_b, means_b = A.null_random_time(fr, t1, 200, 20261114, "bars", 120)
    np.save(os.path.join(A.OUT, "null_means_clock.npy"), means_c)
    np.save(os.path.join(A.OUT, "null_means_bars.npy"), means_b)
    res["null_clock"] = nl_c
    res["null_bars"] = nl_b
    print("null clock", nl_c, flush=True)
    print("null bars", nl_b, flush=True)
    # correlation
    cor = A.corr_with_ten(t1)
    res["correlation"] = cor
    print("corr", cor["rho"], cor["weeks_with_an_exit"], flush=True)
    # criteria on the main
    nb = [res["configs"][c["name"]]["fp"]["pf"] for c in A.CONFIGS[1:]]
    res["neighbours_pf"] = {c["name"]: res["configs"][c["name"]]["fp"]["pf"] for c in A.CONFIGS[1:]}
    res["neighbours_median_pf"] = round(float(np.median(nb)), 4)
    res["criteria"] = criteria(res["configs"]["main"]["fp"], res["configs"]["main"]["x1.5"], nb,
                               res["every_signal"]["expectancy_R"], min(nl_c["percentile"], 100.0), cor["rho"])
    res["criteria_null_bars_variant"] = {"value": nl_b["percentile"], "pass": nl_b["percentile"] >= 97.5}
    res["main_pass"] = bool(all(v["pass"] for v in res["criteria"].values()))
    # sensitivities: other readings of the open details, main at FP costs (and the 18:10 window)
    sens = {}
    main = A.CONFIGS[0]
    for reading in ("session", "evening"):
        t, _ = A.run_config(df, main, cal, "fp", reading=reading, fr_cache=cache, h1=h1)
        m = A.metrics(t)
        sens[f"holiday_reading_{reading}_only"] = m
        log("main", main, "fp", reading, m, "attack sensitivity, same configuration")
    cal_cb = dict(cal)
    for d in ("2013-10-14", "2014-10-13"):
        cal_cb[pd.Timestamp(d).date()] = ("early", "columbus_day_halt_seen_in_frame")
    t, _ = A.run_config(df, main, cal_cb, "fp", fr_cache=cache, h1=h1)
    m = A.metrics(t)
    sens["calendar_plus_columbus_2013_2014_halts"] = m
    log("main", main, "fp", "union+columbus", m, "attack sensitivity, same configuration")
    cal_j = dict(cal)
    cal_j.pop(pd.Timestamp("2019-07-04").date())
    t, _ = A.run_config(df, main, cal_j, "fp", fr_cache=cache, h1=h1)
    m = A.metrics(t)
    sens["calendar_without_2019_07_04_normal_in_frame"] = m
    log("main", main, "fp", "union-2019-07-04", m, "attack sensitivity, same configuration")
    cal_n = dict(cal)
    for y in range(2013, 2022):
        d = pd.Timestamp(f"{y}-07-03").date()
        if d.weekday() < 5 and d not in cal_n:
            cal_n[d] = ("early", "nyse_july_3_half_day")
    t, _ = A.run_config(df, main, cal_n, "fp", fr_cache=cache, h1=h1)
    m = A.metrics(t)
    sens["calendar_plus_nyse_july_3_half_days"] = m
    log("main", main, "fp", "union+july3", m, "attack sensitivity, same configuration")
    t, _ = A.run_config(df, main, cal, "fp", range_kind="bid", fr_cache=cache, h1=h1)
    m = A.metrics(t)
    sens["h1_range_on_bid_quotes"] = m
    log("main", main, "fp", "union", m, "attack sensitivity: H1 range on bid quotes (MetaTrader chart)")
    t, _ = A.run_config(df, A.CONFIGS[1], cal, "fp", quote_end="18:15", fr_cache=cache, h1=h1)
    m = A.metrics(t)
    sens["n_entry_1810_with_quote_window_1800_1815"] = m
    log("n_entry_1810", A.CONFIGS[1], "fp", "union", m, "attack sensitivity: quote window [18:00, 18:15)")
    res["sensitivities"] = sens
    for k, v in sens.items():
        print(k, v["n"], v["pf"], v["t"], v["expectancy_R"], v["years_pos"], flush=True)
    A.jdump(res, os.path.join(A.OUT, "attack_results.json"))
    print(json.dumps({k: v for k, v in res["criteria"].items()}, default=str))


if __name__ == "__main__":
    main()
