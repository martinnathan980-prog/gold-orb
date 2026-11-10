"""Stage D -- neighbour robustness of the two shortlisted rules on gold (declared before running).

Shortlist after stages A-C (gold in-sample, FP costs):
  SQ  = B5_sq1h_n24_07       volatility-contraction breakout (1h bars, 24-bar channel, width <= 0.7 x its
                             20-day median) -- the only stage-B pass that is NOT mostly inside legacy trades
                             (13 % of its trades, weekly-R correlation 0.15).
  TR  = B3_d1h_n48_tr240_k2  2-day channel breakout taken only on the side of the 10-day channel state --
                             of the channel variants that pass, the one that duplicates the legacy sleeve
                             least (weekly-R correlation 0.57) and trades most (133 / year, 9/9 years).
Not shortlisted: B1 n240 (98 % of trades inside legacy trades), B1 n120 k3 (correlation 0.77).

Neighbours: each tuned parameter at -20 % / +20 % (max_days: adjacent value 4), one at a time.
Controls (reported, not part of the neighbour median): the rule with its defining condition switched off,
and the same channel duration on 2h bars."""
import json, os, sys
import numpy as np
from research import RES, run, n_configs
import stageB

SQ = stageB.B["B5_sq1h_n24_07"]
TR = stageB.B["B3_d1h_n48_tr240_k2"]

NB = {
    "SQ": {
        "n=19": {"n": 19}, "n=29": {"n": 29},
        "squeeze=0.56": {"squeeze": 0.56}, "squeeze=0.84": {"squeeze": 0.84},
        "squeeze_ref=384": {"squeeze_ref": 384}, "squeeze_ref=576": {"squeeze_ref": 576},
        "stop_atr=1.6": {"stop_atr": 1.6}, "stop_atr=2.4": {"stop_atr": 2.4},
        "trail_atr=1.6": {"trail_atr": 1.6}, "trail_atr=2.4": {"trail_atr": 2.4},
        "atr_n=11": {"atr_n": 11}, "atr_n=17": {"atr_n": 17},
        "max_days=4": {"max_days": 4},
    },
    "TR": {
        "n=38": {"n": 38}, "n=58": {"n": 58},
        "trend_n=192": {"trend_n": 192}, "trend_n=288": {"trend_n": 288},
        "stop_atr=1.6": {"stop_atr": 1.6}, "stop_atr=2.4": {"stop_atr": 2.4},
        "trail_atr=1.6": {"trail_atr": 1.6}, "trail_atr=2.4": {"trail_atr": 2.4},
        "atr_n=11": {"atr_n": 11}, "atr_n=17": {"atr_n": 17},
        "max_days=4": {"max_days": 4},
    },
}
CTRL = {
    "SQ": {"ctrl_no_squeeze": {"squeeze": 0.0, "squeeze_ref": 0},
           "ctrl_2h_bars": {"tf": 120, "n": 12, "squeeze_ref": 240}},
    "TR": {"ctrl_no_trend": {"trend_n": 0},
           "ctrl_2h_bars": {"tf": 120, "n": 24, "trend_n": 120}},
}
BASE = {"SQ": SQ, "TR": TR}

if __name__ == "__main__":
    pth = os.path.join(RES, "plan_stageD.json")
    if not os.path.exists(pth):
        json.dump({"stage": "D-neighbours", "declared_before_running": True, "sym": "xauusd", "base": BASE,
                   "neighbours": NB, "controls": CTRL, "rationale": __doc__}, open(pth, "w"), indent=1)
    out = {}
    for f in ("SQ", "TR"):
        pfs = []
        rows = {}
        for k, ch in NB[f].items():
            d = run(f"D_{f}_{k}", "D-neighbour", "xauusd", {**BASE[f], **ch}, full=True)
            pfs.append(d["is"]["pf"])
            rows[k] = {"n": d["is"]["n"], "pf": d["is"]["pf"], "t": d["is"]["t_stat"], "exp_R": d["is"]["expectancy_R"],
                       "years_pos": d["is"]["years_pos"], "stress_pf": d["stress"]["pf"], "every_exp_R": d["every"]["expectancy_R"],
                       "pass": d["crit"]["pass"]}
        ctrl = {}
        for k, ch in CTRL[f].items():
            d = run(f"D_{f}_{k}", "D-control", "xauusd", {**BASE[f], **ch}, full=True)
            ctrl[k] = {"n": d["is"]["n"], "pf": d["is"]["pf"], "t": d["is"]["t_stat"], "exp_R": d["is"]["expectancy_R"],
                       "years_pos": d["is"]["years_pos"], "gross_pf": d["gross"]["pf"], "every_exp_R": d["every"]["expectancy_R"]}
        out[f] = {"neighbour_median_pf": round(float(np.median(pfs)), 3), "neighbour_min_pf": min(pfs), "neighbour_max_pf": max(pfs),
                  "n_neighbours": len(pfs), "n_pass_all_is_criteria": int(sum(r["pass"] for r in rows.values())),
                  "neighbours": rows, "controls": ctrl}
        print(f, "median neighbour PF", out[f]["neighbour_median_pf"], "min", min(pfs), "max", max(pfs), flush=True)
    json.dump(out, open(os.path.join(RES, "neighbours.json"), "w"), indent=1)
    print("configurations so far:", n_configs())
