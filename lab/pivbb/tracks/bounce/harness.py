"""Evaluation harness of the bounce track: every configuration goes through r2.evaluate and is logged twice
(r2.log_trial -> results/r2/pivbb_bounce/trials.jsonl, and results/pivbb/bounce/trials.jsonl with its name)."""
import json
import os
import sys
import time

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from goldlab import r2  # noqa: E402
import strategy as S  # noqa: E402

OUT = os.path.join(LAB, "results", "pivbb", "bounce")
SYM = "xauusd"


def n_trials():
    f = os.path.join(OUT, "trials.jsonl")
    return sum(1 for _ in open(f)) if os.path.exists(f) else 0


def run(name, params, stage, log=True):
    t0 = time.time()
    ev = r2.evaluate(SYM, S.make_orders, params)
    r, st, gr, es = ev["is"], ev.get("is_stress", {}), ev.get("is_gross", {}), ev.get("is_every_signal", {})
    crit = r2.is_criteria(ev)
    row = {"name": name, "stage": stage, "params": params, "n": r.get("n", 0), "per_year": r.get("trades_per_year"),
           "win": r.get("win_rate"), "pf": r.get("pf"), "exp_R": r.get("expectancy_R"), "t": r.get("t_stat"),
           "years_pos": r.get("years_pos"), "long_R": r.get("long_R"), "short_R": r.get("short_R"),
           "stress_pf": st.get("pf"), "gross_pf": gr.get("pf"), "gross_exp_R": gr.get("expectancy_R"),
           "every_n": es.get("n"), "every_exp_R": es.get("expectancy_R"), "avg_hold_h": r.get("avg_hold_h"),
           "net_bps": ev.get("is_bps_per_trade"), "gross_bps": ev.get("is_gross_bps_per_trade"),
           "by_year_R": r.get("by_year_R"), "pass": crit.get("pass", False)}
    if log:
        r2.log_trial("pivbb_bounce", SYM, dict(params, _name=name), ev)
        with open(os.path.join(OUT, "trials.jsonl"), "a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    print(f"{name:34s} n={row['n']:5d} /yr={row['per_year']} win={row['win']} PF={row['pf']} exp={row['exp_R']} t={row['t']} "
          f"yrs={row['years_pos']} L/S={row['long_R']}/{row['short_R']} stressPF={row['stress_pf']} grossPF={row['gross_pf']} "
          f"grossExp={row['gross_exp_R']} every={row['every_exp_R']} pass={row['pass']} [{time.time() - t0:.0f}s]", flush=True)
    return ev, row
