"""Random-entry null for each qualifying pair (information only; PROTOCOL_V2 section 4 logic of goldlab.r2.null_test,
re-implemented here on the in-sample slice because r2.null_test loads the whole frame).

    PYTHONDONTWRITEBYTECODE=1 python3 null.py [rule:sym ...]        (default: the qualifiers of analysis.json)

The pair's taken trades of the window (FP costs) are re-entered AT MARKET at random moments, each keeping its side, its
stop distance and trailing distance (scaled with the price level) and its time-exit delay:
  mode "day"  (signal rules): same New-York minute of the day, random day of the window 2018-02-01 .. 2021-12-31;
  mode "time" (GOLD_FRI_PM, a calendar rule): random day and time of the window.
200 draws, one position at a time, FP costs.  Output: the percentile of the rule's mean R among the draws.
Output file: results/r2/autopsy/breadth/null.json
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402


def null_pair(rule, sym, n_draw=200, seed=0):
    m1 = C.load_is(sym)
    leader = C.leader_series(C.load_is("us100")) if rule == "nq_btc_follow" else None
    t, o, info = C.run_rule(rule, sym, m1, "fp", leader=leader)
    t = C.window(t)
    rows = o.iloc[t["oid"].to_numpy()]
    idx = m1.index
    fill_i = idx.searchsorted(t.entry_time).astype(np.int64)
    entry = t.entry.to_numpy(float)
    side = t.side.to_numpy()
    stop_rel = t.risk.to_numpy(float) / entry
    trail_rel = (rows["trail"].to_numpy(float) / entry) if "trail" in rows else np.full(len(t), np.nan)
    xi = rows["exit_i"].to_numpy(np.int64) if "exit_i" in rows else np.full(len(t), -1, np.int64)
    dur = np.where(xi >= 0, np.maximum(xi - fill_i, 1), -1)
    lo, hi = int(idx.searchsorted(C.COMMON_START)), len(idx)
    ny = idx[lo:hi].tz_convert(C.NY)
    mod = (ny.hour * 60 + ny.minute).to_numpy()
    order = np.argsort(mod, kind="stable")
    bounds = np.searchsorted(mod[order], np.arange(1441))
    mod_c = (idx[fill_i].tz_convert(C.NY).hour * 60 + idx[fill_i].tz_convert(C.NY).minute).to_numpy()
    mid = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2
    rng = np.random.default_rng(seed)
    mode = "time" if rule == "GOLD_FRI_PM" else "day"
    costs = C.r2.costs(sym)
    means = []
    for _ in range(n_draw):
        if mode == "day":
            a, b = bounds[mod_c], bounds[mod_c + 1]
            ok = b > a
            pos = a + (rng.random(len(t)) * np.maximum(b - a, 1)).astype(np.int64)
            ei = lo + order[np.minimum(pos, len(order) - 1)]
        else:
            ok = np.ones(len(t), bool)
            ei = lo + rng.integers(0, hi - lo - 2, len(t))
        px = mid[ei]
        no = pd.DataFrame({"entry_i": ei, "side": side, "stop_dist": stop_rel * px, "trail": trail_rel * px,
                           "exit_i": np.where(dur >= 0, np.minimum(ei + dur, len(idx) - 1), -1)})[ok]
        tn = C.simulate(m1, no, sym=sym, costs=costs, no_overlap=True)
        means.append(float(tn.R.mean()) if len(tn) else 0.0)
    means = np.array(means)
    cand = float(t.R.mean())
    C.clear_rule_caches()
    return {"rule": rule, "instrument": sym, "mode": mode, "n": int(len(t)), "rule_mean_R": round(cand, 4),
            "null_mean_R": round(float(means.mean()), 4), "null_p95_R": round(float(np.percentile(means, 95)), 4),
            "null_max_R": round(float(means.max()), 4), "percentile": round(float((means < cand).mean() * 100), 1),
            "draws": n_draw}


def main(args):
    if args:
        pairs = [a.split(":") for a in args]
    else:
        an = json.load(open(os.path.join(C.RES, "analysis.json")))
        pairs = [(r["rule"], r["instrument"]) for r in an["ranking"]]
    path = os.path.join(C.RES, "null.json")
    allres = json.load(open(path)) if os.path.exists(path) else {}
    for rule, sym in pairs:
        r = null_pair(rule, sym)
        allres[f"{rule}:{sym}"] = r
        C.jdump(allres, path)
        print(json.dumps(r), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
