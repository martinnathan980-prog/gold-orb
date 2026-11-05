"""Diagnostic (NOT new trials, coordinator caveat 3): configs with multi-day holds or clustered
signals re-simulated with no_overlap=False (every signal traded, positions may overlap), IS only,
normal costs.  Shows whether the one-position-at-a-time results depend on which signals get skipped.
Output: results/crossasset/overlap_diag.csv"""
import json
import os

import numpy as np
import pandas as pd

from common import RES, TRACK, free_m1, gl, load_bars
import strategy as S
from parta import make_cache

A_NAMES = ["A2a_div_h1_n24", "A2b_div_h1_n72", "A3a_yen_h1", "A3a_yen_h1_ldnmorning", "A3b_riskoff_giveback",
           "A4a_channel_usd_confirm", "A4b_channel_usd_contra", "A5a_resmom_n24_h3", "A5b_rawmom_n24_h3_control"]


def rep_of(t, cfg=None):
    r = gl.report(gl.cut(t, "is"))
    if cfg is not None:   # logged as a trial (tagged diag=overlap) to keep the trial count conservative
        gl.log_trial(TRACK, {**cfg, "diag": "overlap", "no_overlap": False}, r)
    return {k: r.get(k) for k in ("n", "trades_per_year", "pf", "expectancy_R", "t_stat", "years_pos")}


def main():
    trials = [json.loads(l) for l in open(os.path.join(RES, "trials.jsonl"))]
    trials = [tr for tr in trials if "diag" not in tr["config"]]   # skip diagnostic re-runs
    last = {}
    for tr in trials:
        c = tr["config"]
        key = (c.get("part"), c.get("name") or f'{c.get("rule")}{"_d" if c.get("rule_tf") == "D" else ""}@{c.get("sym")}')
        last[key] = tr
    rows = []
    for sym in ["xauusd", "eurusd", "gbpusd", "usdjpy", "deuidxeur", "lightcmdusd"]:
        m1 = gl.load_m1(sym)
        for nm, tf in (("channel", "4h"), ("channel_d", "D"), ("rsi2", "D")):
            tr = last[("B", f"{nm}@{sym}")]   # last logged run = bug-fixed version when re-run
            p = {k: v for k, v in tr["config"].items() if k not in ("part", "sym", "rerun")}
            o = S.make_orders(m1, rule=p.pop("rule"), bars=load_bars(sym, tf), **p)
            ov = rep_of(gl.simulate(m1, o, sym=sym, no_overlap=False), tr["config"])
            rows.append({"name": f"{nm}@{sym}", "n_noov": tr["is"]["n"], "pf_noov": tr["is"]["pf"],
                         "t_noov": tr["is"]["t_stat"], **{f"{k}_overlap": v for k, v in ov.items()}})
            print(rows[-1], flush=True)
        free_m1(sym)
        del m1
    m1 = gl.load_m1("xauusd")
    cache = make_cache()
    for nm in A_NAMES:
        tr = last[("A", nm)]
        p = {k: v for k, v in tr["config"].items() if k not in ("part", "name", "note")}
        o = S.make_orders(m1, None, cache=cache, **p)
        ov = rep_of(gl.simulate(m1, o, no_overlap=False), tr["config"])
        rows.append({"name": nm, "n_noov": tr["is"]["n"], "pf_noov": tr["is"]["pf"], "t_noov": tr["is"]["t_stat"],
                     **{f"{k}_overlap": v for k, v in ov.items()}})
        print(rows[-1], flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RES, "overlap_diag.csv"), index=False)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
