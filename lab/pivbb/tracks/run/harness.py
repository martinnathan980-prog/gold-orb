"""Runner for the 'run' track: evaluate + log every configuration (in-sample only)."""
import json, os, sys, time
sys.path.insert(0, "/home/user/gold-orb/lab")
import numpy as np, pandas as pd
from goldlab import r2
from pivbb.tracks.run import strategy as S

OUT = "/home/user/gold-orb/lab/results/pivbb/run"
TRIALS = os.path.join(OUT, "trials.jsonl")


def n_trials():
    return sum(1 for _ in open(TRIALS)) if os.path.exists(TRIALS) else 0


def trial(tag, params, full=True, kind="rule"):
    t0 = time.time()
    ev = r2.evaluate("xauusd", S.make_orders, params, full=full)
    r2.log_trial("pivbb_run", "xauusd", {"tag": tag, **params}, ev)
    r = ev["is"]
    row = {"id": n_trials() + 1, "tag": tag, "kind": kind, "params": params,
           "n": r.get("n", 0), "per_year": r.get("trades_per_year"), "win": r.get("win_rate"), "pf": r.get("pf"), "t": r.get("t_stat"),
           "exp_R": r.get("expectancy_R"), "years_pos": r.get("years_pos"), "long_R": r.get("long_R"), "short_R": r.get("short_R"),
           "bps": ev.get("is_bps_per_trade"), "by_year_R": r.get("by_year_R")}
    if full:
        row.update(stress_pf=ev["is_stress"].get("pf"), gross_pf=ev["is_gross"].get("pf"), gross_exp_R=ev["is_gross"].get("expectancy_R"),
                   gross_bps=ev.get("is_gross_bps_per_trade"), every_n=ev["is_every_signal"].get("n"), every_exp_R=ev["is_every_signal"].get("expectancy_R"),
                   every_pf=ev["is_every_signal"].get("pf"))
    with open(TRIALS, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    print(f"#{row['id']:>2} {tag:<34} n={row['n']:>5} /yr={row['per_year']} win={row['win']} PF={row['pf']} t={row['t']} exp={row['exp_R']} "
          f"yrs={row['years_pos']} L/S={row['long_R']}/{row['short_R']}" + (f" | stress PF={row['stress_pf']} gross PF={row['gross_pf']} gross exp={row['gross_exp_R']} every exp={row['every_exp_R']}" if full else "")
          + f"  [{time.time() - t0:.0f}s]", flush=True)
    return ev, row
