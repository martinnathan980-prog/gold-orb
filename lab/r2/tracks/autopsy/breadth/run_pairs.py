"""PART 2 -- the frozen rules on the declared never-tried pairs (results/r2/autopsy/breadth/declared.json).

    NUMBA_CACHE_DIR=/tmp/... PYTHONDONTWRITEBYTECODE=1 python3 run_pairs.py [instrument ...]

One instrument frame (in-sample slice) in memory at a time, plus the us100 leader (mid closes) for nq_btc_follow.
Every declared pair is run once in three cost modes (fp and stress with the broker's 3-spread minimum stop; gross for
information), logged as ONE line of trials.jsonl (losing pairs alike), and its fp / stress trades are saved in
results/r2/autopsy/breadth/trades/.  A pair already logged is not run again (restart after a crash).
"""
import gc
import json
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402

import common as C  # noqa: E402

TRADES = os.path.join(C.RES, "trades")
KEEP = ["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk", "R", "ret", "hold_min"]
ORDER = (["us100", "us500", "us30", "ger40", "xauusd", "xagusd", "btcusd", "ethusd"] + C.FX + ["jp225"] + C.STOCKS)


def done_ids():
    p = os.path.join(C.RES, "trials.jsonl")
    if not os.path.exists(p):
        return set()
    return {json.loads(ln)["id"] for ln in open(p) if ln.strip()}


def run_pair(pid, rule, sym, m1, leader):
    reg = C.registry()
    t0 = time.time()
    res = {"id": pid, "rule": rule, "instrument": sym, "params": reg[rule][2], "track": reg[rule][0]}
    per = {}
    for mode in ("fp", "stress", "gross"):
        t, o, info = C.run_rule(rule, sym, m1, mode, leader=leader, min_spreads=None if mode == "gross" else 3.0)
        per[mode] = t
        res[f"orders_{mode}"] = info["orders"]
        res[f"refused_3spreads_{mode}"] = info["refused_3spreads"]
        res[mode] = C.summ(C.window(t))
        res[f"{mode}_before_2018_02"] = C.summ(C.window(t, start=pd.Timestamp("2000-01-01", tz="UTC"), end=C.COMMON_START)) if len(t) else {"n": 0}
    res["first_trade"] = str(per["fp"].entry_time.min()) if len(per["fp"]) else None
    res["breadth_criteria"] = C.breadth_pass(res["fp"], res["stress"])
    res["v2_criteria_info"] = C.v2_criteria(res["fp"], res["stress"])
    res["sec"] = round(time.time() - t0, 1)
    for mode in ("fp", "stress"):
        t = per[mode]
        if len(t):
            t[[c for c in KEEP if c in t.columns]].to_parquet(os.path.join(TRADES, f"{rule}__{sym}__{mode}.parquet"))
    C.append_trial(res)
    f, s = res["fp"], res["stress"]
    print(f"#{pid:3d} {rule:20s} {sym:7s} n {f.get('n', 0):5d} PF {f.get('pf', float('nan')):6.3f} exp {f.get('expectancy_R', float('nan')):+.4f} "
          f"t {f.get('t_stat', float('nan')):5.2f} yrs {f.get('years_2018_2021_pos', 0)}/4 | stress PF {s.get('pf', float('nan')):6.3f} "
          f"R {s.get('total_R', float('nan')):7.1f} | refused {res['refused_3spreads_fp']} | "
          f"{'PASS' if res['breadth_criteria']['pass'] else 'fail'} [{res['sec']}s]", flush=True)


def main(only):
    os.makedirs(TRADES, exist_ok=True)
    decl = json.load(open(os.path.join(C.RES, "declared.json")))
    by_sym = {}
    for p in decl["pairs"]:
        by_sym.setdefault(p["instrument"], []).append((p["id"], p["rule"]))
    done = done_ids()
    leader = None
    syms = [s for s in ORDER if s in by_sym and (not only or s in only)]
    for sym in syms:
        todo = [(i, r) for i, r in by_sym[sym] if i not in done]
        if not todo:
            continue
        if leader is None and any(r == "nq_btc_follow" for _, r in todo):
            leader = C.leader_series(C.load_is("us100"))
        m1 = C.load_is(sym)
        assert m1.index.max() < C.IS_END
        for pid, rule in todo:
            run_pair(pid, rule, sym, m1, leader)
        del m1
        C.clear_rule_caches()
        gc.collect()


if __name__ == "__main__":
    main(set(sys.argv[1:]))
