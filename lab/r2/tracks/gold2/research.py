"""Research harness of track `gold2` (in-sample only).

Every evaluated configuration goes through r2.evaluate and is logged once with r2.log_trial; the
complete record (resolved parameters, per-year R, criteria) is appended to
results/r2/gold2/trials_detail.jsonl, which also serves as a cache (a configuration is never
evaluated or logged twice, except a quick run later upgraded to a full run: flagged `rerun_of_quick`).
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
for _p in (LAB, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.split import cut  # noqa: E402
import strategy as S  # noqa: E402

TRACK = "gold2"
RES = os.path.join(LAB, "results", "r2", TRACK)
DETAIL = os.path.join(RES, "trials_detail.jsonl")
os.makedirs(RES, exist_ok=True)


def key_of(sym, params):
    return json.dumps({"sym": sym, **S.resolve(params)}, sort_keys=True, default=str)


def load_detail():
    out = {}
    if os.path.exists(DETAIL):
        with open(DETAIL) as f:
            for line in f:
                d = json.loads(line)
                out[d["key"]] = d            # a later (full) record replaces the quick one
    return out


def n_configs():
    return len(load_detail())


def use(sym):
    """Keep one symbol in memory at a time."""
    for s in list(r2._fp_cache):
        if s != sym:
            r2.free(s)
            S._CTX.clear()


def run(label, stage, sym, params, full=True, note="", quiet=False):
    """Evaluate one configuration on the in-sample period (FP costs), log it, cache it."""
    p = S.resolve(params)
    key = key_of(sym, p)
    cache = load_detail()
    if key in cache and (cache[key]["full"] or not full):
        if not quiet:
            show(cache[key])
        return cache[key]
    use(sym)
    t0 = time.time()
    ev = r2.evaluate(sym, S.make_orders, p, full=full)
    r2.log_trial(TRACK, sym, {"label": label, "stage": stage, **p}, ev)
    d = {"key": key, "label": label, "stage": stage, "sym": sym, "params": p, "full": bool(full), "note": note,
         "rerun_of_quick": key in cache, "is": ev["is"], "is_bps": ev.get("is_bps_per_trade"),
         "secs": round(time.time() - t0, 1), "utc": pd.Timestamp.now("UTC").isoformat(timespec="seconds")}
    if full:
        d["stress"] = {q: ev["is_stress"].get(q) for q in ("n", "pf", "expectancy_R", "t_stat")}
        d["gross"] = {q: ev["is_gross"].get(q) for q in ("n", "pf", "expectancy_R", "t_stat", "long_R", "short_R",
                                                         "long_n", "short_n")}
        d["gross_bps"] = ev.get("is_gross_bps_per_trade")
        d["every"] = {q: ev["is_every_signal"].get(q) for q in ("n", "pf", "expectancy_R", "t_stat", "years_pos",
                                                                "long_R", "short_R", "max_dd_R")}
        d["crit"] = r2.is_criteria(ev)
    with open(DETAIL, "a") as f:
        f.write(json.dumps(d, default=str) + "\n")
    if not quiet:
        show(d)
    return d


def show(d):
    r = d["is"]
    if r.get("n", 0) == 0:
        print(f"[{d['label']} {d['sym']}] no trades", flush=True)
        return
    s = (f"[{d['label']} | {d['sym']}] n={r['n']} ({r['trades_per_year']}/yr) win={r['win_rate']} exp={r['expectancy_R']}R "
         f"PF={r['pf']} t={r['t_stat']} yrs+={r['years_pos']} DD={r['max_dd_R']}R hold={r['avg_hold_h']}h "
         f"L={r['long_R']}R/{r['long_n']} S={r['short_R']}R/{r['short_n']} bps={d['is_bps']}")
    if d.get("full"):
        s += (f" | stressPF={d['stress']['pf']} grossPF={d['gross']['pf']} gross_exp={d['gross']['expectancy_R']} "
              f"gross_bps={d['gross_bps']} | every: n={d['every']['n']} exp={d['every']['expectancy_R']} PF={d['every']['pf']} "
              f"| pass={d['crit']['pass']} fail={[k for k, v in d['crit'].items() if not v and k != 'pass']}")
    print(s, flush=True)
    print("      by year:", r.get("by_year_R"), flush=True)


def is_trades(sym, params, mode="fp", no_overlap=True):
    """In-sample trades of a configuration (diagnostics: sides, halves, overlaps).  Uses r2.run, i.e. the
    same code path as r2.evaluate; only trades entered before 2022 are returned."""
    use(sym)
    return cut(r2.run(sym, S.make_orders, S.resolve(params), mode, no_overlap), "is")


def pf(x):
    x = np.asarray(x, float)
    g, l = x[x > 0].sum(), -x[x < 0].sum()
    return float(g / l) if l > 0 else float("nan")


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 else float("nan")
