"""Research harness for track `trend` (IS only).

    python3 research.py '<json config>' [phase] [note]      evaluate + log ONE config
    python3 research.py --batch file.json                    evaluate + log a list of {cfg, phase, note}

Every evaluation is logged with gl.log_trial("trend", ...) (results/trend/trials.jsonl) and a
detailed record (by-year R, long/short PF, top-5% share, criteria) in trials_detail.jsonl.
A config already present in the log is NOT re-run (no double counting): its record is printed.
Simulation runs on M1 data cut at 2022-01-10, so VAL prices are never seen during research
(trades entered before 2022-01-01 can still finish their <= 5-day life).
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, LAB)
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import goldlab as gl  # noqa: E402
from goldlab.evalkit import evaluate_is, is_criteria  # noqa: E402

import strategy as S  # noqa: E402

RES = os.path.join(LAB, "results", "trend")
DETAIL = os.path.join(RES, "trials_detail.jsonl")
IS_END_DATA = "2022-01-10"

_m1 = None


def m1_is():
    global _m1
    if _m1 is None:
        _m1 = gl.load_m1("xauusd", end=IS_END_DATA)
    return _m1


def _pf(x):
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return round(float(g / l), 3) if l > 0 else float("nan")


def extra_stats(t):
    R = t["R"].to_numpy()
    fin = np.isfinite(R)
    R = R[fin]
    side = t["side"].to_numpy()[fin]
    out = {}
    if len(R) == 0:
        return out
    k = max(1, int(round(0.05 * len(R))))
    top = np.sort(R)[::-1][:k].sum()
    out["top5pct_R"] = round(float(top), 1)
    out["top5pct_share"] = round(float(top / R.sum()), 2) if R.sum() > 0 else None
    out["long_pf"] = _pf(R[side > 0])
    out["short_pf"] = _pf(R[side < 0])
    out["long_exp"] = round(float(R[side > 0].mean()), 4) if (side > 0).any() else None
    out["short_exp"] = round(float(R[side < 0].mean()), 4) if (side < 0).any() else None
    out["med_risk_usd"] = round(float(t["risk"].median()), 2)
    out["cost_R"] = round(float(((t["commission"] + t["swap"]) / t["risk"]).median()), 3)
    return out


def _done():
    seen = {}
    if os.path.exists(DETAIL):
        for line in open(DETAIL):
            r = json.loads(line)
            seen[json.dumps(r["config"], sort_keys=True)] = r
    return seen


def fmt(r):
    s = r["is"]
    if s.get("n", 0) == 0:
        return "n=0"
    return (f"n={s['n']:5d} /yr={s['trades_per_year']:6.1f} win={s['win_rate']:.2f} "
            f"aw={s['avg_win_R']:.2f} al={s['avg_loss_R']:.2f} exp={s['expectancy_R']:+.3f} "
            f"pf={s['pf']:.3f} t={s['t_stat']:+.2f} yrs={s['years_pos']} wk+={s['weeks_pos_pct']} "
            f"dd={s['max_dd_R']} L={s['long_R']:+.0f}(pf{s.get('long_pf')}) "
            f"S={s['short_R']:+.0f}(pf{s.get('short_pf')}) stress={s.get('stress_pf')} "
            f"top5={s.get('top5pct_share')} hold={s['avg_hold_h']}h")


def run(cfg, phase="", note="", verbose=True):
    cfg = S.resolve(cfg)
    key = json.dumps(cfg, sort_keys=True)
    seen = _done()
    if key in seen:
        r = seen[key]
        if verbose:
            print(f"[cached] {phase:8s} {key}\n         {fmt(r)}")
        return r
    m1 = m1_is()
    t0 = time.time()
    orders = S.make_orders(m1, **cfg)
    t, rep, rs = evaluate_is(m1, orders)
    ti = gl.cut(t, "is")
    rec = dict(rep)
    rec.update(stress_pf=rs.get("pf"), stress_exp=rs.get("expectancy_R"))
    rec.update(extra_stats(ti))
    crit = is_criteria(rep, rs)
    gl.log_trial("trend", dict(cfg, _phase=phase, _note=note), rec)
    r = {"config": cfg, "phase": phase, "note": note, "is": {k: v for k, v in rec.items()},
         "crit": crit, "skipped": t.attrs.get("skipped"), "orders": t.attrs.get("orders"),
         "secs": round(time.time() - t0, 1)}
    with open(DETAIL, "a") as f:
        f.write(json.dumps(r, default=str) + "\n")
    if verbose:
        print(f"{phase:8s} {key}\n         {fmt(r)}\n         by_year={rec.get('by_year_R')} "
              f"exits={rec.get('exit_reasons')} pass={crit.get('pass')} ({r['secs']}s)")
    return r


def n_trials():
    p = os.path.join(RES, "trials.jsonl")
    return sum(1 for _ in open(p)) if os.path.exists(p) else 0


if __name__ == "__main__":
    if sys.argv[1] == "--batch":
        jobs = json.load(open(sys.argv[2]))
        for j in jobs:
            run(j["cfg"], j.get("phase", ""), j.get("note", ""))
    else:
        run(json.loads(sys.argv[1]), *(sys.argv[2:4]))
    print("trials logged so far:", n_trials())
