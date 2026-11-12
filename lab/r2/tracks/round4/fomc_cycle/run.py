"""Runs the ten declared configurations of FOMC-cycle even/odd weeks (declared.json), IN SAMPLE ONLY, and writes
results/r2/round4/fomc_cycle/trials.jsonl (one line per configuration), results.json and the trades files.

    python3 run.py --smoke   # structure only (statuses, counts, columns): no result is printed or written
    python3 run.py           # the declared run (refuses to run twice: trials.jsonl is written once)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import json  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DECL = json.load(open(os.path.join(C.OUT, "declared.json")))
CFG = {c["id"]: c for c in DECL["configurations"]}
COST_TXT = {"fp": "FP frames + r2.costs: market slip 0.2 bp/side, stop slip 0.5 bp, long swap (us500 5.5 %/yr, ger40 4.1 %/yr) "
                  "per 17:00 NY rollover, Friday x3, shorts 0",
            "x1.5": "spread x1.5, slippage x1.5, swap rates x1.5 (D9)", "gross": "mid quotes, no cost (accounting only)"}


def line(cid, t, o, extra=None):
    c = CFG[cid]
    p = c["params"]
    d = {"id": cid, "name": c["name"], "role": c["role"], "sym": p["sym"], "params": p,
         "period": "in sample: entries and exits 2013-01-01 .. 2021-12-31 (frames cut at ts < 2022-01-01)",
         "costs": COST_TXT[p["costs"]], "first_entry": str(t.entry_time.min()), "last_exit": str(t.exit_time.max()),
         "is": C.summarize(t, o)}
    if extra:
        d.update(extra)
    return d


def save_trades(t, name):
    t.to_parquet(os.path.join(C.OUT, f"trades_{name}.parquet"))


def main(smoke=False):
    tri = os.path.join(C.OUT, "trials.jsonl")
    if not smoke:
        assert not os.path.exists(tri), "trials.jsonl exists: the declared run is done once"
    us = C.load_is("us500")
    if smoke:
        t, o, ok = C.run(us, CFG[1]["params"])
        print("rows", len(us), "decisions", len(o), dict(o.status.value_counts()), "trades", len(t))
        print("columns", list(t.columns))
        print("first entry", t.entry_time.min(), "last exit", t.exit_time.max(), "max n_days", int(t.n_days.max()))
        print("entry delays > 5 min", int((t.entry_delay_min > 5).sum()), "exits moved", int((t.exit_shift_min < -1).sum()))
        print("weeks", dict(t.wlabel.value_counts().sort_index()), "sides", dict(t.side.value_counts()))
        return
    lines, trades = {}, {}
    # (1)-(6), (8): us500, FP costs
    for cid in (1, 2, 3, 4, 5, 6, 8):
        t, o, ok = C.run(us, CFG[cid]["params"])
        trades[cid] = (t, o, ok)
        save_trades(t, f"{cid:02d}_{CFG[cid]['name']}")
        lines[cid] = line(cid, t, o)
    t1, o1, ok1 = trades[1]
    o1.to_parquet(os.path.join(C.OUT, "decisions_01_main.parquet"))
    # every signal: the main already takes every week (no_overlap = False, trades never overlap)
    ov = (t1.entry_time.to_numpy()[1:] < t1.exit_time.to_numpy()[:-1]).sum()
    lines[1]["every_signal"] = {"note": "calendar rule: every week is a signal; all taken (no_overlap=False); identical trades",
                                "overlapping_trades": int(ov), "n": int(len(t1)), "expectancy_R": round(float(t1.R.mean()), 4)}
    # gross accounting of the main (r2 'gross' convention), not a configuration
    tg, _, _ = C.run(us, CFG[1]["params"], cmode="gross")
    lines[1]["is_gross_accounting"] = {"n": int(len(tg)), "pf": round(C.pf(tg.R), 3), "expectancy_R": round(float(tg.R.mean()), 4),
                                       "t_stat": round(C.t_stat(tg.R), 2), "bp_gross_per_trade": round(float((tg.pnl / tg.entry).mean() * 1e4), 2),
                                       "bp_gross_long": round(float((tg.pnl / tg.entry)[tg.side > 0].mean() * 1e4), 2),
                                       "bp_gross_short": round(float((tg.pnl / tg.entry)[tg.side < 0].mean() * 1e4), 2)}
    save_trades(tg, "01_main_gross_accounting")
    # (9) stress
    t9, o9, ok9 = C.run(us, CFG[9]["params"])
    save_trades(t9, "09_stress_x1.5")
    R_sw1 = (t9.pnl + t9.swap / 3.0) / t9.risk                 # same stressed trades, swap rate x1 instead of x1.5
    lines[9] = line(9, t9, o9, {"info_only_stress_with_swap_x1": {
        "pf": round(C.pf(R_sw1), 3), "expectancy_R": round(float(R_sw1.mean()), 4),
        "note": "the lab's usual stress (spread and slippage x1.5, swap unchanged), by exact arithmetic on the same trades; not used"}})
    # (10) null of the main
    nl, means = C.null_time(us, ok1, t1, "us500", 200, 0)
    np.save(os.path.join(C.OUT, "null_means_10_main.npy"), means)
    lines[10] = {"id": 10, "name": CFG[10]["name"], "role": CFG[10]["role"], "sym": "us500", "params": CFG[10]["params"],
                 "period": "replays drawn over the in-sample slice 2013-01-01 .. 2021-12-31, each replay entirely inside it",
                 "costs": COST_TXT["fp"], "null": nl}
    # (8) against its own null
    t8, o8, ok8 = trades[8]
    nl8, means8 = C.null_time(us, ok8, t8, "us500", 200, 0)
    np.save(os.path.join(C.OUT, "null_means_08_long_even.npy"), means8)
    lines[8]["null_own_trades"] = nl8
    del us
    # (7) ger40
    ge = C.load_is("ger40")
    t7, o7, ok7 = C.run(ge, CFG[7]["params"])
    save_trades(t7, "07_mech_ger40")
    lines[7] = line(7, t7, o7)
    del ge
    with open(tri, "w") as f:
        for cid in range(1, 11):
            f.write(json.dumps(lines[cid], default=str) + "\n")
    # criteria on (1)
    r1, r9 = lines[1]["is"], lines[9]["is"]
    yp, yn = (int(x) for x in r1["years_pos"].split("/"))
    nb = {CFG[c]["name"]: lines[c]["is"]["pf"] for c in (2, 3, 4, 5, 6)}
    med = float(np.median(list(nb.values())))
    crit = {
        "n>=250": {"value": r1["n"], "pass": r1["n"] >= 250},
        "pf>=1.12": {"value": r1["pf"], "pass": r1["pf"] >= 1.12},
        "t>=2.5": {"value": r1["t_stat"], "pass": r1["t_stat"] >= 2.5},
        "years_pos>=60%": {"value": r1["years_pos"], "pass": yp >= 0.6 * yn},
        "stress_pf>=1.04": {"value": r9["pf"], "pass": r9["pf"] >= 1.04},
        "neighbours_median_pf>=1.06": {"value": round(med, 3), "neighbours": nb, "pass": med >= 1.06},
        "every_signal_exp>0": {"value": lines[1]["every_signal"]["expectancy_R"], "pass": lines[1]["every_signal"]["expectancy_R"] > 0},
        "hold<=5_nyse_days": {"value": r1["max_hold_nyse_days"], "max_hold_h": r1["max_hold_h"],
                              "trades_over_192h": r1["n_hold_over_192h"], "pass": r1["max_hold_nyse_days"] <= 5},
        "null>=97.5pct": {"value": nl["percentile"], "pass": nl["percentile"] >= 97.5},
        "ger40_expectancy>0": {"value": lines[7]["is"]["expectancy_R"], "pass": lines[7]["is"]["expectancy_R"] > 0},
    }
    res = {"what": "FOMC-cycle even/odd weeks (PROTOCOL_V3 Addendum J rule 4), in sample only, verdict on (1)",
           "criteria": crit, "passes_in_sample": bool(all(v["pass"] for v in crit.values())),
           "configs": {CFG[c]["name"]: {k: lines[c]["is"].get(k) for k in ("n", "pf", "t_stat", "expectancy_R", "total_R",
                                                                       "years_pos", "bp_net_per_trade", "bp_swap_per_trade")}
                       for c in range(1, 10)},
           "null_main": nl, "null_diag_long_even": nl8}
    C.jdump(res, os.path.join(C.OUT, "results.json"))
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main(smoke="--smoke" in sys.argv)
