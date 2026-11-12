"""Configuration 11 of declared.json: random-entry null (R16).  IN SAMPLE ONLY.

goldlab.r2.null_test (mode 'day', 200 replays, seed 0) re-implemented on the in-sample slice (r2.null_test itself loads
the whole frame), with the BERLIN minute of day: every taken trade of configuration 1 (FP costs, 2014-2021) is re-entered
at market at a random bar of the same Berlin minute of day (any bar of the slice, frame start 2013-09-30 .. 2021-12-31,
as the lab's _minute_groups), same side, same stop distance relative to price (scaled at the random entry's mid), same
time-exit delay in bars (the order's planned exit), one position at a time, FP costs.  Appends line 11 to trials.jsonl.

    PYTHONDONTWRITEBYTECODE=1 python3 null.py
"""
import json
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import xetra as X  # noqa: E402
from goldlab.split import cut  # noqa: E402


def main(n_seeds=200, seed=0):
    decl = json.load(open(os.path.join(X.RES, "declared.json")))
    c = [c for c in decl["configurations"] if c["id"] == 11][0]
    tpath = os.path.join(X.RES, "trials.jsonl")
    lines = [json.loads(x) for x in open(tpath)]
    assert [x["id"] for x in lines] == list(range(1, 11)), "run.py first; the null line is written once"
    t0 = time.time()
    m1 = X.load_is()
    t, orders, info = X.run(m1, c["params"], "fp")
    rows = orders.reset_index(drop=True).iloc[t["oid"].to_numpy()]      # the order of each taken trade (oid = row)
    idx = m1.index
    fill_i = idx.searchsorted(t.entry_time.to_numpy())
    entry = t.entry.to_numpy(float)
    side = t.side.to_numpy()
    stop_rel = t.risk.to_numpy(float) / entry
    tgt_rel = np.full(len(t), np.nan)
    trail_rel = np.full(len(t), np.nan)
    be_rel = np.full(len(t), np.nan)
    xi = rows["exit_i"].to_numpy(np.int64)
    dur = np.where(xi >= 0, np.maximum(xi - fill_i, 1), -1)
    lo, hi = 0, int(idx.searchsorted(X.IS_END))
    ber = idx[lo:hi].tz_convert(X.BER)
    mod = (ber.hour * 60 + ber.minute).to_numpy()
    order = np.argsort(mod, kind="stable")
    bounds = np.searchsorted(mod[order], np.arange(1441))
    mod_c = mod[np.clip(fill_i - lo, 0, hi - lo - 1)]
    mid = (m1["bc"].to_numpy() + m1["ac"].to_numpy()) / 2
    costs = X.mode_costs("fp")
    rng = np.random.default_rng(seed)
    means, ns = [], []
    n_bars = len(m1)
    for _ in range(n_seeds):
        a, b = bounds[mod_c], bounds[mod_c + 1]
        ok = b > a
        pos = (a + (rng.random(len(t)) * np.maximum(b - a, 1)).astype(np.int64))
        ei = lo + order[np.minimum(pos, len(order) - 1)]
        px = mid[ei]
        no = pd.DataFrame({"entry_i": ei, "side": side, "stop_dist": stop_rel * px, "target_dist": tgt_rel * px,
                           "trail": trail_rel * px, "be": be_rel * px,
                           "exit_i": np.where(dur >= 0, np.minimum(ei + dur, n_bars - 1), -1)})[ok]
        tn = X.simulate(m1, no, sym=X.SYM, costs=costs, no_overlap=True)
        tn = cut(tn, "is")
        means.append(float(tn.R.mean()) if len(tn) else 0.0)
        ns.append(int(len(tn)))
    means = np.array(means)
    cand = float(t.R.mean())
    res = {"n": int(len(t)), "mode": "day (same Berlin minute of day, random day)", "replays": n_seeds, "seed": seed,
           "rule_mean_R": round(cand, 4), "null_mean_R": round(float(means.mean()), 4),
           "null_sd_R": round(float(means.std(ddof=1)), 4),
           "null_p95_R": round(float(np.percentile(means, 95)), 4),
           "null_p97.5_R": round(float(np.percentile(means, 97.5)), 4), "null_max_R": round(float(means.max()), 4),
           "null_min_R": round(float(means.min()), 4), "null_trades_per_replay_median": int(np.median(ns)),
           "percentile": round(float((means < cand).mean() * 100), 1),
           "pass": bool((means < cand).mean() >= 0.975)}
    np.save(os.path.join(X.RES, "null_means.npy"), means)
    line = {"id": 11, "name": c["name"], "role": "null", "params": c["params"], "costs": "fp", "null_spec": c["null"],
            "period": "rule trades: sessions 2014-2021; random bars: whole in-sample slice 2013-09-30 .. 2021-12-31",
            **info, "result": res, "sec": round(time.time() - t0, 1)}
    with open(tpath, "a") as f:
        f.write(json.dumps(line) + "\n")
    print(json.dumps(line, indent=1))


if __name__ == "__main__":
    main()
