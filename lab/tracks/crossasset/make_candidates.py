"""Build results/crossasset/candidates.json + markdown tables for report.md from the logged
configs (re-evaluation of already-logged configs on IS only; nothing new is logged)."""
import json
import os

import numpy as np
import pandas as pd

from common import RES, free_m1, gl, load_bars
from goldlab.evalkit import evaluate_is, is_criteria
import strategy as S
from parta import CONFIGS, NEIGH_YEN, make_cache
from partb import FIXED

OUT_MD = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/tables.md"
KEYS = ["n", "trades_per_year", "win_rate", "avg_win_R", "avg_loss_R", "expectancy_R", "pf", "t_stat",
        "years_pos", "weeks_pos_pct", "max_dd_R", "long_n", "long_R", "short_n", "short_R", "max_hold_h"]


def row(name, rep, rs, crit, extra=None):
    d = {"name": name, **{k: rep.get(k) for k in KEYS}, "stress_pf": rs.get("pf"),
         "by_year_R": rep.get("by_year_R"), "is_criteria": {k: bool(v) for k, v in crit.items()}}
    d.update(extra or {})
    return d


def md_table(rows, cols):
    h = "| " + " | ".join(c for c, _ in cols) + " |\n|" + "---|" * len(cols) + "\n"
    for r in rows:
        h += "| " + " | ".join(str(f(r)) for _, f in cols) + " |\n"
    return h


def main():
    gross = pd.read_csv(os.path.join(RES, "gross_vs_net.csv")).set_index("name")
    ov = pd.read_csv(os.path.join(RES, "overlap_diag.csv")).set_index("name")
    m1 = gl.load_m1("xauusd")
    cache = make_cache()
    A = []
    for nm, p in CONFIGS.items():
        q = {k: v for k, v in p.items() if k != "note"}
        o = S.make_orders(m1, None, cache=cache, **q)
        t, rep, rs = evaluate_is(m1, o)
        crit = is_criteria(rep, rs)
        ex = {"params": q, "note": p.get("note"), "gross_pf": gross.pf_gross.get(nm),
              "overlap_pf": ov["pf_overlap"].get(nm)}
        A.append(row(nm, rep, rs, crit, ex))
        print(nm, rep["pf"], rs.get("pf"), crit["pass"], flush=True)
    free_m1("xauusd")
    del m1
    B = []
    for sym in ["xauusd", "eurusd", "gbpusd", "usdjpy", "deuidxeur", "lightcmdusd"]:
        m1 = gl.load_m1(sym)
        bars = {"channel": load_bars(sym, "4h"), "rsi2": load_bars(sym, "D"), "orb": None,
                "channel_d": load_bars(sym, "D")}
        for fam, p in FIXED.items():
            q = {k: v for k, v in p.items() if k != "rule"}
            o = S.make_orders(m1, rule=p["rule"], bars=bars[fam], **q)
            t, rep, rs = evaluate_is(m1, o, sym=sym)
            crit = is_criteria(rep, rs)
            nm = f"{fam}@{sym}"
            B.append(row(nm, rep, rs, crit, {"params": {"sym": sym, **p}, "gross_pf": gross.pf_gross.get(nm),
                                              "overlap_pf": ov["pf_overlap"].get(nm)}))
            print(nm, rep["pf"], rs.get("pf"), crit["pass"], flush=True)
        free_m1(sym)
        del m1
    yen_neigh = [r for r in A if r["name"] in NEIGH_YEN]
    med = float(np.median([r["pf"] for r in yen_neigh]))
    out = {
        "track": "crossasset",
        "verdict": "no configuration passes the pre-registered IS criteria; no finalist; VAL not accessed",
        "trials_logged": sum(1 for _ in open(os.path.join(RES, "trials.jsonl"))),
        "finalists": [],
        "best_near_miss": {"name": "A3a_yen_h1_ldnmorning", "neighbour_median_pf": round(med, 3),
                           "neighbours": {r["name"]: r["pf"] for r in yen_neigh},
                           "why_not_finalist": "IS t=0.96 (<2), PF 1.19 (<1.20), 24.8 trades/yr (<25); session "
                                               "window chosen after a descriptive IS split; stress PF 1.08"},
        "part_A": A, "part_B": B,
    }
    with open(os.path.join(RES, "candidates.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    cols = [("config", lambda r: r["name"]), ("n", lambda r: r["n"]), ("tr/yr", lambda r: r["trades_per_year"]),
            ("win", lambda r: r["win_rate"]), ("avgW R", lambda r: r["avg_win_R"]), ("avgL R", lambda r: r["avg_loss_R"]),
            ("PF", lambda r: r["pf"]), ("t", lambda r: r["t_stat"]), ("yrs+", lambda r: r["years_pos"]),
            ("wk+%", lambda r: r["weeks_pos_pct"]), ("maxDD R", lambda r: r["max_dd_R"]),
            ("long n/R", lambda r: f'{r["long_n"]}/{r["long_R"]}'), ("short n/R", lambda r: f'{r["short_n"]}/{r["short_R"]}'),
            ("stress PF", lambda r: r["stress_pf"]), ("gross PF", lambda r: r["gross_pf"]),
            ("overlap PF", lambda r: "" if r.get("overlap_pf") is None or r["overlap_pf"] != r["overlap_pf"]
             else r["overlap_pf"])]
    with open(OUT_MD, "w") as f:
        f.write("## Part A\n\n" + md_table(A, cols) + "\n## Part B\n\n" + md_table(B, cols))
        f.write("\nPart B PF matrix\n\n")
        fams = list(FIXED)
        f.write("| instrument | " + " | ".join(fams) + " |\n|" + "---|" * (len(fams) + 1) + "\n")
        for sym in ["xauusd", "eurusd", "gbpusd", "usdjpy", "deuidxeur", "lightcmdusd"]:
            cells = []
            for fam in fams:
                r = next(x for x in B if x["name"] == f"{fam}@{sym}")
                cells.append(f'{r["pf"]} / {r["n"]} (gross {r["gross_pf"]})')
            f.write(f"| {sym} | " + " | ".join(cells) + " |\n")
    print("neighbour median PF", med)


if __name__ == "__main__":
    main()
