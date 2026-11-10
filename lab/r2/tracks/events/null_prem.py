"""Random-entry null (IS) for the calendar-long rule: protocol mode 'time' + stricter mode 'day' (same clock time)."""
import json, sys, time
from runner import use, RES, r2, S
P = S.resolve(dict(rule="long", lead=5, exit="hold", hold=15, stop_atr=1.0))
out = {}
for sym in (sys.argv[1:] or ["us500", "us100"]):
    use(sym)
    for mode in ("time", "day"):
        t0 = time.time()
        nul = r2.null_test(sym, S.make_orders, P, n_seeds=200, mode=mode)
        out[f"{sym}:{mode}"] = nul
        print(sym, mode, nul, f"({time.time() - t0:.0f}s)", flush=True)
path = f"{RES}/null_prem.json"
json.dump(out, open(path, "w"), indent=1)
