"""Configurations 1-10 of declared.json (main, 8 neighbours, main at costs x1.5).  IN SAMPLE ONLY.

Everything is computed in memory first; then trials.jsonl is written (lines 1-10, one per configuration, losing ones
included), with the trades of every configuration (trades_NN_<name>.parquet), the orders of the main configuration and
its gross and every-signal runs (information / criterion of config 1).  Configuration 11 (null) is null.py.

    PYTHONDONTWRITEBYTECODE=1 python3 run.py
"""
import json
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import xetra as X  # noqa: E402

KEEP = ("n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "t_stat", "pf", "total_R",
        "max_dd_R", "years_pos", "weeks_pos_pct", "weeks_neg_pct", "months_pos_pct", "worst_week_R", "long_n", "long_R",
        "short_n", "short_R", "avg_hold_h", "max_hold_h", "pf_ret", "by_year_R", "by_year_n", "exit_reasons",
        "bps_per_trade", "swap_total")


def js(x):
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return str(x)


def short(r):
    return {k: r.get(k) for k in KEEP if k in r}


def main():
    decl = json.load(open(os.path.join(X.RES, "declared.json")))
    tpath = os.path.join(X.RES, "trials.jsonl")
    assert not os.path.exists(tpath), "trials.jsonl exists: the declared configurations are run once"
    m1 = X.load_is()
    lines, files = [], {}
    for c in decl["configurations"]:
        if c["role"] == "null":
            continue
        t0 = time.time()
        mode = "fp" if c["costs"] == "fp" else "stress"
        t, o, info = X.run(m1, c["params"], mode)
        rep = X.summary(t)
        line = {"id": c["id"], "name": c["name"], "role": c["role"], "params": c["params"], "costs": c["costs"],
                "checks_berlin": c["checks_berlin"],
                "period": "sessions 2014-01-01 .. 2021-12-31 (entries < 2022-01-01); frame read with ts < 2022-01-01",
                **info, "result": short(rep)}
        if c["id"] == 1:
            te = X.simulate_filtered(m1, o, X.mode_costs("fp"), min_spreads=3.0, no_overlap=False)
            te = te[te.entry_time >= pd.Timestamp(X.TRADE_START, tz="UTC")]
            re_ = X.summary(te)
            line["every_signal"] = {k: re_.get(k) for k in ("n", "pf", "expectancy_R", "t_stat", "total_R")}
            line["every_signal_identical_trades"] = bool(len(te) == len(t) and np.array_equal(
                te.entry_time.to_numpy(), t.entry_time.to_numpy()) and np.allclose(te.R.to_numpy(), t.R.to_numpy()))
            tg, _, ig = X.run(m1, c["params"], "gross")
            rg = X.summary(tg)
            line["gross_information"] = {k: rg.get(k) for k in ("n", "pf", "expectancy_R", "t_stat", "total_R",
                                                                 "bps_per_trade", "by_year_R", "long_R", "short_R")}
            files["gross_01_main.parquet"] = tg
            files["orders_01_main.parquet"] = o
            # cost per round trip actually paid (bp of entry): gross minus net, same orders
            line["cost_bp_per_trade_net_vs_gross"] = round(float(rg["bps_per_trade"] - rep["bps_per_trade"]), 3)
            assert float(t["swap"].abs().sum()) == 0.0, "a swap was charged"
            spr = (m1["ao"] - m1["bo"]).to_numpy()[m1.index.searchsorted(t.entry_time)]
            line["min_stop_in_spreads"] = round(float((t["risk"].to_numpy() / spr).min()), 1)
            line["median_stop_bp"] = round(float((t["risk"] / t["entry"]).median() * 1e4), 1)
        line["sec"] = round(time.time() - t0, 1)
        lines.append(line)
        files[f"trades_{c['id']:02d}_{c['name']}.parquet"] = t
        print(c["id"], c["name"], c["costs"], {k: rep.get(k) for k in ("n", "pf", "t_stat", "expectancy_R", "total_R",
                                                                       "years_pos")}, info, flush=True)
    for name, df in files.items():
        df.to_parquet(os.path.join(X.RES, name))
    with open(tpath, "w") as f:
        for line in lines:
            f.write(json.dumps(line, default=js) + "\n")
    print("written", tpath, len(lines), "lines")


if __name__ == "__main__":
    main()
