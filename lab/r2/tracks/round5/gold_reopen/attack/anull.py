"""Attack null, in sample only (supersedes the null of arun.py, which did not charge the swap that a random-time replay
pays when it crosses the 17:00 New York rollover; the rule's own trades never cross one).

1. My random-time null (acommon.null_random_time) with FP costs including the swap: duration 'clock' (first bar at or
   after entry + 120 min, the rule's own exit) and 'bars' (same number of M1 bars as each rule trade, the convention of
   goldlab.r2.null_test), each with independent replays and with one position at a time; 200 replays, my seed.
2. The engineer's declared call reproduced on MY orders: goldlab.r2.null_test(mode='time', n_seeds=200, seed=0,
   no_overlap=True) with my in-sample slice installed in r2's frame cache and r2.load made unable to read any file.
   Expected: exactly the engineer's null.json if their orders equal mine (they do, trade for trade).
3. Seed spread of that same r2.null_test call (seeds 1-5) and of my null (4 more seeds).
Output: results/r2/round5/gold_reopen/attack/anull.json (+ null_means_*.npy)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acommon as A  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


def main():
    df = A.load_is()
    fr = A.Frame(df, 1.0)
    t = pd.read_parquet(os.path.join(A.OUT, "trades_01_main.parquet"))
    assert len(t) == 1737
    out = {"rule": {"n": int(len(t)), "mean_R": round(float(t.R.mean()), 5)}}
    # 1. my null
    for dur in ("clock", "bars"):
        for one in (False, True):
            key = f"mine_{dur}_{'one_position' if one else 'independent'}_with_swap"
            res, means = A.null_random_time(fr, t, 200, 20261114, dur, 120, swap=True, one_position=one)
            np.save(os.path.join(A.OUT, f"null_means_{key}.npy"), means)
            out[key] = res
            print(key, res, flush=True)
    seeds = {}
    for s in (1, 2, 3, 4):
        res, _ = A.null_random_time(fr, t, 200, 20261114 + s, "clock", 120, swap=True, one_position=False)
        seeds[int(20261114 + s)] = {"percentile": res["percentile"], "null_mean_R": res["null_mean_R"], "null_p975_R": res["null_p975_R"]}
    out["mine_clock_independent_with_swap_other_seeds"] = seeds
    print("my seeds", seeds, flush=True)
    # 2. the engineer's declared r2.null_test call, on my orders
    sys.path.insert(0, A.LAB)
    from goldlab import r2  # noqa: E402
    orig = r2.load

    def guarded(sym, start=None, end=None):
        if sym not in r2._fp_cache:
            raise RuntimeError("r2.load would read a whole file: refused")
        o = orig(sym, start, end)
        A.assert_is(o.index)
        return o

    r2.load = guarded
    r2.free()
    r2._fp_cache["xauusd"] = df

    def my_orders(m1, **p):
        assert m1.index.max() < A.CUT
        return pd.DataFrame({"entry_i": t.entry_i.to_numpy(np.int64), "side": 1, "etype": 0,
                             "stop_dist": t.stop_dist.to_numpy(float), "exit_i": t.exit_i_sched.to_numpy(np.int64)})

    rep = r2.null_test("xauusd", my_orders, {}, n_seeds=200, mode="time", period="is", no_overlap=True, seed=0)
    out["r2_null_test_seed0_on_my_orders"] = rep
    eng = json.load(open(os.path.join(A.ENG, "null.json")))
    out["engineer_null_json"] = {k: eng[k] for k in ("rule_mean_R", "null_mean_R", "null_p95_R", "null_max_R", "percentile", "pass")}
    out["r2_reproduces_engineer"] = bool(all(rep[k] == eng[k] for k in ("rule_mean_R", "null_mean_R", "null_p95_R", "null_max_R", "percentile")))
    print("r2.null_test seed 0 on my orders", rep, "| engineer", out["engineer_null_json"], "| equal", out["r2_reproduces_engineer"], flush=True)
    s2 = {}
    for s in (1, 2, 3, 4, 5):
        rr = r2.null_test("xauusd", my_orders, {}, n_seeds=200, mode="time", period="is", no_overlap=True, seed=s)
        s2[s] = {"percentile": rr["percentile"], "null_mean_R": rr["null_mean_R"]}
    out["r2_null_test_other_seeds"] = s2
    print("r2 other seeds", s2, flush=True)
    for k, v in r2._fp_cache.items():
        A.assert_is(v.index)
    r2.load = orig
    A.jdump(out, os.path.join(A.OUT, "anull.json"))


if __name__ == "__main__":
    main()
