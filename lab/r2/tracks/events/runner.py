"""Trial runner for the events track: every evaluated configuration is logged with r2.log_trial
(results/r2/events/trials.jsonl) and, with more detail, in trials_full.jsonl."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
for p in (LAB, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
import strategy as S  # noqa: E402

TRACK = "events"
RES = os.path.join(LAB, "results", "r2", TRACK)
os.makedirs(RES, exist_ok=True)
_cur = {"sym": None}


def use(sym):
    """Keep ONE symbol in memory."""
    if _cur["sym"] != sym:
        r2.free()
        S._cache.clear()
        _cur["sym"] = sym
    return r2.load(sym)


def n_trials():
    f = os.path.join(RES, "trials.jsonl")
    return sum(1 for _ in open(f)) if os.path.exists(f) else 0


def trial(sym, params, full=False, tag=""):
    use(sym)
    t0 = time.time()
    p = S.resolve(params)
    ev = r2.evaluate(sym, S.make_orders, p, full=full)
    r2.log_trial(TRACK, sym, p, ev)
    row = {"tag": tag, "sym": sym, "params": p, "full": full, "ev": ev}
    with open(os.path.join(RES, "trials_full.jsonl"), "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    r = ev["is"]
    if r.get("n", 0) == 0:
        print(f"[{n_trials():3d}] {tag:18s} {sym:7s} n=0  {json.dumps(params)}", flush=True)
        return ev
    s = (f"[{n_trials():3d}] {tag:18s} {sym:7s} n={r['n']:4d} pf={r['pf']:.3f} t={r['t_stat']:+.2f} expR={r['expectancy_R']:+.4f} "
         f"win={r['win_rate']:.2f} yrs={r['years_pos']} bps={ev['is_bps_per_trade']:+.2f} L={r['long_R']:+.1f} S={r['short_R']:+.1f} "
         f"hold={r['avg_hold_h']:.1f}h dd={r['max_dd_R']:.1f}")
    if full:
        s += (f" | stress pf={ev['is_stress'].get('pf')} gross bps={ev.get('is_gross_bps_per_trade')} gross pf={ev['is_gross'].get('pf')} "
              f"every expR={ev.get('is_every_signal', {}).get('expectancy_R')}")
    print(s + f"  ({time.time() - t0:.0f}s)", flush=True)
    return ev
