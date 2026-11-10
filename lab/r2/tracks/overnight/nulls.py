"""Random-entry null tests (r2.null_test, IS only) for already-logged configurations.
Usage: python3 nulls.py <name> [...]      results appended to results/r2/overnight/nulls.json
"""
import importlib.util
import json
import os
import sys
import time

from common import LAB, RES, S, r2, use

WD = (0, 1, 2, 3, 4)
ALL = (0, 1, 2, 3, 4, 5, 6)


def _r1():
    spec = importlib.util.spec_from_file_location("seasonality_strategy", os.path.join(LAB, "tracks", "seasonality", "strategy.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CASES = {
    "btc_base": ("btcusd", None, dict(tz="NY", entry="17:05", exit="19:00", weekdays=ALL, side=1, stop_atr=2.0, atr_tf="1h"), "time"),
    "us100_evening": ("us100", None, dict(tz="NY", entry="18:30", exit="09:30", exit_next=True, weekdays=(6, 0, 1, 2, 3), side=1,
                                          stop_atr=1.0, atr_tf="D"), "time"),
    "us100_evening_up": ("us100", None, dict(tz="NY", entry="18:30", exit="09:30", exit_next=True, weekdays=(0, 1, 2, 3), side=1,
                                             stop_atr=1.0, atr_tf="D", cond="sess_up"), "day"),
    "us100_fade_long": ("us100", None, dict(tz="NY", entry="09:30", exit="16:00", weekdays=WD, side=1, stop_atr=1.0, atr_tf="D",
                                            cond="prev_sess_down"), "day"),
    "gold_fri_pm": ("xauusd", "FRI_PM_LIM", None, "time"),
    "gold_wknd": ("xauusd", "WKND_LIM", None, "time"),
}


def run(name, case=None, n_seeds=200):
    sym, r1name, params, mode = case or CASES[name]
    use(sym)
    if r1name:
        mod = _r1()
        mo, params = mod.make_orders, dict(mod.FINALISTS[r1name])
    else:
        mo = S.make_orders
    t0 = time.time()
    res = r2.null_test(sym, mo, params, n_seeds=n_seeds, mode=mode)
    res.update({"name": name, "sym": sym, "params": params, "secs": round(time.time() - t0)})
    print(json.dumps(res, default=str), flush=True)
    p = os.path.join(RES, "nulls.json")
    allr = json.load(open(p)) if os.path.exists(p) else {}
    allr[name] = res
    json.dump(allr, open(p, "w"), indent=1, default=str)
    return res


if __name__ == "__main__":
    for nm in sys.argv[1:]:
        run(nm)
    r2.free()
