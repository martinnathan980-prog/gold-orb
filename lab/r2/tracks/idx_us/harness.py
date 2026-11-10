"""Research harness for track idx_us: every evaluated configuration goes through trial() and is logged."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/user/gold-orb/lab")
sys.path.insert(0, HERE)
import numpy as np            # noqa: E402
import pandas as pd           # noqa: E402
import goldlab as gl          # noqa: E402
from goldlab import r2        # noqa: E402
import strategy as S          # noqa: E402

TRACK = "idx_us"
RES = "/home/user/gold-orb/lab/results/r2/idx_us"
DETAIL = os.path.join(RES, "trials_detail.jsonl")
os.makedirs(RES, exist_ok=True)


def _key(sym, p):
    return json.dumps({"sym": sym, "params": p}, sort_keys=True, default=str)


def _load_detail():
    out = {}
    if os.path.exists(DETAIL):
        for line in open(DETAIL):
            r = json.loads(line)
            k = _key(r["sym"], r["params"])
            if k not in out or (r["full"] and not out[k]["full"]):
                out[k] = r
    return out


def n_trials():
    """(lines in trials.jsonl, distinct (sym, params) configurations)."""
    p = os.path.join(RES, "trials.jsonl")
    if not os.path.exists(p):
        return 0, 0
    rows = [json.loads(x) for x in open(p)]
    return len(rows), len({_key(r["sym"], r["params"]) for r in rows})


def trial(sym, params, full=False, note="", quiet=False):
    """Evaluate one configuration on IS (FP costs) and log it. Cached: the same (sym, params) is never
    evaluated (nor logged) twice at the same depth."""
    p = S.resolve(params)
    k = _key(sym, p)
    det = _load_detail()
    if k in det and (det[k]["full"] or not full):
        ev = det[k]["ev"]
    else:
        t0 = time.time()
        ev = r2.evaluate(sym, S.make_orders, p, full=full)
        r2.log_trial(TRACK, sym, p, ev)
        with open(DETAIL, "a") as f:
            f.write(json.dumps({"sym": sym, "params": p, "note": note, "full": full, "ev": ev, "secs": round(time.time() - t0, 1)}, default=str) + "\n")
    if not quiet:
        show(sym, p, ev, note)
    return ev


def show(sym, p, ev, note=""):
    r = ev["is"]
    if r.get("n", 0) == 0:
        print(f"[{sym}] {note} n=0", flush=True)
        return
    line = (f"[{sym}] {note:<28} n={r['n']:>5} tpy={r['trades_per_year']:>6} win={r['win_rate']:.3f} PF={r['pf']:.3f} t={r['t_stat']:>5} "
            f"expR={r['expectancy_R']:+.4f} yrs={r['years_pos']} ddR={r['max_dd_R']:>5} L={r['long_R']:+.1f} S={r['short_R']:+.1f} "
            f"hold={r['avg_hold_h']}h bp={ev['is_bps_per_trade']:+.2f}")
    if "is_stress" in ev:
        line += f" | stressPF={ev['is_stress'].get('pf')} grossPF={ev['is_gross'].get('pf')} gross_bp={ev.get('is_gross_bps_per_trade')}"
    if "is_every_signal" in ev:
        line += f" everyR={ev['is_every_signal'].get('expectancy_R')}"
    print(line, flush=True)
    print(f"        by_year={r.get('by_year_R')} exits={r.get('exit_reasons')}", flush=True)
